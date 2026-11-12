from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gateway import AgentGateway
from .models import AgentRun, UserMemory
from .memory import UserMemoryStore
from .serializers import UserMemorySerializer
from data_security.adapters.django.privacy_api import PrivateResponseMixin
from .serializers import AgentRunSerializer, LearningRunRequestSerializer


class LearningRunCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LearningRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = AgentGateway().run_learning_task(
            user=request.user,
            message=serializer.validated_data['message'],
            agent_id=serializer.validated_data.get('agent_id', 'tutor'),
            context=serializer.validated_data.get('context') or {},
            conversation_history=serializer.validated_data.get('conversation_history') or [],
        )
        return Response(AgentRunSerializer(run).data, status=status.HTTP_201_CREATED)


class AgentRunListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AgentRunSerializer

    def get_queryset(self):
        return AgentRun.objects.filter(user=self.request.user)


class AgentRunDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AgentRunSerializer

    def get_queryset(self):
        return AgentRun.objects.filter(user=self.request.user)


class UserMemoryListView(PrivateResponseMixin, generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserMemorySerializer

    def get_queryset(self):
        return UserMemory.objects.filter(user=self.request.user).order_by('-updated_at', '-pk')


class UserMemoryDetailView(PrivateResponseMixin, generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserMemorySerializer

    def get_queryset(self):
        return UserMemory.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        UserMemoryStore(user=self.request.user).forget(
            memory_type=instance.memory_type, memory_key=instance.memory_key)
