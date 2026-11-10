"""Business-facing handles for injected OfficialAIPort instances, never raw SDKs."""
import asyncio
from dataclasses import dataclass, replace

from data_security.contracts import (AIRequest, BoundedPayload, FrozenJSON, MediaType, Outlet,
    PayloadKind, ProtectionError)


@dataclass(frozen=True, slots=True, repr=False)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True, repr=False)
class ChatResponse:
    content: str
    provider: str
    model: str
    usage: dict | None = None


class ProviderHandle:
    def __init__(self, *, name, model, port, context_factory, binding, limits, sanitize_response, run_sync):
        self.name, self.model = name, model
        self._port, self._context = port, context_factory
        self._binding, self._limits = binding, limits
        self._sanitize_response, self._run_sync = sanitize_response, run_sync

    def is_available(self):
        return True

    def _request(self, content, *, model=None, temperature=0.7, max_tokens=2048):
        return AIRequest(schema_version=AIRequest.SCHEMA, endpoint_ref=self.name,
            model_ref=model or self.model, output_token_limit=max_tokens, temperature=float(temperature),
            content=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                media_type=MediaType.JSON, text=None, tree=FrozenJSON(content), binary=None, limits=self._limits))

    def _response(self, result):
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        # CTF answers and internal prompts are business rules, applied after the DTO.
        content = self._sanitize_response(result.content.text)
        return ChatResponse(content=content, provider=result.endpoint_ref, model=result.model_ref,
            usage={'prompt_tokens': result.input_tokens, 'completion_tokens': result.output_tokens})

    async def chat(self, messages, **kwargs):
        request = self._request({'messages': [{'role': m.role, 'content': str(m.content)} for m in messages]}, **kwargs)
        result = await self._run_sync(self._port.chat, request, self._context(Outlet.MODEL), self._binding)
        return self._response(result)

    async def chat_tools(self, messages, *, tools, **kwargs):
        """Explicit non-streaming JSON message protocol; the result remains an AIResponse."""
        request = self._request({'messages': messages, 'tools': tools}, **kwargs)
        result = await self._run_sync(self._port.chat, request, self._context(Outlet.MODEL), self._binding)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        if result.content.kind is not PayloadKind.JSON:
            raise RuntimeError('INVALID_VALUE')
        message = result.content.tree.to_value()
        if message['content'] is not None:
            message['content'] = self._sanitize_response(message['content'])
        return replace(result, content=replace(result.content, tree=FrozenJSON(message)))

    async def chat_stream(self, messages, **kwargs):
        request = self._request({'messages': [{'role': m.role, 'content': str(m.content)} for m in messages]}, **kwargs)
        results = await self._run_sync(lambda: list(self._port.stream(
            request, self._context(Outlet.MODEL), self._binding)))
        # Business prompt/answer rules also run on the complete result, not fragments.
        for item in results:
            if type(item) is ProtectionError:
                raise RuntimeError(item.code.value)
        content = self._sanitize_response(''.join(item.content.text for item in results))
        for start in range(0, len(content), 512):
            yield content[start:start + 512]

    def embed(self, texts, *, model, dimensions=None):
        content = {'input': list(texts)}
        if dimensions is not None:
            content['dimensions'] = dimensions
        request = self._request(content, model=model)
        result = self._port.embed(request, self._context(Outlet.EMBEDDING), self._binding)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return result


class ProviderRegistry:
    AGENT_PROVIDER_MAP = {
        'xiaohei': 'volcano', 'analyst': 'deepseek', 'architect': 'wenxin',
        'developer': 'volcano', 'security': 'qwen', 'tester': 'spark',
        'tutor': 'volcano', 'curriculum': 'volcano', 'content_gen': 'volcano',
        'code_mentor': 'volcano', 'assessor': 'volcano',
        'compliance_officer': 'qwen', 'legal_reviewer': 'deepseek',
    }

    @classmethod
    def get_provider_for_agent(cls, agent_id):
        return cls.AGENT_PROVIDER_MAP.get(agent_id, 'deepseek')

    @classmethod
    def set_agent_provider_map(cls, mapping):
        cls.AGENT_PROVIDER_MAP.update(mapping)


class MultiProviderManager:
    def __init__(self, handles=()):
        self._instances = {handle.name: handle for handle in handles}

    def refresh(self):
        # Reconfiguration is a startup operation; never rediscover dotenv/secrets.
        return None

    def get_provider(self, name):
        return self._instances.get(name)

    def get_provider_for_agent(self, agent_id):
        return self.get_provider(ProviderRegistry.get_provider_for_agent(agent_id))

    async def chat_single(self, agent_id, messages, **kwargs):
        provider = self.get_provider_for_agent(agent_id)
        return await provider.chat(messages, **kwargs) if provider else None

    async def chat_collaborative(self, agent_ids, messages, **kwargs):
        results = await asyncio.gather(*(self.chat_single(agent, messages, **kwargs)
                                        for agent in agent_ids), return_exceptions=True)
        return [result for result in results if type(result) is ChatResponse]

    async def chat_sequential(self, agent_ids, initial_messages, **kwargs):
        messages, responses = list(initial_messages), []
        for agent in agent_ids:
            provider = self.get_provider_for_agent(agent)
            if not provider:
                continue
            try:
                response = await provider.chat(messages, **kwargs)
            except RuntimeError:
                continue
            responses.append(response)
            messages.append(Message(role='assistant', content=response.content))
            messages.append(Message(role='system', content='Continue using the preceding answer.'))
        return responses

    async def chat_competitive(self, agent_ids, messages, **kwargs):
        responses = await self.chat_collaborative(agent_ids, messages, **kwargs)
        if not responses:
            raise RuntimeError('PROVIDER_UNAVAILABLE')
        return max(responses, key=lambda response: len(response.content))


_manager = MultiProviderManager()


def bind_manager(manager):
    global _manager
    _manager = manager


def get_manager():
    return _manager


def reset_manager():
    bind_manager(MultiProviderManager())
