import asyncio
import logging
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise
from .serializers import (
    GeneratedTutorialSerializer,
    GeneratedQuizSerializer,
    GeneratedDiagramSerializer,
    GeneratedCodeExerciseSerializer,
    CONTENT_SERIALIZER_MAP,
)
from .generators import ContentGeneratorService

logger = logging.getLogger(__name__)

_MODEL_REGISTRY = [GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise]


def _resolve_concept(topic):
    """将 topic 字符串解析为 KnowledgeConcept 实例；未匹配时返回 (None, topic_str)"""
    if topic is None:
        return None, ''
    try:
        from learning_paths.models import KnowledgeConcept
    except ImportError:
        return None, str(topic)

    # 尝试按 ID 查找
    if isinstance(topic, int) or (isinstance(topic, str) and topic.isdigit()):
        try:
            return KnowledgeConcept.objects.get(id=int(topic)), ''
        except KnowledgeConcept.DoesNotExist:
            pass
    # 尝试按 name 查找
    try:
        return KnowledgeConcept.objects.get(name=str(topic)), ''
    except KnowledgeConcept.DoesNotExist:
        pass
    # 尝试按 slug 查找
    try:
        return KnowledgeConcept.objects.get(slug=str(topic)), ''
    except KnowledgeConcept.DoesNotExist:
        pass

    return None, str(topic)


def _run_async(coro):
    """在同步视图中安全执行异步协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # ASGI 环境下已有运行中的事件循环，使用 nest_asyncio 或回退方案
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _find_content_by_id(content_id):
    """按 id 遍历 4 个模型查找内容，返回 (instance, model_class) 或 (None, None)"""
    for model in _MODEL_REGISTRY:
        try:
            return model.objects.get(id=content_id), model
        except model.DoesNotExist:
            continue
    return None, None


def _get_serializer_for_instance(instance):
    """根据实例类型返回对应的序列化器"""
    for model_cls, serializer_cls in [
        (GeneratedTutorial, GeneratedTutorialSerializer),
        (GeneratedQuiz, GeneratedQuizSerializer),
        (GeneratedDiagram, GeneratedDiagramSerializer),
        (GeneratedCodeExercise, GeneratedCodeExerciseSerializer),
    ]:
        if isinstance(instance, model_cls):
            return serializer_cls
    return None


# ------------------------------------------------------------------
# 生成视图
# ------------------------------------------------------------------

class GenerateTutorialView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        topic = request.data.get('topic', '').strip()
        difficulty = request.data.get('difficulty', 'medium').strip()

        if not topic:
            return Response({'error': '请提供 topic 参数'}, status=status.HTTP_400_BAD_REQUEST)
        if difficulty not in ('easy', 'medium', 'hard'):
            return Response({'error': 'difficulty 必须是 easy/medium/hard'}, status=status.HTTP_400_BAD_REQUEST)

        concept, topic_name = _resolve_concept(topic)
        service = ContentGeneratorService()

        try:
            tutorial = _run_async(service.generate_tutorial(
                topic_name or topic, difficulty, concept, request.user
            ))
        except Exception as exc:
            logger.exception('生成教程失败')
            return Response({'error': f'生成失败: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = GeneratedTutorialSerializer(tutorial, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GenerateQuizView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        topic = request.data.get('topic', '').strip()
        difficulty = request.data.get('difficulty', 'medium').strip()
        question_count = request.data.get('question_count', 5)

        if not topic:
            return Response({'error': '请提供 topic 参数'}, status=status.HTTP_400_BAD_REQUEST)
        if difficulty not in ('easy', 'medium', 'hard'):
            return Response({'error': 'difficulty 必须是 easy/medium/hard'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            question_count = int(question_count)
            question_count = max(1, min(question_count, 20))
        except (ValueError, TypeError):
            return Response({'error': 'question_count 必须是整数'}, status=status.HTTP_400_BAD_REQUEST)

        concept, topic_name = _resolve_concept(topic)
        service = ContentGeneratorService()

        try:
            quiz = _run_async(service.generate_quiz(
                topic_name or topic, question_count, difficulty, concept, request.user
            ))
        except Exception as exc:
            logger.exception('生成测验失败')
            return Response({'error': f'生成失败: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = GeneratedQuizSerializer(quiz, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GenerateDiagramView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        topic = request.data.get('topic', '').strip()
        diagram_type = request.data.get('diagram_type', 'flowchart').strip()

        if not topic:
            return Response({'error': '请提供 topic 参数'}, status=status.HTTP_400_BAD_REQUEST)
        valid_types = {'flowchart', 'sequence', 'class', 'architecture', 'mindmap'}
        if diagram_type not in valid_types:
            return Response(
                {'error': f'diagram_type 必须是: {", ".join(sorted(valid_types))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        concept, topic_name = _resolve_concept(topic)
        service = ContentGeneratorService()

        try:
            diagram = _run_async(service.generate_diagram(
                topic_name or topic, diagram_type, 'medium', concept, request.user
            ))
        except Exception as exc:
            logger.exception('生成图表失败')
            return Response({'error': f'生成失败: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = GeneratedDiagramSerializer(diagram, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GenerateExerciseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        topic = request.data.get('topic', '').strip()
        language = request.data.get('language', 'python').strip()
        difficulty = request.data.get('difficulty', 'medium').strip()

        if not topic:
            return Response({'error': '请提供 topic 参数'}, status=status.HTTP_400_BAD_REQUEST)
        if difficulty not in ('easy', 'medium', 'hard'):
            return Response({'error': 'difficulty 必须是 easy/medium/hard'}, status=status.HTTP_400_BAD_REQUEST)

        concept, topic_name = _resolve_concept(topic)
        service = ContentGeneratorService()

        try:
            exercise = _run_async(service.generate_exercise(
                topic_name or topic, language, difficulty, concept, request.user
            ))
        except Exception as exc:
            logger.exception('生成练习失败')
            return Response({'error': f'生成失败: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = GeneratedCodeExerciseSerializer(exercise, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------
# 详情与重新生成
# ------------------------------------------------------------------

class GeneratedContentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        instance, _model = _find_content_by_id(pk)
        if instance is None:
            return Response({'error': '内容不存在'}, status=status.HTTP_404_NOT_FOUND)

        serializer_cls = _get_serializer_for_instance(instance)
        if serializer_cls is None:
            return Response({'error': '未知内容类型'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = serializer_cls(instance, context={'request': request})
        return Response(serializer.data)


class RegenerateContentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        instance, model_cls = _find_content_by_id(pk)
        if instance is None:
            return Response({'error': '内容不存在'}, status=status.HTTP_404_NOT_FOUND)

        params = instance.generation_params or {}
        service = ContentGeneratorService()

        try:
            if isinstance(instance, GeneratedTutorial):
                new_instance = _run_async(service.generate_tutorial(
                    params.get('topic', instance.title),
                    params.get('difficulty', 'medium'),
                    instance.topic,
                    request.user,
                ))
                serializer_cls = GeneratedTutorialSerializer
            elif isinstance(instance, GeneratedQuiz):
                new_instance = _run_async(service.generate_quiz(
                    params.get('topic', instance.title),
                    params.get('question_count', instance.question_count),
                    params.get('difficulty', 'medium'),
                    instance.topic,
                    request.user,
                ))
                serializer_cls = GeneratedQuizSerializer
            elif isinstance(instance, GeneratedDiagram):
                new_instance = _run_async(service.generate_diagram(
                    params.get('topic', instance.title),
                    params.get('diagram_type', instance.diagram_type),
                    params.get('difficulty', 'medium'),
                    instance.topic,
                    request.user,
                ))
                serializer_cls = GeneratedDiagramSerializer
            elif isinstance(instance, GeneratedCodeExercise):
                new_instance = _run_async(service.generate_exercise(
                    params.get('topic', instance.title),
                    params.get('language', instance.language),
                    params.get('difficulty', 'medium'),
                    instance.topic,
                    request.user,
                ))
                serializer_cls = GeneratedCodeExerciseSerializer
            else:
                return Response({'error': '未知内容类型'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception('重新生成失败')
            return Response({'error': f'重新生成失败: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = serializer_cls(new_instance, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
