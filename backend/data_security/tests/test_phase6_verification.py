"""Phase-six evidence routing must not turn the default regression into a bound run."""
import runpy
import unittest
from unittest.mock import patch

from tools.data_security import isolation, verify_phase5


class VerificationEntryTests(unittest.TestCase):
    def test_phase_destination_preserves_default_and_bound_commands(self):
        for phase in (5, 6):
            for suite in ('default', 'bound'):
                with self.subTest(phase=phase, suite=suite), \
                        patch('sys.argv', ['verify', '--label', 'fixture', suite]), \
                        patch.object(isolation, 'EVIDENCE', isolation.EVIDENCE), \
                        patch.object(isolation, 'start_postgres', return_value=0), \
                        patch.object(isolation, 'environment', return_value={}), \
                        patch.object(isolation, 'run', return_value=7) as execute:
                    self.assertEqual(verify_phase5.main(phase=phase), 7)
                    self.assertEqual(isolation.EVIDENCE.name, f'phase-{phase:02d}')
                    label, command, cwd, env = execute.call_args.args
                    self.assertEqual(label, 'fixture')
                    self.assertEqual(cwd, isolation.ROOT / 'backend')
                    if suite == 'default':
                        self.assertEqual(command[2], 'manage.py')
                        self.assertNotIn('tools.data_security.phase2_test_entry', command)
                    else:
                        self.assertEqual(command[2:5], ['-m', 'tools.data_security.phase2_test_entry', 'django'])
                    self.assertTrue(set(isolation.MAIN_TEST_LABELS) <= set(command))
                    self.assertIn('--testrunner=baseline_fix_test_cleanup.CleanupRunner', command)
                    self.assertEqual(env['DJANGO_SETTINGS_MODULE'], 'tools.data_security.test_settings')

    def test_sixth_phase_cli_selects_sixth_phase_without_copying_driver(self):
        with patch.object(verify_phase5, 'main', return_value=0) as main:
            with self.assertRaises(SystemExit) as exit:
                runpy.run_path(str(isolation.ROOT / 'tools/data_security/verify_phase6.py'), run_name='__main__')
        self.assertEqual(exit.exception.code, 0)
        main.assert_called_once_with(phase=6)

    def test_dirty_candidate_is_rejected_before_any_test_or_database_start(self):
        sha = 'a' * 40
        with patch('sys.argv', ['verify', '--label', 'fixture', '--expect-head', sha, 'default']), \
                patch.object(verify_phase5.subprocess, 'check_output', side_effect=[sha, ' M changed.py']), \
                patch.object(isolation, 'start_postgres') as start, patch.object(isolation, 'run') as execute:
            with self.assertRaisesRegex(RuntimeError, 'EXACT_CLEAN_CANDIDATE_REQUIRED'):
                verify_phase5.main(phase=6)
        start.assert_not_called()
        execute.assert_not_called()
