"""Catalog access, review sign-off and publish gates.

Nothing here fabricates a reviewer or an acceptance result.  A catalog can be
frozen only after every required delivery item is signed off with a real
reviewer, attachment location and time; it can be published only when it is
frozen and every open capability has reviewed evidence and a complete task
package.
"""

from django.db import transaction
from django.utils import timezone

from .. import constants
from ..models import CatalogVersion, DataBasisCard, DeliveryRegisterItem, WSTGMapping


class CatalogUnavailable(Exception):
    code = 'catalog_not_published'

    def __init__(self, detail='目录尚未发布，等待课程审核。'):
        super().__init__(detail)
        self.detail = detail


class PublishBlocked(Exception):
    code = 'publish_blocked'

    def __init__(self, missing):
        self.missing = missing
        super().__init__('目录发布条件未满足。')


def latest_published():
    return CatalogVersion.objects.filter(status=constants.CATALOG_STATUS_PUBLISHED).order_by('-published_at', '-id').first()


def latest_catalog():
    return CatalogVersion.objects.order_by('-created_at', '-id').first()


def get_catalog(version=None, published_only=False, allow_candidate=False):
    if version:
        catalog = CatalogVersion.objects.filter(version=version).first()
        if not catalog:
            raise CatalogUnavailable(f'目录版本 {version} 不存在。')
        if published_only and catalog.status != constants.CATALOG_STATUS_PUBLISHED and not allow_candidate:
            raise CatalogUnavailable(f'目录版本 {version} 尚未发布，等待课程审核。')
        return catalog

    catalog = latest_published()
    if catalog:
        return catalog
    if allow_candidate:
        catalog = latest_catalog()
        if catalog:
            return catalog
    raise CatalogUnavailable()


def readable_catalog(user, version=None):
    """Return the catalog a user may read.

    Students only see a published catalog.  Teachers/admins may inspect a
    candidate for review.  ``LEARNING_MAP_PREVIEW_CANDIDATE`` is an explicit
    development switch, off by default.
    """

    from django.conf import settings

    is_staff_role = bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_teacher', False) or getattr(user, 'is_admin', False) or user.is_superuser)
    )
    allow_candidate = is_staff_role or bool(getattr(settings, 'LEARNING_MAP_PREVIEW_CANDIDATE', False))
    return get_catalog(version=version, published_only=not is_staff_role, allow_candidate=allow_candidate)


def _delivery_missing(catalog):
    missing = []
    for delivery_no, title in constants.REQUIRED_DELIVERY_ITEMS:
        item = DeliveryRegisterItem.objects.filter(delivery_no=delivery_no, catalog=catalog).first()
        if not item:
            missing.append({
                'code': 'delivery_item_missing',
                'delivery_no': delivery_no,
                'detail': f'缺少交付项：{title}',
            })
            continue
        if item.status != constants.DELIVERY_SIGNED_OFF:
            missing.append({
                'code': 'delivery_item_not_signed',
                'delivery_no': delivery_no,
                'detail': f'交付项未签收：{title}（当前 {item.get_status_display()}）',
            })
        elif not (item.author_id and item.reviewer_id and item.attachment_path and item.signed_off_at):
            missing.append({
                'code': 'delivery_item_incomplete_signoff',
                'delivery_no': delivery_no,
                'detail': f'交付项签收记录不完整：{title}',
            })
    return missing


def _open_capability_missing(catalog):
    missing = []
    open_capabilities = catalog.capabilities.filter(status=constants.CAPABILITY_STATUS_OPEN)
    for capability in open_capabilities.prefetch_related('tasks', 'wstg_mappings', 'basis_cards'):
        frozen_tasks = [
            task for task in capability.tasks.all()
            if task.catalog_id == catalog.id
            and task.status == constants.TASK_STATUS_FROZEN
            and not task.requires_milestone_i
        ]
        if not frozen_tasks:
            missing.append({
                'code': 'open_capability_without_task',
                'capability_id': capability.stable_id,
                'detail': f'{capability.stable_id} 已开放但没有已冻结任务。',
            })
        else:
            complete = [
                task for task in frozen_tasks
                if task.has_required_parts
                and task.student_solution_ref
                and (task.retest_task_keys or any(
                    t.purpose == constants.PURPOSE_RETEST
                    and t.status == constants.TASK_STATUS_FROZEN
                    and t.catalog_id == catalog.id
                    for t in capability.tasks.all()
                ))
            ]
            if not complete:
                missing.append({
                    'code': 'task_package_incomplete',
                    'capability_id': capability.stable_id,
                    'detail': f'{capability.stable_id} 的任务缺少材料、四级提示、解析、验证器、验收或复测题池。',
                })

        if capability.track == constants.TRACK_NETWORK:
            reviewed = capability.wstg_mappings.filter(
                catalog=catalog,
                status='reviewed',
                reviewer__isnull=False,
                reviewed_at__isnull=False,
            ).exists()
            if not reviewed:
                missing.append({
                    'code': 'wstg_not_reviewed',
                    'capability_id': capability.stable_id,
                    'detail': f'{capability.stable_id} 缺少已复核的 WSTG 场景转译。',
                })
        else:
            reviewed = capability.basis_cards.filter(
                catalog=catalog,
                status='reviewed',
                verified_date__isnull=False,
                owner__isnull=False,
            ).exists()
            if not reviewed:
                missing.append({
                    'code': 'basis_card_not_reviewed',
                    'capability_id': capability.stable_id,
                    'detail': f'{capability.stable_id} 缺少已复核的数据依据卡。',
                })
    return missing


def _diagnostic_missing(catalog):
    missing = []
    tracks = set(
        catalog.capabilities.filter(status=constants.CAPABILITY_STATUS_OPEN).values_list('track', flat=True)
    )
    for track in sorted(tracks):
        exists = catalog.diagnostic_questions.filter(
            track=track, status='frozen', version__isnull=False,
        ).exists()
        if not exists:
            missing.append({
                'code': 'diagnostic_missing',
                'track': track,
                'detail': f'{track} 主线缺少已冻结诊断题。',
            })
    return missing


def publish_readiness(catalog):
    """Return the exact missing items for freezing/publishing a catalog."""

    missing = []
    missing.extend(_delivery_missing(catalog))
    missing.extend(_open_capability_missing(catalog))
    missing.extend(_diagnostic_missing(catalog))
    missing.extend(_wstg_source_guard(catalog))
    return {
        'ready': not missing,
        'missing': missing,
        'counts': {
            'capabilities': catalog.capabilities.count(),
            'open_capabilities': catalog.capabilities.filter(status=constants.CAPABILITY_STATUS_OPEN).count(),
            'tasks': catalog.tasks.count(),
            'diagnostic_questions': catalog.diagnostic_questions.count(),
            'delivery_items': catalog.delivery_items.count(),
        },
    }


def _wstg_source_guard(catalog):
    """WSTG is a testing guide; every translation must keep the version."""

    missing = []
    for mapping in WSTGMapping.objects.filter(catalog=catalog, status='reviewed'):
        if not mapping.wstg_version or not mapping.scenario_id:
            missing.append({
                'code': 'wstg_version_missing',
                'detail': f'WSTG 转译 {mapping.id} 缺少版本或场景编号。',
            })
    return missing


@transaction.atomic
def freeze_catalog(catalog, actor=None):
    if catalog.status not in (constants.CATALOG_STATUS_CANDIDATE,):
        raise ValueError('只有候选目录可以冻结。')
    readiness = publish_readiness(catalog)
    if not readiness['ready']:
        raise PublishBlocked(readiness['missing'])
    catalog.status = constants.CATALOG_STATUS_FROZEN
    catalog.frozen_at = timezone.now()
    catalog.review_record = {
        **(catalog.review_record or {}),
        'frozen_by': getattr(actor, 'id', None),
        'frozen_at': catalog.frozen_at.isoformat(),
        'delivery_items': [no for no, _ in constants.REQUIRED_DELIVERY_ITEMS],
    }
    catalog.save(update_fields=['status', 'frozen_at', 'review_record', 'updated_at'])
    return catalog


@transaction.atomic
def publish_catalog(catalog, actor=None):
    if catalog.status != constants.CATALOG_STATUS_FROZEN:
        raise ValueError('目录必须先冻结才能发布。')
    readiness = publish_readiness(catalog)
    if not readiness['ready']:
        raise PublishBlocked(readiness['missing'])

    previous = CatalogVersion.objects.filter(status=constants.CATALOG_STATUS_PUBLISHED).exclude(pk=catalog.pk)
    now = timezone.now()
    for old in previous:
        old.status = constants.CATALOG_STATUS_DEPRECATED
        old.deprecated_at = now
        old.save(update_fields=['status', 'deprecated_at', 'updated_at'])

    catalog.status = constants.CATALOG_STATUS_PUBLISHED
    catalog.published_at = now
    catalog.review_record = {
        **(catalog.review_record or {}),
        'published_by': getattr(actor, 'id', None),
        'published_at': now.isoformat(),
    }
    catalog.save(update_fields=['status', 'published_at', 'review_record', 'updated_at'])
    return catalog


def catalog_version_payload(catalog):
    return {
        'version': catalog.version,
        'label': catalog.label,
        'status': catalog.status,
        'status_label': catalog.get_status_display(),
        'rule_version': catalog.rule_version,
        'created_at': catalog.created_at.isoformat() if catalog.created_at else None,
        'frozen_at': catalog.frozen_at.isoformat() if catalog.frozen_at else None,
        'published_at': catalog.published_at.isoformat() if catalog.published_at else None,
        'deprecated_at': catalog.deprecated_at.isoformat() if catalog.deprecated_at else None,
    }
