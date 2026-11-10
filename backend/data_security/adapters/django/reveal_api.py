"""Thin original-request mapping; never accept client roles, approvals or grants."""
from typing import Callable

from django.urls import path
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from data_security.contracts import (
    BoundedPayload, ContractViolation, Environment, FrozenJSON, MediaType, Outlet, PayloadKind,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, RevealField, RevealRequestRecord, Role,
)
from data_security.contracts.schema import count, reference, require

_binding = None
_source_reader: Callable[[ProtectionContext, int, tuple[tuple[RevealField, str], ...], int | None],
                         FrozenJSON | ProtectionError] | None = None


def bind_reveal_api(*, factory=None, clock=None, identifier=None, limits=None, source_reader=None):
    global _binding, _source_reader
    _binding = (factory, clock, identifier, limits) if factory is not None else None
    _source_reader = source_reader if factory is not None else None


def _metadata(record):
    return {
        'id': record.request_ref, 'requested_by': record.subject_ref, 'course_id': record.course_id,
        'object_ref': record.object_ref, 'object_version': record.object_version,
        'fields': [[category.value, reference] for category, reference in record.fields],
        'purpose': record.purpose_ref.removeprefix('purpose/'), 'reason': record.reason.text,
        'requested_at': record.requested_at.isoformat(), 'state': record.state,
        'decided_by': record.decided_by,
        'decided_at': record.decided_at.isoformat() if record.decided_at is not None else None,
        'expires_at': record.grant.expires_at.isoformat() if record.grant is not None else None,
    }


class RevealAPI(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['Pragma'] = 'no-cache'
        return response

    def context(self, request, *, object_ref='reveal-requests', object_version='v1',
                scope_refs=('reveal-requests',)):
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='user/' + str(request.user.pk), role=Role(request.user.role),
            authorization_ref='authorization/reveal-request-' + _binding[2](),
            scope_refs=scope_refs, environment=Environment.EVALUATION, domain='ctf', outlet=Outlet.API,
            purpose=Purpose.INVESTIGATION, object_ref=object_ref, object_version=object_version,
            source_ref=None, source_version=None, source_hash=None, trace_id='trace/' + _binding[2]())

    def reply(self, result, *, status=200):
        if isinstance(result, ProtectionError):
            code = result.code
            if code in (ReasonCode.AUTHORIZATION_DENIED, ReasonCode.AUTHORIZATION_EXPIRED):
                status = 403
            elif code is ReasonCode.UNSUPPORTED_SCOPE:
                status = 400
            else:
                status = 503
            return Response({'code': code.value}, status=status)
        if isinstance(result, RevealRequestRecord):
            return Response(_metadata(result), status=status)
        return Response({'originals': result.tree.to_value()}, status=status)


class RevealSourceView(RevealAPI):
    parser_classes = ()

    def get(self, request):
        if _binding is None or _source_reader is None:
            return Response({'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'}, status=503)
        try:
            query = request.query_params
            required = {'source_id', 'field', 'field_ref'}
            require(not set(query) - required - {'course_id'}, ReasonCode.UNKNOWN_FIELD)
            require(required <= set(query), ReasonCode.MISSING_FIELD)
            require(all(len(query.getlist(name)) == 1 for name in query))
            source_id = int(query['source_id'])
            count(source_id, 2**63 - 1)
            require(source_id > 0)
            fields = ((RevealField(query['field']), query['field_ref']),)
            reference(query['field_ref'])
            course_id = int(query['course_id']) if 'course_id' in query else None
            if course_id is not None:
                count(course_id)
                require(course_id > 0)
            context = self.context(request, object_ref='reveal-source/' + str(source_id),
                                   scope_refs=(query['field_ref'],))
        except ContractViolation as error:
            return Response({'code': error.code.value}, status=400)
        except ValueError:
            return Response({'code': 'INVALID_TYPE'}, status=400)
        result = _source_reader(context, source_id, fields, course_id)
        return self.reply(result) if isinstance(result, ProtectionError) else Response(result.to_value())


class RevealRequestsView(RevealAPI):
    def get(self, request):
        if _binding is None:
            return Response({'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'}, status=503)
        try:
            require(not set(request.query_params) - {'offset', 'limit'}, ReasonCode.UNKNOWN_FIELD)
            offset, limit = int(request.query_params.get('offset', '0')), int(request.query_params.get('limit', '50'))
            count(offset)
            count(limit, 100)
            require(limit > 0)
            result = _binding[0]().list_requests(self.context(request), offset=offset, limit=limit)
            if isinstance(result, ProtectionError):
                return self.reply(result)
            return Response({'items': [_metadata(record) for record in result],
                             'offset': offset, 'limit': limit, 'state': 'enabled-unverified'})
        except ContractViolation as error:
            return Response({'code': error.code.value}, status=400)
        except (ValueError, TypeError):
            return Response({'code': 'INVALID_TYPE'}, status=400)

    def post(self, request):
        if _binding is None:
            return Response({'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'}, status=503)
        try:
            data = request.data
            require(type(data) is dict, ReasonCode.INVALID_TYPE)
            required = {'object_ref', 'object_version', 'fields', 'purpose', 'reason'}
            require(not set(data) - required - {'course_id'}, ReasonCode.UNKNOWN_FIELD)
            require(required <= set(data), ReasonCode.MISSING_FIELD)
            require(type(data['fields']) is list, ReasonCode.INVALID_TYPE)
            fields = tuple((RevealField(category), reference) for category, reference in data['fields'])
            context = self.context(request, object_ref=data['object_ref'], object_version=data['object_version'],
                                   scope_refs=tuple(reference for category, reference in fields))
            record = RevealRequestRecord(schema_version=RevealRequestRecord.SCHEMA,
                request_ref='reveal-request-' + _binding[2](), subject_ref=context.actor_ref,
                course_id=data.get('course_id'), object_ref=data['object_ref'], object_version=data['object_version'],
                fields=fields, purpose_ref='purpose/' + data['purpose'], requested_at=_binding[1](),
                reason=BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
                    media_type=MediaType.TEXT, text=data['reason'], tree=None, binary=None, limits=_binding[3]),
                state='pending', grant=None, decided_by=None, decided_at=None, decision_event_ref=None)
            return self.reply(_binding[0]().request(record, context), status=201)
        except ContractViolation as error:
            return Response({'code': error.code.value}, status=400)
        except (ValueError, TypeError, KeyError):
            return Response({'code': 'INVALID_TYPE'}, status=400)


class RevealDecisionView(RevealAPI):
    action = None

    def post(self, request, request_ref):
        if _binding is None:
            return Response({'code': 'POLICY_NOT_APPROVED', 'state': 'disabled'}, status=503)
        try:
            reference(request_ref)
            require(type(request.data) is dict and not request.data, ReasonCode.UNKNOWN_FIELD)
            flow, context = _binding[0](), self.context(request, object_ref=request_ref)
            if self.action == 'read':
                result = flow.reveal_request(request_ref, context)
            elif self.action == 'revoke':
                result = flow.revoke(request_ref, context)
            else:
                result = flow.decide(request_ref, context, approved=self.action == 'approve')
            return self.reply(result)
        except ContractViolation as error:
            return Response({'code': error.code.value}, status=400)
        except (ValueError, TypeError):
            return Response({'code': 'INVALID_TYPE'}, status=400)


urlpatterns = [path('reveal-requests/', RevealRequestsView.as_view(), name='security-reveal-requests'),
               path('reveal-source/', RevealSourceView.as_view(), name='security-reveal-source')]
urlpatterns += [path('reveal-requests/<str:request_ref>/' + action + '/',
                     RevealDecisionView.as_view(action=action), name='security-reveal-' + action)
                for action in ('approve', 'reject', 'revoke', 'read')]
