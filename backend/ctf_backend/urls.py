"""
URL configuration for ctf_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponseNotFound
from challenges import views as challenge_views


def resource_media_disabled(request, path):
    return HttpResponseNotFound()


urlpatterns = [
    path('media/resources/<path:path>', resource_media_disabled, name='resource-media-disabled'),
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/challenges/', include('challenges.urls')),
    path('api/submissions/', include('submissions.urls')),
    path('api/resources/', include('resources.urls')),
    path('api/articles/', include('articles.urls')),
    path('api/learning-paths/', include('learning_paths.urls')),
    path('api/exams/', include('exams.urls')),
    path('api/ai/', include('ai_assistant.urls')),
    path('api/ai/learning/', include('ai_assistant.urls_learning')),
    path('api/announcements/', include('announcements.urls')),
    path('api/audit/', include('audit.urls')),
    path('api/legal/', include('legal.urls')),
    path('api/legal-kb/', include('legal_kb.urls')),
    path('api/agent-runtime/', include('agent_runtime.urls')),
    path('api/rag-ingestion/', include('rag_ingestion.urls')),
    path('api-auth/', include('rest_framework.urls')),
    # CTF代理路由 - 处理/challenge/路径转发到FRP
    # 必须在API路由之后，避免冲突
    path('challenge/<path:path>/', challenge_views.proxy_challenge_view, name='proxy_challenge'),
    # 健康检查
    path('proxy/health/', challenge_views.health_check_view, name='proxy_health'),
    path('api/student-profiles/', include('student_profiles.urls')),
    path('api/content/', include('content_generator.urls')),
    path('api/analytics/', include('learning_analytics.urls')),
]

# 开发环境下的媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
