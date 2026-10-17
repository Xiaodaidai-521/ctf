from django.urls import include, path


urlpatterns = [path("api/controlled-export/", include("controlled_export.urls"))]
