"""Reuse isolated-cluster lifecycle; preserve step-03 historical evidence."""
from mainline1.tests.run_isolated_postgres import main

if __name__ == '__main__':
    raise SystemExit(main(test_modules=('mainline1.tests.postgres_review_cases', 'mainline1.tests.postgres_cases'),
                          evidence_filename='step-06-postgres-verification.json'))
