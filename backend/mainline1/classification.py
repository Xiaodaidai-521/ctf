"""Versioned, private configuration and context. No public API or policy activation."""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .parsing import InputError, fingerprint

IMPLEMENTATIONS = frozenset({'email_ascii_v1', 'ipv4_v1', 'luhn_candidate_v1'})


def require(condition, code='CONFIG_INVALID'):
    if not condition:
        raise InputError(code)


def canonical(value):
    fingerprint(value)  # Reject floats and unsupported types; no implicit coercion.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def identifier(value):
    try:
        require(isinstance(value, str) and str(UUID(value)) == value)
    except (ValueError, TypeError, AttributeError):
        raise InputError('CONFIG_INVALID') from None


def validate_meta(meta):
    require(set(meta) == {'schema_version', 'trace_id', 'environment', 'evaluation_run_id', 'domain_id', 'created_at'})
    require(meta['schema_version'] == 'mainline1.proposed.v1')
    require(meta['environment'] in ('development', 'test', 'production'))
    require(isinstance(meta['domain_id'], str) and bool(meta['domain_id']))
    identifier(meta['trace_id'])
    if meta['evaluation_run_id'] is not None:
        identifier(meta['evaluation_run_id'])
    try:
        require(datetime.fromisoformat(meta['created_at'].replace('Z', '+00:00')).utcoffset() is not None)
    except (ValueError, TypeError, AttributeError):
        raise InputError('CONFIG_INVALID') from None


def unique(items, key=None):
    values = [item[key] if key else item for item in items]
    require(len(values) == len(set(values)), 'DUPLICATE_ID')
    return set(values)


@dataclass(frozen=True)
class RuleConfiguration:
    payload: str = field(repr=False)

    @classmethod
    def load(cls, value):
        try:
            require(set(value) == {'baseline_version', 'allowed_environments', 'policy', 'rules'})
            policy, rules = value['policy'], value['rules']
            require(set(policy) == {'meta', 'policy_id', 'version', 'dictionary_version', 'ruleset_version',
                    'state', 'effective_at', 'levels', 'categories', 'rule_refs', 'conflict_strategy',
                    'review_policy_version', 'content_hash'})
            validate_meta(policy['meta'])
            identifier(policy['policy_id'])
            require(policy['state'] == 'draft' and policy['effective_at'] is None)
            require(value['allowed_environments'] and set(value['allowed_environments']) <= {'test', 'development'})
            require(policy['conflict_strategy'] == 'review_no_downgrade')
            for key in ('baseline_version',):
                require(isinstance(value[key], str) and bool(value[key]))
            for key in ('version', 'dictionary_version', 'ruleset_version', 'review_policy_version'):
                require(isinstance(policy[key], str) and bool(policy[key]))
            levels = unique(policy['levels'])
            require(levels and all(isinstance(level, str) and level for level in levels))
            category_ids = unique(policy['categories'], 'category_id')
            rule_ids = unique(rules, 'rule_id')
            require(category_ids and rule_ids)
            require(not category_ids & {'unknown', 'pending', 'pending_review', 'no_match'})
            unique(policy['rule_refs'])
            require(set(policy['rule_refs']) == rule_ids, 'RULE_REFERENCE_INVALID')
            categories = {c['category_id']: c for c in policy['categories']}
            for category in categories.values():
                require(isinstance(category['category_id'], str) and bool(category['category_id']))
                require(set(category) == {'category_id', 'definition', 'aliases', 'positive_examples',
                    'negative_examples', 'rule_refs', 'related_categories', 'protection_level', 'review_conditions'})
                require(isinstance(category['definition'], str) and bool(category['definition']))
                require(category['protection_level'] in levels, 'POLICY_CONFLICT')
                for key in ('aliases', 'positive_examples', 'negative_examples', 'rule_refs', 'related_categories', 'review_conditions'):
                    require(isinstance(category[key], list) and all(isinstance(x, str) and x for x in category[key]))
                    unique(category[key])
                require(category['rule_refs'] and category['review_conditions'])
                require(set(category['related_categories']) <= category_ids, 'CATEGORY_REFERENCE_INVALID')
                require(set(category['rule_refs']) <= rule_ids, 'RULE_REFERENCE_INVALID')
            for rule in rules:
                require(set(rule) == {'rule_id', 'version', 'implementation', 'category_id', 'enabled'})
                require(isinstance(rule['rule_id'], str) and bool(rule['rule_id']))
                require(isinstance(rule['version'], str) and bool(rule['version']))
                require(type(rule['enabled']) is bool)
                require(rule['implementation'] in IMPLEMENTATIONS, 'RULE_IMPLEMENTATION_UNSUPPORTED')
                require(rule['category_id'] in category_ids, 'CATEGORY_REFERENCE_INVALID')
            for category in categories.values():
                actual = {r['rule_id'] for r in rules if r['category_id'] == category['category_id']}
                require(actual == set(category['rule_refs']), 'RULE_REFERENCE_INVALID')
            require(policy['content_hash'] == fingerprint({k: v for k, v in policy.items() if k != 'content_hash'}), 'CONFIG_HASH_MISMATCH')
            return cls(canonical(value))
        except InputError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError):
            raise InputError('CONFIG_INVALID') from None

    def data(self):
        return json.loads(self.payload)


def load_baseline():
    return RuleConfiguration.load(json.loads((Path(__file__).parent / 'config/rule-baseline-v1.json').read_text(encoding='utf-8')))


@dataclass(frozen=True)
class BusinessContext:
    payload: str = field(repr=False)

    @classmethod
    def create(cls, *, meta, context_id, version, asset_version_id, scope_hash,
               scenario='', purpose='', table_description='', field_descriptions=(),
               source='user_input', confirmation='unconfirmed', confirmation_receipt=None,
               supersedes_context_id=None):
        """Trusted internal caller only. Receipt is supplied by the owner, never client JSON.

        There is no confirmation endpoint here. Model-inferred facts cannot self-confirm.
        """
        validate_meta(meta)
        identifier(context_id)
        identifier(asset_version_id)
        if supersedes_context_id is not None:
            identifier(supersedes_context_id)
        require(type(version) is int and version > 0, 'CONTEXT_INVALID')
        require(isinstance(scope_hash, str) and len(scope_hash) == 71 and scope_hash.startswith('sha256:'), 'CONTEXT_INVALID')
        require(source in ('admin_config', 'confirmed_dictionary', 'user_input', 'model_inferred'), 'CONTEXT_INVALID')
        require(confirmation in ('unconfirmed', 'confirmed', 'conflicted'), 'CONTEXT_INVALID')
        for value in (scenario, purpose, table_description):
            require(isinstance(value, str) and len(value) <= 8192, 'CONTEXT_INVALID')
        require(len(field_descriptions) <= 1024, 'CONTEXT_INVALID')
        seen = set()
        for item in field_descriptions:
            require(set(item) == {'sheet_id', 'column', 'description'}, 'CONTEXT_INVALID')
            require(isinstance(item['sheet_id'], str) and item['sheet_id'] and type(item['column']) is int and item['column'] > 0, 'CONTEXT_INVALID')
            require(isinstance(item['description'], str) and len(item['description']) <= 8192, 'CONTEXT_INVALID')
            key = (item['sheet_id'], item['column'])
            require(key not in seen, 'CONTEXT_INVALID')
            seen.add(key)
        actor, timestamp = None, None
        if confirmation == 'confirmed':
            require(source != 'model_inferred' and isinstance(confirmation_receipt, ConfirmationReceipt), 'CONTEXT_NOT_CONFIRMED')
            actor, timestamp = confirmation_receipt.actor, confirmation_receipt.at
            require(type(actor) is int and actor > 0, 'CONTEXT_INVALID')
            try:
                require(datetime.fromisoformat(timestamp.replace('Z', '+00:00')).utcoffset() is not None, 'CONTEXT_INVALID')
            except (ValueError, TypeError, AttributeError):
                raise InputError('CONTEXT_INVALID') from None
        else:
            require(confirmation_receipt is None, 'CONTEXT_INVALID')
        value = dict(meta=meta, context_id=context_id, version=version, asset_version_id=asset_version_id,
                     scope_hash=scope_hash, scenario=scenario, purpose=purpose, table_description=table_description,
                     field_descriptions=list(field_descriptions), source=source, confirmation=confirmation,
                     confirmed_by=actor, confirmed_at=timestamp, supersedes_context_id=supersedes_context_id)
        return cls(canonical(dict(value, content_hash=fingerprint(value))))

    def data(self):
        return json.loads(self.payload)


@dataclass(frozen=True)
class ConfirmationReceipt:
    """Internal trusted-owner proof of confirmation, not an authorization mechanism."""
    actor: int
    at: str
