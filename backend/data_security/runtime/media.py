"""Development media serving excludes all permission-checked file namespaces."""
from pathlib import PurePosixPath
from django.http import Http404
from django.views.static import serve


def serve_public_media(request, path, **kwargs):
    # Keep this aligned with the Nginx exclusions, including historical files.
    filename = PurePosixPath(path.replace('\\', '/'))
    parts = filename.parts
    # Django's static view normalizes traversal and leading slashes. Reject them
    # before its normalization can turn an allowed prefix into a private one.
    if parts and (filename.is_absolute() or '..' in parts
                  or parts[0].lower() in ('resources', 'resource_covers', 'feedback_evidence')):
        raise Http404
    return serve(request, path, **kwargs)
