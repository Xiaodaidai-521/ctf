from io import BytesIO
from pathlib import PurePath
import tarfile
import zipfile

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers


RESOURCE_FILE_TYPES = {
    '.pdf': {'application/pdf'},
    '.zip': {'application/zip', 'application/x-zip-compressed'},
    '.tar.gz': {'application/gzip', 'application/x-gzip'},
    '.jpg': {'image/jpeg'},
    '.jpeg': {'image/jpeg'},
    '.png': {'image/png'},
    '.gif': {'image/gif'},
    '.webp': {'image/webp'},
    '.mp4': {'video/mp4'},
    '.txt': {'text/plain'},
    '.md': {'text/markdown', 'text/plain'},
}

COVER_IMAGE_TYPES = {
    '.jpg': ('image/jpeg', 'JPEG'),
    '.jpeg': ('image/jpeg', 'JPEG'),
    '.png': ('image/png', 'PNG'),
    '.gif': ('image/gif', 'GIF'),
    '.webp': ('image/webp', 'WEBP'),
}

SCRIPT_MARKERS = (b'<script', b'<!doctype html', b'<html', b'<svg', b'<?xml')


def _extension(filename):
    lowered = filename.lower()
    if lowered.endswith('.tar.gz'):
        return '.tar.gz'
    return PurePath(lowered).suffix


def _read_upload(upload):
    upload.seek(0)
    data = upload.read()
    upload.seek(0)
    return data


def _validate_size(upload, maximum):
    if upload.size > maximum:
        raise serializers.ValidationError('The uploaded file exceeds the configured size limit.')


def _validate_image(upload, extension, allowed_types):
    expected_type, expected_format = allowed_types[extension]
    if upload.content_type not in {expected_type}:
        raise serializers.ValidationError('The declared content type does not match the file extension.')
    try:
        upload.seek(0)
        image = Image.open(upload)
        image.verify()
        if image.format != expected_format:
            raise serializers.ValidationError('The image content does not match the file extension.')
    except (UnidentifiedImageError, OSError):
        raise serializers.ValidationError('The uploaded image is invalid.')
    finally:
        upload.seek(0)


def validate_resource_file(upload):
    extension = _extension(upload.name)
    if extension not in RESOURCE_FILE_TYPES:
        raise serializers.ValidationError('This file extension is not allowed.')
    _validate_size(upload, settings.RESOURCE_MAX_UPLOAD_SIZE)
    if upload.content_type not in RESOURCE_FILE_TYPES[extension]:
        raise serializers.ValidationError('The declared content type does not match the file extension.')

    if extension in COVER_IMAGE_TYPES:
        _validate_image(upload, extension, COVER_IMAGE_TYPES)
        return upload

    data = _read_upload(upload)
    if extension == '.pdf' and not data.startswith(b'%PDF-'):
        raise serializers.ValidationError('The uploaded PDF is invalid.')
    if extension == '.zip':
        _validate_zip_archive(data)
    if extension == '.tar.gz':
        try:
            with tarfile.open(fileobj=BytesIO(data), mode='r:gz'):
                pass
        except tarfile.TarError:
            raise serializers.ValidationError('The uploaded TAR.GZ archive is invalid.')
    if extension in {'.txt', '.md'}:
        try:
            text = data.decode('utf-8').lower().encode('utf-8')
        except UnicodeDecodeError:
            raise serializers.ValidationError('Text uploads must be UTF-8 encoded.')
        if any(marker in text for marker in SCRIPT_MARKERS):
            raise serializers.ValidationError('HTML, SVG, and script-capable content is not allowed.')
    return upload


def _validate_zip_archive(data):
    maximum_uncompressed_size = getattr(
        settings,
        'RESOURCE_MAX_ARCHIVE_UNCOMPRESSED_SIZE',
        settings.RESOURCE_MAX_UPLOAD_SIZE,
    )
    maximum_entries = getattr(settings, 'RESOURCE_MAX_ARCHIVE_ENTRIES', 1000)
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > maximum_entries:
                raise serializers.ValidationError('The ZIP archive contains too many entries.')
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise serializers.ValidationError('Encrypted ZIP archives are not allowed.')

            expected_size = sum(entry.file_size for entry in entries)
            if expected_size > maximum_uncompressed_size:
                raise serializers.ValidationError('The ZIP archive expands beyond the allowed size.')

            actual_size = 0
            for entry in entries:
                if entry.is_dir():
                    continue
                with archive.open(entry) as member:
                    while chunk := member.read(64 * 1024):
                        actual_size += len(chunk)
                        if actual_size > maximum_uncompressed_size:
                            raise serializers.ValidationError('The ZIP archive expands beyond the allowed size.')
    except zipfile.BadZipFile:
        raise serializers.ValidationError('The uploaded ZIP archive is invalid.')


def validate_cover_image(upload):
    extension = _extension(upload.name)
    if extension not in COVER_IMAGE_TYPES:
        raise serializers.ValidationError('Cover images must be JPEG, PNG, GIF, or WebP.')
    _validate_size(upload, settings.RESOURCE_MAX_COVER_IMAGE_SIZE)
    _validate_image(upload, extension, COVER_IMAGE_TYPES)
    return upload
