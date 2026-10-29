"""Run one registered comparison in the dedicated disk-backed scratch database."""
import json
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from evaluation_center import evaluations, live_evaluations, live_fixtures
from evaluation_center.models import NonFormalAccount
from feedback_center import constants
from feedback_center.models import FeedbackIssueGroup
from feedback_center.services import candidates


class Command(BaseCommand):
    help = 'Run a bounded real gateway comparison on registered synthetic cases; never publishes a candidate.'

    def add_arguments(self, parser):
        parser.add_argument('--factor', choices=live_fixtures.FACTORS, default='prompt_version')
        parser.add_argument('--max-duration-ms', type=int, default=900000)

    def handle(self, *args, **options):
        db_path = Path(str(connection.settings_dict['NAME'])).resolve()
        if (getattr(settings, 'SETTINGS_MODULE', '') != 'evaluation_center.scratch_settings' or
                getattr(settings, 'EVALUATION_SCRATCH', False) is not True or
                connection.vendor != 'sqlite' or db_path.parent.parent != Path('/tmp') or
                not db_path.parent.name.startswith('m8-scratch-') or
                getattr(settings, 'FEEDBACK_PHASE3_RELEASE_ENABLED', True)):
            raise CommandError('真实批次命令只允许独立scratch数据库且禁止发布。')
        live_evaluations.require_live()
        users = get_user_model()
        if users.objects.exclude(pk__in=NonFormalAccount.objects.filter(source='offline').values('student_id')).exists():
            raise CommandError('scratch库中存在非offline账号，拒绝执行。')
        suffix = uuid.uuid4().hex[:12]
        actor = users.objects.create_user(username='m8-offline-live-' + suffix, role='admin', password=None)
        NonFormalAccount.objects.create(student=actor, source='offline')
        now = timezone.now()
        # An explicitly labelled fixture, not a real teacher's feedback or signoff.
        group = FeedbackIssueGroup.objects.create(
            title='SCRATCH synthetic classifier comparison ' + suffix,
            category=constants.CATEGORY_TEACHING, issue_type='synthetic_prompt_comparison',
            window_start=now - timedelta(seconds=1), window_end=now + timedelta(hours=1),
            status=constants.ISSUE_GROUP_CONFIRMED, counts={'missing_evidence': 0},
            reviewed_by=actor, reviewed_at=now, created_by=actor,
            notes='Independent scratch fixture only; not real course/material signoff.')
        baseline, candidate_config = live_fixtures.configurations(options['factor'])
        candidate = candidates.create_candidate(
            actor=actor, title='SCRATCH live comparison ' + suffix, issue_group_ids=[group.group_id],
            baseline_config_version='m8-live-baseline/1', candidate_config_version='m8-live-candidate/2',
            single_changed_factor=options['factor'], target_task_versions=live_fixtures.TASK_SCOPE,
            baseline_config=baseline, candidate_config=candidate_config, rollback_version='m8-live-baseline/1',
            expected_risk='Synthetic classification only; never changes production authorization.')
        candidates.submit_for_evaluation(candidate, actor=actor)
        run = evaluations.create_run(candidate, actor=actor, dataset_version=live_fixtures.DATASET_VERSION,
                                     purpose='Registered live API comparison on minimal synthetic cases',
                                     max_duration_ms=options['max_duration_ms'])
        report = evaluations.execute_run(run, actor=actor)
        reference = evaluations.report_reference(report)
        attachment = {'accepted': False, 'error': None}
        try:
            candidates.attach_report(candidate, actor=actor, report=reference)
            candidates.complete_evaluation(candidate, actor=actor)
            attachment['accepted'] = True
        except candidates.CandidateError as exc:
            attachment['error'] = exc.code
        candidate.refresh_from_db()
        payload = report.payload
        summary = {
            'database': str(db_path), 'reference': reference, 'candidate_id': str(candidate.candidate_id),
            'configuration_snapshots': payload['configuration_snapshots'],
            'dataset_version': payload['dataset_version'], 'mode': payload['mode'],
            'simulated': payload['simulated'], 'input_source': payload['input_source'],
            'expected_cases': payload['expected_cases'], 'completed_cases': payload['completed_cases'],
            'stop_reason': payload['stop_reason'], 'provider_calls': payload['provider_calls'],
            'successful_provider_calls': payload['successful_provider_calls'],
            'arm_metrics': payload['arm_metrics'], 'usage_by_arm': payload['usage_by_arm'],
            'tokens': payload['tokens'], 'cost': payload['cost'], 'repeat_count': payload['repeat_count'],
            'module7_attachment': attachment, 'candidate_state': candidate.state,
            'module7_events': list(candidate.events.values_list('action', flat=True)),
            'published': False,
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        if not attachment['accepted'] or not payload['successful_provider_calls']:
            raise CommandError('真实批次证据不足；持久报告已保留，未伪造成功或审批。')
