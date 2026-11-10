"""Explicit runtime tool dispatch; model arguments carry references, never authority."""
import re

from data_security.contracts import (
    AuditReceipt, CanaryCheckPort, CanarySeed, ContractViolation, Environment,
    ProtectionContext, ProtectionError, ReasonCode,
)
from data_security.contracts.schema import reference, require


class CanaryToolRegistry:
    """The owner resolves current authority and loads the exact referenced output.

    resolve_context(name, reference, user) must authorize that user for the current
    operation and object version. load_output(reference, context) must return the
    corresponding decoded output, not caller text or an arbitrary filesystem path.
    Plant persistence and current authorization remain owned by the injected tools.
    """
    def __init__(self, *, plant, checker: CanaryCheckPort, resolve_context, load_output):
        self.plant, self.checker = plant, checker
        self.resolve_context, self.load_output = resolve_context, load_output

    def definitions(self):
        return [
            {'name': 'canary.plant',
             'description': '在已授权的合成目标中埋入已登记蜜标，不接受原文或授权参数。',
             'input_schema': {'type': 'object', 'additionalProperties': False,
                 'properties': {'seed_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'}},
                 'required': ['seed_id']}},
            {'name': 'canary.check',
             'description': '检查已授权产物的实际出口内容，只返回告警数量，不返回正文。',
             'input_schema': {'type': 'object', 'additionalProperties': False,
                 'properties': {'artifact_ref': {'type': 'string', 'minLength': 1, 'maxLength': 160}},
                 'required': ['artifact_ref']}},
        ]

    def model_definitions(self):
        """OpenAI-compatible function names cannot contain the registry's dot."""
        return [{'type': 'function', 'function': {
            'name': item['name'].replace('.', '_'), 'description': item['description'],
            'parameters': item['input_schema']}} for item in self.definitions()]

    def run_model_tool(self, name, *, arguments, user):
        names = {'canary_plant': 'canary.plant', 'canary_check': 'canary.check'}
        if type(name) is not str or name not in names:
            return {'status': 'error', 'code': 'UNSUPPORTED_SCOPE'}
        return self.run(names[name], arguments=arguments, user=user)

    def run(self, name, *, arguments, user):
        try:
            require(type(name) is str and name in ('canary.plant', 'canary.check'),
                    ReasonCode.UNSUPPORTED_SCOPE)
            require(user is not None and user.is_authenticated and user.is_active,
                    ReasonCode.AUTHORIZATION_DENIED)
            field = 'seed_id' if name == 'canary.plant' else 'artifact_ref'
            require(type(arguments) is dict and set(arguments) == {field}, ReasonCode.INVALID_TYPE)
            ref = arguments[field]
            if name == 'canary.plant':
                require(type(ref) is str and re.fullmatch(r'[0-9a-f]{32}', ref) is not None)
            else:
                reference(ref)
            context = self.resolve_context(name, ref, user)
            if type(context) is ProtectionError:
                return {'status': 'error', 'code': context.code.value}
            require(type(context) is ProtectionContext and context.environment in
                    (Environment.TEST, Environment.EVALUATION), ReasonCode.AUTHORIZATION_DENIED)
            if name == 'canary.plant':
                result = self.plant(seed_id=ref, context=context)
                if type(result) is ProtectionError:
                    return {'status': 'error', 'code': result.code.value}
                require(type(result) is CanarySeed and result.seed_id == ref,
                        ReasonCode.SOURCE_NOT_APPROVED)
                return {'status': 'planted', 'seed_id': ref}
            payload = self.load_output(ref, context)
            if type(payload) is ProtectionError:
                return {'status': 'error', 'code': payload.code.value}
            result = self.checker.check(payload=payload, context=context)
            if type(result) is ProtectionError:
                return {'status': 'error', 'code': result.code.value}
            require(type(result) is tuple and all(type(item) is AuditReceipt for item in result),
                    ReasonCode.AUDIT_UNAVAILABLE)
            return {'status': 'alert' if result else 'clean', 'alert_count': len(result)}
        except ContractViolation as error:
            return {'status': 'error', 'code': error.code.value}
        except Exception:
            # Tool results must not expose a body-bearing owner/adapter exception.
            return {'status': 'error', 'code': 'CANARY_TOOL_FAILED'}
