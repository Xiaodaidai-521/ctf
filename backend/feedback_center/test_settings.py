"""Isolated settings for module 7 tests.

Import the normal project settings, but point ``ROOT_URLCONF`` at module 7's
own URLconf.  This avoids coupling module 7 tests to the parallel module 6 HTTP
work while still exercising the real database, models and permissions.
"""

from ctf_backend.settings import *  # noqa: F401,F403

# Module 6 is being written in parallel and currently has an unrelated model
# field clash.  Module 7 tests only need module 1 facts and the shared event
# store, so exclude the in-progress app here.  Production settings still include
# it; the optional module 6 adapter will connect once its models are valid.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'skill_review']  # noqa: F405
if 'feedback_center' not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS = list(INSTALLED_APPS) + ['feedback_center']  # noqa: F405

ROOT_URLCONF = 'feedback_center.test_urls'


