import hashlib
import json
import re
import logging
from django.core.cache import cache
from django.conf import settings
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class ContentGeneratorService:
    """AI内容生成服务 —— 封装多智能体调用、解析、持久化与缓存"""

    def __init__(self):
        from ai_assistant.service import get_multi_agent_service

        self.ai_service = get_multi_agent_service()
        self.cache_ttl = getattr(settings, 'CONTENT_GENERATOR_CACHE_TTL', 86400)

    # ------------------------------------------------------------------
    # 公共工具方法
    # ------------------------------------------------------------------

    def _cache_key(self, topic, difficulty, content_type):
        raw = f'{topic}:{difficulty}:{content_type}'
        return f'content_gen:{hashlib.md5(raw.encode()).hexdigest()}'

    def _parse_sections(self, markdown):
        """按 ## 二级标题将 Markdown 拆分为 [{title, content}]"""
        sections = []
        blocks = re.split(r'\n(?=## )', markdown)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split('\n', 1)
            title = lines[0].replace('## ', '').replace('##', '').strip()
            body = lines[1].strip() if len(lines) > 1 else ''
            sections.append({'title': title, 'content': body})
        return sections

    def _extract_mermaid(self, text):
        """从AI响应文本中提取 mermaid 代码块"""
        match = re.search(r'```mermaid\s*\n(.*?)```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r'```\s*\n(.*?)```', text, re.DOTALL)
        return match.group(1).strip() if match else text

    def _parse_json_from_response(self, text):
        """从AI响应中提取 JSON —— 尝试直接解析或从代码块中提取"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 提取 ```json ... ``` 代码块
        match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 提取第一个 [ ... ] 或 { ... }
        for pattern in [r'\[.*\]', r'\{.*\}']:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue
        return None

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_tutorial_prompt(self, topic, difficulty):
        level_desc = {'easy': '入门初学者', 'medium': '有一定基础的学习者', 'hard': '进阶学习者'}
        return (
            f'你是一位资深的网络安全教育专家。请为主题「{topic}」生成一份结构化教学教程，'
            f'目标受众为{level_desc.get(difficulty, "学习者")}。\n\n'
            f'要求：\n'
            f'1. 每个主要章节使用 ## 二级标题开头\n'
            f'2. 内容需包含：概述与学习目标 → 核心概念讲解 → 实战示例 → 常见误区与注意事项 → 总结与进阶方向\n'
            f'3. 专业准确、循序渐进，适当使用代码块和表格增强可读性\n'
            f'4. 请直接用 Markdown 格式输出，不要加额外的开场白或结尾语'
        )

    def _build_quiz_prompt(self, topic, question_count, difficulty):
        return (
            f'你是一位网络安全教育培训专家。请为主题「{topic}」生成 {question_count} 道选择题，'
            f'难度等级为「{difficulty}」。\n\n'
            f'请严格以 JSON 数组格式返回，每道题包含以下字段：\n'
            f'  question: 题目文本\n'
            f'  options: ["A. xxx", "B. xxx", "C. xxx", "D. xxx"]\n'
            f'  answer: 正确选项字母 (如 "A")\n'
            f'  explanation: 答案解析\n\n'
            f'示例格式：\n'
            f'[{{"question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], '
            f'"answer": "B", "explanation": "..."}}]\n\n'
            f'请直接输出 JSON 数组，不要加额外说明。'
        )

    def _build_diagram_prompt(self, topic, diagram_type):
        type_guide = {
            'flowchart': '展示流程步骤和分支判断',
            'sequence': '展示参与方之间的交互时序',
            'class': '展示类、属性、方法及类间关系',
            'architecture': '展示系统组件、模块及数据流',
            'mindmap': '以中心主题向外辐射的思维导图',
        }
        return (
            f'你是一位系统架构与可视化专家。请为主题「{topic}」生成一个 Mermaid {diagram_type} 图表。\n'
            f'图表用途：{type_guide.get(diagram_type, "直观展示主题内容")}\n\n'
            f'要求：\n'
            f'1. 输出完整可用的 Mermaid 代码块（```mermaid ... ```）\n'
            f'2. 节点和连线标注使用中文\n'
            f'3. 结构清晰、逻辑准确\n'
            f'4. 请直接输出 Mermaid 代码块，不要加额外说明'
        )

    def _build_exercise_prompt(self, topic, language, difficulty):
        return (
            f'你是一位编程教育与安全实战专家。请为主题「{topic}」创建一个编程练习题，'
            f'编程语言为 {language}，难度为「{difficulty}」。\n\n'
            f'请严格以 JSON 格式返回，包含以下字段：\n'
            f'  description: 题目描述 (Markdown)\n'
            f'  starter_code: 提供给学生的初始代码\n'
            f'  test_cases: [{{"input": "...", "expected": "..."}}]\n'
            f'  solution_code: 参考答案代码\n'
            f'  hints: ["提示1", "提示2"] (从模糊到具体，2-3条)\n\n'
            f'请直接输出 JSON，不要加额外说明。'
        )

    # ------------------------------------------------------------------
    # 生成方法
    # ------------------------------------------------------------------

    async def generate_tutorial(self, topic_name, difficulty='medium', concept=None, user=None):
        cache_key = self._cache_key(topic_name, difficulty, 'tutorial')
        cached_id = cache.get(cache_key)
        if cached_id:
            try:
                get = sync_to_async(GeneratedTutorial.objects.get)
                return await get(id=cached_id)
            except GeneratedTutorial.DoesNotExist:
                cache.delete(cache_key)

        prompt = self._build_tutorial_prompt(topic_name, difficulty)
        result = await self.ai_service.chat_with_agent('architect', prompt)
        raw_content = result.get('content', '')
        sections = self._parse_sections(raw_content)
        reviewer = result.get('agent_id', '')

        create = sync_to_async(GeneratedTutorial.objects.create)
        tutorial = await create(
            title=f'{topic_name} 教程',
            raw_content=raw_content,
            sections=sections,
            difficulty=difficulty,
            topic=concept,
            created_by=user,
            reviewer_agent_id=reviewer,
            generation_params={'topic': topic_name, 'difficulty': difficulty},
            estimated_minutes=max(len(sections) * 10, 15),
        )
        cache.set(cache_key, tutorial.id, self.cache_ttl)
        return tutorial

    async def generate_quiz(self, topic_name, question_count=5, difficulty='medium', concept=None, user=None):
        cache_key = self._cache_key(topic_name, difficulty, 'quiz')
        cached_id = cache.get(cache_key)
        if cached_id:
            try:
                get = sync_to_async(GeneratedQuiz.objects.get)
                return await get(id=cached_id)
            except GeneratedQuiz.DoesNotExist:
                cache.delete(cache_key)

        prompt = self._build_quiz_prompt(topic_name, question_count, difficulty)
        result = await self.ai_service.chat_with_agent('analyst', prompt)
        raw_content = result.get('content', '')
        parsed = self._parse_json_from_response(raw_content)
        questions = parsed if isinstance(parsed, list) else []
        reviewer = result.get('agent_id', '')

        create = sync_to_async(GeneratedQuiz.objects.create)
        quiz = await create(
            title=f'{topic_name} 测验',
            raw_content=raw_content,
            questions=questions,
            question_count=len(questions) if questions else question_count,
            difficulty=difficulty,
            topic=concept,
            created_by=user,
            reviewer_agent_id=reviewer,
            generation_params={
                'topic': topic_name,
                'question_count': question_count,
                'difficulty': difficulty,
            },
            passing_score=60,
        )
        cache.set(cache_key, quiz.id, self.cache_ttl)
        return quiz

    async def generate_diagram(self, topic_name, diagram_type='flowchart', difficulty='medium', concept=None, user=None):
        cache_key = self._cache_key(topic_name, difficulty, 'diagram')
        cached_id = cache.get(cache_key)
        if cached_id:
            try:
                get = sync_to_async(GeneratedDiagram.objects.get)
                return await get(id=cached_id)
            except GeneratedDiagram.DoesNotExist:
                cache.delete(cache_key)

        prompt = self._build_diagram_prompt(topic_name, diagram_type)
        result = await self.ai_service.chat_with_agent('architect', prompt)
        raw_content = result.get('content', '')
        mermaid_code = self._extract_mermaid(raw_content)
        reviewer = result.get('agent_id', '')

        create = sync_to_async(GeneratedDiagram.objects.create)
        diagram = await create(
            title=f'{topic_name} {diagram_type}图',
            raw_content=raw_content,
            mermaid_code=mermaid_code,
            diagram_type=diagram_type,
            difficulty=difficulty,
            topic=concept,
            created_by=user,
            reviewer_agent_id=reviewer,
            generation_params={
                'topic': topic_name,
                'diagram_type': diagram_type,
                'difficulty': difficulty,
            },
        )
        cache.set(cache_key, diagram.id, self.cache_ttl)
        return diagram

    async def generate_exercise(self, topic_name, language='python', difficulty='medium', concept=None, user=None):
        cache_key = self._cache_key(topic_name, difficulty, 'exercise')
        cached_id = cache.get(cache_key)
        if cached_id:
            try:
                get = sync_to_async(GeneratedCodeExercise.objects.get)
                return await get(id=cached_id)
            except GeneratedCodeExercise.DoesNotExist:
                cache.delete(cache_key)

        prompt = self._build_exercise_prompt(topic_name, language, difficulty)
        result = await self.ai_service.chat_with_agent('developer', prompt)
        raw_content = result.get('content', '')
        parsed = self._parse_json_from_response(raw_content) or {}
        reviewer = result.get('agent_id', '')

        create = sync_to_async(GeneratedCodeExercise.objects.create)
        exercise = await create(
            title=f'{topic_name} 练习',
            raw_content=raw_content,
            language=language,
            starter_code=parsed.get('starter_code', ''),
            test_cases=parsed.get('test_cases', []),
            solution_code=parsed.get('solution_code', ''),
            hints=parsed.get('hints', []),
            difficulty=difficulty,
            topic=concept,
            created_by=user,
            reviewer_agent_id=reviewer,
            generation_params={
                'topic': topic_name,
                'language': language,
                'difficulty': difficulty,
            },
        )
        cache.set(cache_key, exercise.id, self.cache_ttl)
        return exercise


# 延迟导入模型，避免循环依赖
from .models import GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise  # noqa: E402
