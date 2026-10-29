from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gateway import AgentGateway
from .models import AgentRun
from .serializers import AgentRunSerializer, LearningRunRequestSerializer


class LearningRunCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LearningRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from teaching_agent.context import resolve_task_context

        trusted_context = resolve_task_context(
            user=request.user,
            request_data=serializer.validated_data,
        )
        run = AgentGateway().run_learning_task(
            user=request.user,
            message=serializer.validated_data['message'],
            agent_id=serializer.validated_data.get('agent_id', 'tutor'),
            context=(
                trusted_context.model_context()
                if trusted_context
                else serializer.validated_data.get('context') or {}
            ),
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
