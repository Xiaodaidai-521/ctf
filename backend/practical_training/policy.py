import json
import os
from ipaddress import ip_address

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError


AUP_VERSION = 'm5-aup-v1'
AUP = ('仅在授权时段操作本次分配目标及端口；禁止扫描、访问其他学生环境、宿主控制面、'
       '校园/企业内网、生产系统及任意互联网目标；禁止真实数据窃取、钓鱼、破坏服务。')
REQUIRED_CHECKS = (
    'student_identity_isolation', 'cross_student_denied', 'host_control_denied',
    'private_network_denied', 'production_denied', 'internet_egress_denied',
    'resource_limits', 'expired_credentials_denied',
)
DEFAULT_POLICY = {
    'version': 'm5-isolation-v1', 'egress': 'deny', 'allowed_egress': [],
    'deny_other_students': True, 'deny_host_control': True,
    'deny_private_networks': True, 'deny_production': True,
    'cpu_millis': 1000, 'memory_mib': 768, 'pids': 256,
    'duration_seconds': 3600, 'max_active_per_student': 1,
}


def configured_policy():
    try:
        overrides = getattr(settings, 'PRACTICAL_TRAINING_POLICY', None)
        if overrides is None:
            overrides = json.loads(os.environ.get('PRACTICAL_TRAINING_POLICY_JSON', '{}'))
        if not isinstance(overrides, dict) or set(overrides) - set(DEFAULT_POLICY):
            raise ValueError('unknown policy fields')
    except (ValueError, TypeError) as exc:
        raise ValidationError('实训策略配置无效。') from exc
    policy = {**DEFAULT_POLICY, **overrides}
    for key in ('deny_other_students', 'deny_host_control', 'deny_private_networks', 'deny_production'):
        if policy.get(key) is not True:
            raise ValidationError('禁止放宽默认隔离策略。')
    if policy.get('egress') != 'deny' or policy.get('allowed_egress') != []:
        raise ValidationError('首期只允许默认拒绝外连。')
    for key, upper in (('cpu_millis', 1000), ('memory_mib', 768), ('pids', 256),
                       ('duration_seconds', 7200), ('max_active_per_student', 2)):
        value = policy.get(key)
        if type(value) is not int or not 1 <= value <= upper:
            raise ValidationError(f'资源限制无效：{key}')
    return policy


def environment_binding(container):
    from skill_review.services.submissions import payload_hash
    return payload_hash({
        'container_id': container.container_id, 'name': container.docker_container_name,
        'user_id': container.user_id, 'challenge_id': container.challenge_id,
        'image': container.challenge.docker_image, 'port': container.port,
        'access_url': container.access_url, 'runtime_metadata': container.runtime_metadata,
        'started_at': container.started_at.isoformat() if container.started_at else None,
        'verifier_ip': getattr(settings, 'PRACTICAL_TRAINING_VERIFIER_IP', os.environ.get('PRACTICAL_TRAINING_VERIFIER_IP', '127.0.0.1')),
    })


def validate_resource_limits(limits, policy):
    if not isinstance(limits, dict):
        raise ValidationError('缺少实例资源上限登记。')
    for key in ('cpu_millis', 'memory_mib', 'pids'):
        value = limits.get(key)
        if type(value) is not int or not 1 <= value <= policy[key]:
            raise ValidationError(f'实例资源上限未满足任务策略：{key}')


def approved_endpoint(container):
    if not getattr(settings, 'PRACTICAL_TRAINING_ENABLED', os.environ.get('PRACTICAL_TRAINING_ENABLED', '').lower() == 'true'):
        raise ValidationError('真实靶场未放行：须先完成部署隔离验收。')
    if (not container.is_running or container.runtime_metadata.get('profile') != 'juice-shop'
            or container.challenge.docker_image != settings.JUICE_SHOP_IMAGE):
        raise ValidationError('没有可用的已登记 Juice Shop 环境。')
    approval = getattr(container, 'environmentapproval', None)
    if (not approval or approval.revoked or approval.expires_at <= timezone.now()
            or not approval.evidence_ref
            or any(approval.checks.get(key) is not True for key in REQUIRED_CHECKS)):
        raise ValidationError('该实例缺少有效的隔离验收登记。')
    if approval.checks.get('binding') != environment_binding(container):
        raise ValidationError('实例来源已变化，原验收登记无效。')
    validate_resource_limits(approval.checks.get('limits'), configured_policy())
    if not container.expires_at or not container.started_at:
        raise ValidationError('实例须有服务端起止时间。')
    # No student URLs, DNS resolution, redirects or proxy-environment overrides.
    host = getattr(settings, 'PRACTICAL_TRAINING_VERIFIER_IP', os.environ.get('PRACTICAL_TRAINING_VERIFIER_IP', '127.0.0.1'))
    try:
        address = ip_address(host)
    except ValueError as exc:
        raise ValidationError('验证器地址必须为部署登记的 IP。') from exc
    if address.is_unspecified or address.is_multicast or address.is_link_local:
        raise ValidationError('不允许该验证器地址。')
    if not settings.JUICE_SHOP_PORT_MIN <= container.port <= settings.JUICE_SHOP_PORT_MAX:
        raise ValidationError('目标端口不在 Juice Shop 专用范围。')
    host = f'[{address}]' if address.version == 6 else str(address)
    return f'http://{host}:{container.port}'
