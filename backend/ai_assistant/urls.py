from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'conversations', views.AIConversationViewSet, basename='ai_conversation')

app_name = 'ai_assistant'

urlpatterns = [
    path('', include(router.urls)),
    path('list/', views.list_conversations, name='list_conversations'),
    path('solve/', views.solve_challenge, name='solve_challenge'),
    # 多智能体相关 API
    path('multi-agent/chat/', views.multi_agent_chat, name='multi_agent_chat'),
    path('multi-agent/handoff/', views.multi_agent_handoff, name='multi_agent_handoff'),
    path('multi-agent/agents/', views.list_agents, name='list_agents'),
    path('multi-agent/presets/', views.list_agent_presets, name='list_agent_presets'),
]
