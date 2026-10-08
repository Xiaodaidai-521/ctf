from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    # SessionAuthentication may return 403 for missing credentials. Keep CSRF and
    # ordinary permission failures distinct from an expired/missing login session.
    if response is not None and isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        response.data['code'] = 'authentication_required'
    return response
