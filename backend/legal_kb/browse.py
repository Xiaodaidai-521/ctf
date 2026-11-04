"""Read-only source catalogue. Teaching evidence stays in its Scope gateway."""

from urllib.parse import urlsplit

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, F, Q, Value
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from articles.models import Article
from learning_knowledge.models import Material
from learning_paths.models import KnowledgeConcept
from rag_ingestion.models import DocumentSource
from resources.models import Resource

from .models import LegalClause, LegalDocument, LegalKnowledgeEmbedding
from .permissions import IsLegalKbReader
from .services.hashing import sha256_text
from .services.visibility import allowed_document_visibilities, apply_embedding_visibility


SOURCES = {
    'legal_document': (LegalDocument, 'legal', '法律库文档', 'title'),
    'document': (DocumentSource, 'legal', '上传文档', 'title'),
    'article': (Article, 'platform', '文章', 'title'),
    'resource': (Resource, 'platform', '学习资源', 'title'),
    'knowledge_concept': (KnowledgeConcept, 'platform', '知识点', 'name'),
}


class LibraryQuery(serializers.Serializer):
    group = serializers.ChoiceField(choices=['legal', 'platform'], default='legal')
    source_type = serializers.ChoiceField(choices=list(SOURCES), required=False)
    q = serializers.CharField(max_length=500, allow_blank=True, default='')
    page = serializers.IntegerField(min_value=1, default=1)


def source_url(value):
    try:
        url = urlsplit(value or '')
        if url.scheme in {'http', 'https'} and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return ''


def embeddings(source_type, user):
    model = SOURCES[source_type][0]
    return apply_embedding_visibility(LegalKnowledgeEmbedding.objects.filter(
        source_type=source_type, content_type=ContentType.objects.get_for_model(model),
    ), user).defer('embedding', 'embedding_vector').order_by('chunk_index', 'pk')


def sources(source_type, user):
    model = SOURCES[source_type][0]
    queryset = model.objects.all()
    if source_type == 'legal_document':
        registered = Material.objects.filter(source_type='legal_clause').values('source_object_id')
        parents = LegalClause.objects.filter(pk__in=registered).values('document_id')
        return queryset.exclude(pk__in=parents)
    registered = Material.objects.filter(source_type=source_type).values('source_object_id')
    queryset = queryset.exclude(pk__in=registered)
    if source_type == 'document':
        return queryset.filter(visibility__in=allowed_document_visibilities(user))
    if source_type in {'article', 'resource'}:
        queryset = queryset.filter(status='approved')
    return queryset.filter(pk__in=embeddings(source_type, user).values('object_id'))


def source_locator(source_type, obj):
    if source_type == 'document':
        return obj.filename
    if source_type == 'knowledge_concept':
        return f'知识点 · {obj.slug}'
    return SOURCES[source_type][2]


def chunk_locator(chunk):
    metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
    path = metadata.get('heading_path')
    if isinstance(path, list) and all(isinstance(item, str) for item in path):
        heading = ' / '.join(path)
    else:
        heading = str(metadata.get('chapter') or metadata.get('article_number') or '')
    return heading or f'索引块 {chunk.chunk_index + 1}（原文定位待补齐）'


def projected_chunks(source_type, obj, user):
    if source_type == 'legal_document':
        clauses = list(obj.clauses.order_by('order', 'pk'))
        indexed = set(apply_embedding_visibility(LegalKnowledgeEmbedding.objects.filter(
            source_type='legal_clause', content_type=ContentType.objects.get_for_model(LegalClause),
            object_id__in=[clause.pk for clause in clauses],
        ), user).values_list('object_id', flat=True))
        return [{
            'id': f'clause:{clause.pk}', 'title': clause.title or obj.title,
            'text': clause.text,
            'locator': ' / '.join(filter(None, [clause.chapter, clause.article_number, clause.clause_key])),
            'index_status': 'indexed' if clause.pk in indexed else 'not_indexed',
        } for clause in clauses]
    if source_type == 'document' and obj.status != 'completed':
        return []
    return [{
        'id': f'embedding:{chunk.pk}', 'title': obj.name if source_type == 'knowledge_concept' else obj.title,
        'text': chunk.text, 'locator': chunk_locator(chunk),
        # An identity string alone is not proof of compatibility with today's provider.
        'index_status': 'versioned' if chunk.index_version else 'legacy_lexical',
    } for chunk in embeddings(source_type, user).filter(object_id=obj.pk)
        if sha256_text(chunk.text) == chunk.text_hash]


def projection(source_type, obj, user, *, detail=False, query=''):
    _, group, label, title_field = SOURCES[source_type]
    chunks = projected_chunks(source_type, obj, user)
    match = next((chunk for chunk in chunks if query and query.casefold() in chunk['text'].casefold()), None)
    first = match or (chunks[0] if chunks else None)
    text = first['text'] if first else (obj.full_text if source_type == 'legal_document' else '')
    start = max(0, text.casefold().find(query.casefold()) - 80) if query else 0
    paths = {
        'article': f'/community/article/{obj.pk}',
        'resource': f'/resources?resource={obj.pk}',
        'knowledge_concept': f'/capability-map?concept={obj.pk}',
    }
    result = {
        'id': f'{source_type}:{obj.pk}', 'title': getattr(obj, title_field),
        'group': group, 'source_type': source_type, 'source_label': label, 'object_id': obj.pk,
        'excerpt': text[start:start + 360],
        'locator': first['locator'] if first else source_locator(source_type, obj),
        'chunk_count': len(chunks), 'source_url': source_url(getattr(obj, 'source_url', '')),
        'source_path': paths.get(source_type, ''), 'status': getattr(obj, 'status', 'indexed'),
    }
    if detail:
        result['chunks'] = chunks
        if source_type == 'legal_document':
            result['full_text'] = obj.full_text
    return result


class LibraryView(APIView):
    permission_classes = [IsLegalKbReader]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['Vary'] = 'Authorization, Cookie'
        return response

    def get(self, request):
        if set(request.query_params) - set(LibraryQuery().fields):
            raise serializers.ValidationError('Unsupported fields.')
        serializer = LibraryQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        options = serializer.validated_data
        selected = [kind for kind, (_, group, _, _) in SOURCES.items()
                    if group == options['group'] and (not options.get('source_type') or kind == options['source_type'])]
        if not selected:
            raise serializers.ValidationError('Source type does not belong to this group.')
        queries = []
        for kind in selected:
            queryset = sources(kind, request.user)
            if options['q']:
                match = Q(**{f'{SOURCES[kind][3]}__icontains': options['q']})
                if kind == 'legal_document':
                    match |= Q(full_text__icontains=options['q']) | Q(clauses__text__icontains=options['q'])
                else:
                    chunks = embeddings(kind, request.user).filter(text__icontains=options['q'])
                    if kind == 'document':
                        match |= Q(status='completed', pk__in=chunks.values('object_id'))
                    else:
                        match |= Q(pk__in=chunks.values('object_id'))
                queryset = queryset.filter(match)
            queries.append(queryset.order_by().annotate(
                library_title=F(SOURCES[kind][3]), library_source=Value(kind, output_field=CharField()),
            ).values('pk', 'library_title', 'library_source').distinct())
        catalogue = queries[0].union(*queries[1:]).order_by('library_source', 'library_title', 'pk')
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(catalogue, request, view=self)
        rows = []
        for row in page:
            # Recheck live source restrictions when hydrating a result; never trust an old index ACL.
            obj = sources(row['library_source'], request.user).filter(pk=row['pk']).first()
            if obj:
                rows.append(projection(row['library_source'], obj, request.user, query=options['q']))
        return paginator.get_paginated_response(rows)


class LibraryDetailView(LibraryView):
    def get(self, request, source_type, object_id):
        if request.query_params:
            raise serializers.ValidationError('Unsupported fields.')
        if source_type not in SOURCES:
            raise NotFound()
        obj = sources(source_type, request.user).filter(pk=object_id).first()
        if not obj:
            raise NotFound()
        return Response(projection(source_type, obj, request.user, detail=True))
