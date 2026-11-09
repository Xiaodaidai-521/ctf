"""Closed browser-SDK compatibility boundary.

Provider authentication belongs to a server-side adapter. Even an old deployment
with COZE_SDK_ENABLED set must never put a provider credential into HTML or JS.
Only non-secret provider reference metadata may be kept in deployment config.
"""


def get_coze_sdk_script():
    """The legacy browser integration is disabled, irrespective of old settings."""
    return ''


def inject_coze_sdk(html_content):
    """Preserve upstream content without injecting a credential-bearing SDK."""
    return html_content


def is_html_response(content_type):
    """Retained for callers that classify proxy responses."""
    return bool(content_type) and 'text/html' in content_type.lower()
