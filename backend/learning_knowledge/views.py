from django.contrib.auth import get_user_model
from django.db import DatabaseError
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_map.models import CatalogVersion, TaskPackage
from .models import CourseGrant, Material, MaterialRevision
from .policy import Scope, can_manage, is_admin, unavailable
from .review import inspection, new_revision, parse_candidate, register, transition
from .serializers import ActionSerializer, GrantSerializer, IssueSerializer, RegisterSerializer, RevisionSerializer, SearchSerializer
from .services import read_evidence, report_issue, search


def validated(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PrivateView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['Vary'] = 'Authorization, Cookie'
        return response

    def handle_exception(self, exc):
        if isinstance(exc, DatabaseError):
            error = APIException('Material authorization unavailable.')
            error.status_code = 503
            return super().handle_exception(error)
        return super().handle_exception(exc)


class SearchView(PrivateView):
    def post(self, request):
        data = validated(SearchSerializer, request.data)
        scope = Scope(request.user, data.pop('attempt_id'))
        payload = search(scope, **data)
        # Final projection is hydrated again, not copied from cached results.
        payload['results'] = [read_evidence(card['evidence_id'], request.user) for card in payload['results']]
        return Response(payload)


class EvidenceView(PrivateView):
    def get(self, request, evidence_id):
        if request.query_params:
            raise ValidationError('Unsupported fields.')
        return Response(read_evidence(evidence_id, request.user))


class EvidenceDownloadView(EvidenceView):
    """Download is the same short authorized projection, never a raw source file."""


class IssueView(PrivateView):
    def post(self, request):
        data = validated(IssueSerializer, request.data)
        return Response(report_issue(scope=Scope(request.user, data.pop('attempt_id')), **data))


class MaterialListView(PrivateView):
    def get(self, request):
        rows = []
        for material in Material.objects.select_related('catalog').order_by('pk'):
            if can_manage(request.user, material):
                revision = material.revisions.order_by('-revision').first()
                if revision:
                    rows.append({'material_id': str(material.material_id), 'revision': revision.revision,
                                 'title': revision.title, 'review_status': revision.review_status,
                                 'material_class': material.material_class, 'catalog_version': material.catalog.version})
        return Response({'results': rows})

    def post(self, request):
        data = validated(RegisterSerializer, request.data)
        catalog = CatalogVersion.objects.filter(version=data.pop('catalog_version')).first()
        if not catalog:
            raise unavailable()
        task_ids = data.pop('task_ids')
        tasks = list(TaskPackage.objects.filter(pk__in=task_ids, catalog=catalog))
        if len(tasks) != len(set(task_ids)):
            raise unavailable()
        revision = register(actor=request.user, catalog=catalog, tasks=tasks, **data)
        parse_candidate(revision_id=revision.pk, token=revision.ingestion_token)
        return Response({'material_id': str(revision.material.material_id), 'revision': revision.revision}, status=201)


def get_revision(material_id, actor, number=None):
    material = Material.objects.filter(material_id=material_id).first()
    if not material or not can_manage(actor, material):
        raise unavailable()
    revisions = material.revisions.select_related('material')
    revision = revisions.filter(revision=number).first() if number else revisions.order_by('-revision').first()
    if not revision:
        raise unavailable()
    return revision


class ChunksView(PrivateView):
    def get(self, request, material_id):
        if set(request.query_params) - {'revision'}:
            raise ValidationError('Unsupported fields.')
        number = request.query_params.get('revision')
        if number and not number.isdigit():
            raise unavailable()
        return Response(inspection(get_revision(material_id, request.user, number), request.user))


class RevisionView(PrivateView):
    def post(self, request, material_id):
        current = get_revision(material_id, request.user)
        data = validated(RevisionSerializer, request.data)
        tasks = list(TaskPackage.objects.filter(pk__in=data['task_ids'], catalog=current.material.catalog))
        if len(tasks) != len(set(data['task_ids'])):
            raise unavailable()
        revision = new_revision(actor=request.user, material=current.material, tasks=tasks, metadata=data['metadata'])
        parse_candidate(revision_id=revision.pk, token=revision.ingestion_token)
        return Response({'material_id': str(current.material.material_id), 'revision': revision.revision}, status=201)


class ActionView(PrivateView):
    def post(self, request, material_id, action):
        data = validated(ActionSerializer, request.data)
        revision = transition(actor=request.user, material_id=material_id, action=action, **data)
        return Response({'revision': revision.revision, 'review_status': revision.review_status,
                         'acl_version': revision.material.acl_version})


class GrantView(PrivateView):
    def post(self, request):
        if not is_admin(request.user):
            raise PermissionDenied('Administrator permission required.')
        data = validated(GrantSerializer, request.data)
        catalog = CatalogVersion.objects.filter(version=data.pop('catalog_version')).first()
        user = get_user_model().objects.filter(pk=data.pop('user_id'), is_active=True).first()
        if not catalog or not user:
            raise unavailable()
        if data['can_review'] and getattr(user, 'role', '') not in {'teacher', 'admin'}:
            raise ValidationError('Review duty requires a teacher or administrator.')
        if data['maintain_secrets'] and not is_admin(user):
            raise ValidationError('Secret maintenance requires an administrator.')
        grant, _ = CourseGrant.objects.update_or_create(catalog=catalog, user=user, defaults=data)
        return Response({'grant_id': grant.pk, 'active': grant.active})
