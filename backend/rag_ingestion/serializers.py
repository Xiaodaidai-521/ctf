from rest_framework import serializers

from .models import DocumentSource


class DocumentSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentSource
        fields = [
            'id', 'title', 'filename', 'mime', 'byte_size', 'status',
            'visibility', 'parser', 'chunk_count', 'embedded_count',
            'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
