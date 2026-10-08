from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.utils import timezone


ACCESS_SALT = 'challenge-container-access'
COOKIE_NAME = 'challenge_access'


def build_access_url(container):
    if container.runtime_metadata.get('profile') == 'juice-shop':
        return container.access_url if container.is_running else ''
    host = getattr(settings, 'CONTAINER_PROXY_HOST', 'localhost:8000')
    scheme = getattr(settings, 'CONTAINER_PROXY_SCHEME', 'http')
    token = build_access_cookie_value(container)
    query = urlencode({'access_token': token})
    return f'{scheme}://{host}/challenge/{container.user_id}-{container.container_id}/?{query}'


def build_access_cookie_value(container):
    payload = {'user_id': container.user_id, 'container_id': container.container_id}
    return signing.dumps(payload, salt=ACCESS_SALT)


def access_cookie_max_age(container):
    lifetime = getattr(settings, 'CONTAINER_LIFETIME', 7200)
    if not container.expires_at:
        return lifetime
    remaining_seconds = int((container.expires_at - timezone.now()).total_seconds())
    return max(0, min(lifetime, remaining_seconds))


def validate_access_token(token, user_id, container_id):
    if not token:
        return False
    try:
        payload = signing.loads(
            token,
            salt=ACCESS_SALT,
            max_age=getattr(settings, 'CONTAINER_LIFETIME', 7200),
        )
    except signing.BadSignature:
        return False
    return payload.get('user_id') == user_id and payload.get('container_id') == container_id
