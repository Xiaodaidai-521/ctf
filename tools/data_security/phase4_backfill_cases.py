"""Explicit real-backup/backfill acceptance; dedicated disposable synthetic database."""
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg2
from psycopg2 import sql


class FieldBackfillAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('DS_PHASE4_BACKFILL_RUN') != '1':
            raise RuntimeError('EXPLICIT_ISOLATED_BACKFILL_ACCEPTANCE_REQUIRED')
        cls.root = Path(__file__).resolve().parents[2]
        cluster = json.loads((cls.root / '.state/postgres.json').read_text())
        if not cluster['synthetic_only'] or cluster['socket'] != str(cls.root / '.state/pg-run'):
            raise RuntimeError('DEDICATED_SYNTHETIC_CLUSTER_REQUIRED')
        cls.database = dict(host='127.0.0.1', port=cluster['port'], user=cluster['user'],
                            dbname='postgres', sslmode='disable')
        cls.source = 'phase4_fields_src_' + uuid4().hex[:12]
        cls.target = 'phase4_fields_dst_' + uuid4().hex[:12]
        with closing(psycopg2.connect(**cls.database)) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                for name in (cls.source, cls.target):
                    cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        cls.addClassCleanup(cls.clean_databases)
        os.environ.update(DB_HOST='127.0.0.1', DB_PORT=str(cluster['port']), DB_USER=cluster['user'],
                          DB_NAME=cls.source, DB_PASSWORD='', DATA_SECURITY_CONFIG='')
        import django
        django.setup()
        from django.core.management import call_command
        call_command('migrate', interactive=False, verbosity=0)

    @classmethod
    def clean_databases(cls):
        from django.db import connections
        connections.close_all()
        with closing(psycopg2.connect(**cls.database)) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                for name in (cls.source, cls.target):
                    cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

    def test_cli_inventory_and_explicit_fernet_candidate_refusal(self):
        from ctf_backend.security_bootstrap import assemble_field_backfill
        from data_security.adapters.persistence.fields import bind_field_storage
        from data_security.contracts import ContractViolation, ReasonCode
        from data_security.tests.phase4_fixtures import field_configuration
        from users.models import CTFUser
        bind_field_storage(None)
        self.addCleanup(bind_field_storage, None)
        user = CTFUser.objects.create_user(username='cli-synthetic-owner', email='gAAAAA-synthetic-format-candidate')
        self.addCleanup(lambda: CTFUser.objects.filter(pk=user.pk).delete())
        with field_configuration(legacy_reads=True) as (path, config, refs, binding):
            command = [str(self.root / '.venv/bin/python'), '-B', '-m', 'tools.data_security.field_maintenance',
                       'inventory', '--config', str(path), '--database', self.source]
            result = subprocess.run(command, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0)
            inventory = json.loads(result.stdout)
            self.assertEqual(inventory['users.ctfuser']['legacy_rows'], 1)
            self.assertEqual(inventory['users.ctfuser']['fernet_candidates']['email'], 1)
            self.assertNotIn(b'gAAAAA-synthetic-format-candidate', result.stdout)
            maintenance = assemble_field_backfill(config_path=path)
            with tempfile.TemporaryDirectory(prefix='phase4-fernet-', dir=os.environ['DS_PHASE4_CONTROLLED_PARENT']) as temporary:
                checkpoint = Path(temporary) / 'checkpoint.json'
                with self.assertRaises(ContractViolation) as failure:
                    maintenance.prepare(checkpoint=checkpoint,
                        recovery={'durability': 'durable', 'event_id': 'backup-restore/synthetic',
                                  'backup_ref': 'backup/synthetic', 'checks': {}})
                self.assertEqual(failure.exception.code, ReasonCode.UNSUPPORTED_FORMAT)
                self.assertFalse(checkpoint.exists())
            user.refresh_from_db()
            self.assertEqual(user.security_state, 'legacy-v0')

    def test_verified_backup_all_owners_restart_cas_reconciliation_and_cutoff(self):
        from django.db import connection, IntegrityError, transaction
        from agent_runtime.models import AgentRun, UserMemory
        from ai_assistant.models import AIConversation, AIMessage
        from audit.models import AuditEvent, AIAuditLog
        from challenges.models import Category, Challenge, ChallengeSolution
        from ctf_backend.security_bootstrap import assemble, assemble_field_backfill
        from data_security.adapters.keys import FileKeyResolver
        from data_security.adapters.persistence.backup import PostgresAgeBackup
        from data_security.adapters.persistence.fields import bind_field_storage
        from data_security.contracts import (AuditReceipt, ContractViolation, Environment, KeyPurpose,
            KeyReference, KeyStatus, ProtectionContext, ProtectionError, Purpose, StoredObject)
        from data_security.tests.fixtures import dto, examples
        from data_security.tests.phase4_fixtures import field_configuration
        from exams.models import ExamRecord, ExamAnswer, TheoryQuestion
        from legal.models import (LegalAnalysisTask, LegalReport, LegalEvidence,
                                  LegalFactSnapshot, ComplianceAgentRun)
        from student_profiles.models import (StudentProfile, DynamicGrowthProfile, LearningPreference,
            LearningPersona, OnboardingInterview, StudentProfileReport)
        from submissions.models import Submission
        from users.models import CTFUser

        self.addCleanup(bind_field_storage, None)
        bind_field_storage(None)
        category = Category.objects.create(name='Synthetic migration')
        originals = []
        expected = {}
        for number in range(100):
            token = f'Backfill{number}@example.invalid'
            originals.append(token)
            tree = {'note': token, 'score': number}
            user = CTFUser.objects.create_user(username=f'backfill-{number}', email=token)
            conversation = AIConversation.objects.create(user=user)
            message = AIMessage.objects.create(conversation=conversation, role='user', content=token, metadata=tree)
            memory = UserMemory.objects.create(user=user, memory_type='fact', memory_key='synthetic',
                                              memory_value=tree, metadata=tree)
            AgentRun.objects.create(user=user, task_type='general', current_step=token, plan=[tree],
                retrieved_docs=[tree], used_tools=[tree], intermediate_result=tree, final_result=tree,
                verification_result=tree, error_message=token)
            challenge = Challenge.objects.create(title=f'Synthetic {number}', category=category,
                                                  difficulty='easy', score=10, flag=token)
            solution = ChallengeSolution.objects.create(challenge=challenge, content=token, hint_map=token)
            question = TheoryQuestion.objects.create(question_type='single_choice', question_text='Synthetic',
                                                      correct_answer=token)
            record = ExamRecord.objects.create(user=user, exam_type='theory')
            answer = ExamAnswer.objects.create(exam_record=record, theory_question=question, user_answer=token)
            submission = Submission.objects.create(user=user, challenge=challenge, flag=token,
                                                     ip_address='192.0.2.42', user_agent='synthetic')
            task = LegalAnalysisTask.objects.create(title=token, input_text=token, result_summary=token,
                                                    metadata=tree, created_by=user)
            legal_report = LegalReport.objects.create(task=task, title=token, summary=token, content=token,
                                                       metadata=tree, generated_by=user)
            LegalEvidence.objects.create(task=task, evidence_type='manual', title=token, excerpt=token, metadata=tree)
            ComplianceAgentRun.objects.create(task=task, input_payload=tree, output_payload=tree)
            snapshot = LegalFactSnapshot.objects.create(source_kind='hybrid', scope={'subject_user_id': user.pk},
                automated_facts=tree, manual_notes=token, warnings=[token], evidence_refs=[],
                preview_hash='1' * 64, snapshot_hash='2' * 64, confirmed_by=user)
            profile = StudentProfile.objects.create(user=user, self_assessed_skills=tree,
                                                     initial_self_assessed_skills=tree)
            DynamicGrowthProfile.objects.create(profile=profile,
                **{name: tree for name in DynamicGrowthProfile.redacted_fields})
            LearningPreference.objects.create(profile=profile, preferred_modality=[token])
            LearningPersona.objects.create(profile=profile, persona_traits=tree, recommended_agent_roster=[token])
            interview = OnboardingInterview.objects.create(profile=profile, answers=tree, ai_analysis=tree)
            report = StudentProfileReport.objects.create(profile=profile, source_interview=interview,
                                                          raw_interview=[tree], report_data=tree, summary=token)
            AuditEvent.objects.create(user=user, category='data_processing', summary='Synthetic',
                                      detail=tree, ip_address='192.0.2.42')
            AIAuditLog.objects.create(user=user, provider=token, model=token, user_message=token,
                ai_response=token, mode='legacy', error_message=token, duration_ms=11,
                token_estimate=12, ip_address='192.0.2.42')
            for obj in (user, message, memory, challenge, solution, question, answer, submission,
                        task, legal_report, snapshot, interview, report):
                expected[(obj._meta.label_lower, obj.pk)] = {
                    name: getattr(obj, name) for name in obj.encrypted_fields}
        scores = dict(CTFUser.objects.values_list('pk', 'score'))

        with field_configuration(legacy_reads=True) as (path, config, refs, binding), \
                tempfile.TemporaryDirectory(prefix='phase4-backfill-', dir=os.environ['DS_PHASE4_CONTROLLED_PARENT']) as temporary:
            work = Path(temporary)
            self.assertFalse(work.is_relative_to(self.root))
            os.chmod(work, 0o700)
            backfill = assemble_field_backfill(config_path=path)
            inventory = backfill.inventory()
            self.assertEqual(len(inventory), 22)
            self.assertTrue(all(item['legacy_rows'] >= 100 for item in inventory.values()))
            self.assertFalse(any(count for item in inventory.values() for count in item['fernet_candidates'].values()))
            existing = CTFUser.objects.order_by('pk').first()
            with self.assertRaises(ContractViolation):
                existing.save(update_fields=['nickname'])
            checkpoint = work / 'checkpoint.json'
            with self.assertRaises(ContractViolation):
                backfill.prepare(checkpoint=checkpoint, recovery={'returncode': 0})
            self.assertFalse(checkpoint.exists())

            tools = Path(os.environ['DS_PHASE4_AGE_TOOLS'])
            offline_dir = work / 'offline'
            offline_dir.mkdir(mode=0o700)
            identity = offline_dir / 'identity.key'
            subprocess.run([str(tools / 'usr/bin/age-keygen'), '-o', str(identity)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            material = next(line for line in identity.read_bytes().splitlines() if line.startswith(b'AGE-'))
            identity.write_bytes(material + b'\n')
            identity.chmod(0o600)
            public_file = path.parent / 'recipient.key'
            with public_file.open('wb') as output:
                subprocess.run([str(tools / 'usr/bin/age-keygen'), '-y', str(identity)], stdout=output,
                               stderr=subprocess.DEVNULL, check=True)
            public_file.chmod(0o600)
            public_ref = dto(KeyReference, key_ref='backup-recipient/v1', purpose=KeyPurpose.BACKUP_PUBLIC,
                             version='v1', status=KeyStatus.ACTIVE)
            private_ref = dto(KeyReference, key_ref='backup-identity/v1', purpose=KeyPurpose.BACKUP_PRIVATE,
                              version='v1', status=KeyStatus.READ_ONLY)
            manifest_path = Path(config['key_manifest'])
            manifest = json.loads(manifest_path.read_text())
            manifest['entries'].append({'reference': public_ref.to_wire(), 'file': public_file.name,
                                        'identities': ['service/security']})
            manifest_path.write_text(json.dumps(manifest))
            offline_manifest = offline_dir / 'manifest.json'
            offline_manifest.write_text(json.dumps({'schema_version': 'ds.key-manifest.v1',
                'environment': 'evaluation', 'entries': [{'reference': private_ref.to_wire(),
                'file': identity.name, 'identities': ['service/backup-offline']}]}))
            offline_manifest.chmod(0o600)
            backup_dir = work / 'backups'
            backup_dir.mkdir(mode=0o700)
            common = dict(directory=str(backup_dir), checks=backfill.checks,
                age=str(tools / 'usr/bin/age'), pg_dump=str(self.root / '.state/pg-install/bin/pg_dump'),
                pg_restore=str(self.root / '.state/pg-install/bin/pg_restore'))
            config['backup'] = dict(database=dict(self.database, dbname=self.source), **common)
            path.write_text(json.dumps(config))
            online = assemble(config_path=path)['backup']
            resolver = FileKeyResolver(manifest_path=offline_manifest, environment=Environment.EVALUATION,
                                       repository_root=self.root)
            offline = PostgresAgeBackup(resolver=resolver, service_identity='service/backup-offline',
                database=dict(self.database, dbname=self.target), environment=Environment.EVALUATION,
                domain='ctf', identity_ref=private_ref, **common)
            self.assertIsInstance(online.resolver.resolve(private_ref, KeyPurpose.BACKUP_PRIVATE,
                                                          'service/security'), ProtectionError)
            context = replace(examples()[ProtectionContext], environment=Environment.EVALUATION,
                              actor_ref='service/security', purpose=Purpose.STORAGE, domain='ctf')
            backup = online.create('snapshot/phase4-owner-fields', public_ref, context)
            self.assertIsInstance(backup, StoredObject)
            receipt = offline.restore(backup, replace(context, actor_ref='service/backup-offline'))
            self.assertIsInstance(receipt, AuditReceipt)
            recovery = json.loads(next(backup_dir.glob('backup-restore-*.json')).read_text())
            with self.assertRaises(ContractViolation):
                backfill.prepare(checkpoint=checkpoint, recovery={**recovery, 'checks': {}})
            counts = backfill.prepare(checkpoint=checkpoint, recovery=recovery)
            self.assertEqual(counts['eligible'], sum(item['legacy_rows'] for item in inventory.values()))

            # A real legacy writer changes a selected row after the backup/checkpoint.
            first_user = CTFUser.objects.order_by('pk').first()
            old_email = first_user.email
            with connection.cursor() as cursor:
                cursor.execute('UPDATE users_ctfuser SET email=%s WHERE id=%s',
                               ['Changed@example.invalid', first_user.pk])
            counts = backfill.run(checkpoint=checkpoint, limit=1)
            self.assertEqual(counts['failed'], 1)
            first_user.refresh_from_db()
            self.assertEqual(first_user.email, 'Changed@example.invalid')
            with connection.cursor() as cursor:
                cursor.execute('UPDATE users_ctfuser SET email=%s WHERE id=%s', [old_email, first_user.pk])
            self.assertEqual(backfill.run(checkpoint=checkpoint, limit=1, retry_failed=True)['failed'], 0)

            # DB commit succeeds but checkpoint write is interrupted; reentry reads the envelope.
            selected = json.loads(checkpoint.read_text())['entries'][1]
            model = backfill.models[selected['model']]
            with patch.object(backfill, '_persist', side_effect=OSError('synthetic checkpoint interruption')):
                with self.assertRaises(OSError):
                    backfill.run(checkpoint=checkpoint, limit=1)
            sealed = model.objects.get(pk=selected['pk'])
            saved_envelope = sealed.security_envelopes
            revision = sealed.security_revision
            backfill = assemble_field_backfill(config_path=path)
            backfill.run(checkpoint=checkpoint, limit=1)
            sealed.refresh_from_db()
            self.assertEqual((sealed.security_revision, sealed.security_envelopes), (revision, saved_envelope))
            while counts['unprocessed']:
                counts = backfill.run(checkpoint=checkpoint, limit=1000)
            self.assertEqual(counts, dict(eligible=counts['eligible'], succeeded=counts['eligible'], failed=0, unprocessed=0))
            self.assertEqual(dict(CTFUser.objects.values_list('pk', 'score')), scores)
            with self.assertRaises(ContractViolation):
                backfill.finish(checkpoint=checkpoint)
            config['field_storage']['legacy_reads'] = False
            path.write_text(json.dumps(config))
            backfill = assemble_field_backfill(config_path=path)
            duplicate = CTFUser.objects.create_user(username='synthetic-duplicate', email=old_email)
            conflicts = backfill.finish(checkpoint=checkpoint)
            self.assertFalse(conflicts['accepted'])
            self.assertEqual(conflicts['conflicts'], 1)
            duplicate.email = 'Resolved@example.invalid'
            duplicate.save(update_fields=['email'])
            result = backfill.finish(checkpoint=checkpoint)
            self.assertTrue(result['accepted'])
            self.assertTrue(backfill.finish(checkpoint=checkpoint)['accepted'])
            for (label, pk), fields in expected.items():
                obj = backfill.models[label].objects.get(pk=pk)
                for name, value in fields.items():
                    self.assertEqual(obj.read_protected(name), value)
            with connection.cursor() as cursor:
                for model in backfill.models.values():
                    table = connection.ops.quote_name(model._meta.db_table)
                    cursor.execute(f'SELECT row_to_json(item)::text FROM {table} item')
                    copied = '\n'.join(row[0] for row in cursor.fetchall())
                    self.assertTrue(all(token not in copied for token in originals), model._meta.label_lower)
            with self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE users_ctfuser SET security_state='legacy-v0' WHERE id=%s", [first_user.pk])
            bind_field_storage(None)
            with self.assertRaises(IntegrityError), transaction.atomic():
                CTFUser.objects.create_user(username='old-writer-refused', email='Old@example.invalid')
            with self.assertRaises(ContractViolation):
                CTFUser.objects.get(pk=first_user.pk).read_protected('email')
            checkpoint_text = checkpoint.read_text()
            self.assertTrue(all(token not in checkpoint_text for token in originals))
            observations = dict(inventory=inventory, recovery=recovery, migration=result,
                encrypted_field_values=1500, plaintext_copy_hits=0, schema_cutoff_tables=22,
                ai_audit_minimized_rows=AIAuditLog.objects.filter(security_state='sealed-v1').count(),
                interrupted_reentry_verified=True, stale_source_refused=True,
                duplicate_conflict_resolved_without_merge=True, scores_not_replayed=True,
                key_material_in_evidence=False, backup_residual='encrypted backup deleted with temporary fixture on exit')
        observations['temporary_backup_removed'] = not work.exists()
        target = Path(os.environ['DS_PHASE4_BACKFILL_OBSERVATIONS'])
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
            json.dump(observations, output, sort_keys=True, indent=2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
