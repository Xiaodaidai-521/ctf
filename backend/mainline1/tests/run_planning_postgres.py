"""Use only the existing fresh-cluster harness; never a configured business DB."""
from mainline1.tests.run_isolated_postgres import main

if __name__ == '__main__':
    raise SystemExit(main(test_modules=('mainline1.tests.postgres_planning_cases',
        'mainline1.tests.postgres_review_cases', 'mainline1.tests.postgres_cases'),
        evidence_filename='step-07-postgres-verification.json'))
