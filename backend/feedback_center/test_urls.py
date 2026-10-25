"""Module-7-only URLconf used by isolated tests.

The workspace also contains an in-progress module 6 app whose HTTP layer is
being written in parallel.  Module 7 tests must not depend on that layer or
modify its files, so they use this URLconf instead of the project root one.
Production wiring is still ``ctf_backend/urls.py``.
"""

from django.urls import include, path

urlpatterns = [
    path('api/users/', include('users.urls')),
    path('api/announcements/', include('announcements.urls')),
    path('api/learning-map/', include('learning_map.urls')),
    path('api/feedback/', include('feedback_center.urls')),
]
