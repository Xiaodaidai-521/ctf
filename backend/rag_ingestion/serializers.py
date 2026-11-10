from rest_framework import serializers

from data_security.adapters.django.rag import protect_rag_fields

from .models import DocumentSource


class ProtectedRagSerializer(serializers.ModelSerializer):
    rag_text_fields = ()

    def to_representation(self, instance):
        value = super().to_representation(instance)
        at = getattr(instance, 'updated_at', instance.created_at)
        return protect_rag_fields(value, text_fields=self.rag_text_fields,
            object_ref=f'rag/{instance._meta.label_lower}/{instance.pk}',
            object_version='v' + str(int(at.timestamp() * 1_000_000)))


class DocumentSourceSerializer(ProtectedRagSerializer):
    rag_text_fields = ('error_message',)

    class Meta:
        model = DocumentSource
        fields = [
            'id', 'title', 'filename', 'mime', 'byte_size', 'status',
            'visibility', 'parser', 'chunk_count', 'embedded_count',
            'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
