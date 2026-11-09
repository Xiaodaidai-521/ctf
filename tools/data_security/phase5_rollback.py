"""Disable only phase-five adapters, retaining phase-three formal failure closure."""
import importlib
import json
import sys

STOPPED = ('data_security.adapters.tabular.codec', 'data_security.adapters.tabular.column_v1',
           'data_security.adapters.tabular.source_plans', 'data_security.adapters.tabular.parsed_artifacts')


class DisabledTabular:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in STOPPED:
            raise ImportError('PHASE5_ADAPTER_STOPPED')


def main():
    guard = DisabledTabular()
    sys.meta_path.insert(0, guard)
    try:
        for module in STOPPED:
            try:
                importlib.import_module(module)
            except ImportError as exc:
                assert str(exc) == 'PHASE5_ADAPTER_STOPPED'
            else:
                raise AssertionError('STOPPED_ADAPTER_REMAINED_AVAILABLE')
        from tools.data_security.phase3_rollback import main as formal_failure_closure
        result = formal_failure_closure()
        assert result == 0
        print(json.dumps({'phase5_adapters_disabled': True, 'prior_formal_protection_retained': True,
            'raw_payload_fallback': False, 'delivery_enabled': False, 'quota_released': False,
            'schema_or_key_version_downgrade': False, 'rollback_kind': 'stop-new-tabular-use-cases'}))
        return result
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    raise SystemExit(main())
