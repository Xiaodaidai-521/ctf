#!/usr/bin/env bash
# Disposable module-five PostgreSQL acceptance. No system package/service writes.
set -euo pipefail
ROOT=/home/hatch/workspace/ctf-module5
TOOLS=/home/hatch/.local/share/module5-r2-pg-20261029
RUNTIME=/tmp/module5-r2-pg-20261029-1328
PG_BIN="$RUNTIME/install/bin"
export LD_LIBRARY_PATH="$RUNTIME/install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
PY=/home/hatch/workspace/ctf-venv/bin/python
LOG="$ROOT/evidence/module5"
export DATABASE_BACKEND=postgres
export DATABASE_URL=postgresql://r2pg@127.0.0.1:55465/module5_r2
export DEBUG=true ALLOWED_HOSTS=localhost,127.0.0.1,testserver SECURE_SSL_REDIRECT=false
export PRACTICAL_TRAINING_ENABLED=true PRACTICAL_TRAINING_VERIFIER_IP=127.0.0.1
export PGHOST=127.0.0.1 PGPORT=55465 PGUSER=r2pg PGDATABASE=module5_r2
export PGAPPNAME=r2pg-driver PYTHONUNBUFFERED=1
pg_run() {
    if [[ $(id -u) == 0 ]]; then
        setpriv --reuid=65534 --regid=65534 --clear-groups "$@"
    else
        "$@"
    fi
}
init_cluster() {
    [[ ! -e "$RUNTIME/cluster/PG_VERSION" ]] || { printf 'Private cluster already initialized\n'; return; }
    # /home/hatch has unmapped ancestor GIDs in this user namespace. Do not
    # change shared ancestors; use a new private temporary runtime instead.
    mkdir -m 755 "$RUNTIME"
    cp -R --no-preserve=ownership "$TOOLS/install" "$RUNTIME/install"
    chmod -R a+rX "$RUNTIME/install"
    if [[ $(id -u) == 0 ]]; then chown 65534:65534 "$RUNTIME"; fi
    pg_run mkdir -m 700 "$RUNTIME/cluster" "$RUNTIME/socket"
    pg_run "$PG_BIN/initdb" -D "$RUNTIME/cluster" -U r2pg --auth-local=trust --auth-host=trust --encoding=UTF8 --no-locale
}
start_cluster() {
    if pg_run "$PG_BIN/pg_ctl" -D "$RUNTIME/cluster" status; then return; fi
    # Refuse to use an occupied endpoint; never operate on a shared server.
    "$PY" -I -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',55465)); s.close()"
    pg_run "$PG_BIN/pg_ctl" -D "$RUNTIME/cluster" \
        -o "-h 127.0.0.1 -p 55465 -k $RUNTIME/socket -c max_connections=25 -c log_lock_waits=on -c deadlock_timeout=100ms -c log_statement=ddl -c log_line_prefix=%m[%p]%d/%a:" -w start >> "$LOG/r2-pg-server.log" 2>&1
}
stop_cluster() {
    pg_run "$PG_BIN/pg_ctl" -D "$RUNTIME/cluster" -m fast -w stop
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p 55465; then return 1; fi
    printf 'Private PostgreSQL stopped; loopback endpoint no longer responds.\n'
}
create_database() {
    "$PG_BIN/createdb" --maintenance-db=postgres module5_r2
    "$PG_BIN/psql" -X -v ON_ERROR_STOP=1 -c 'SELECT version(), current_database(), inet_server_addr(), inet_server_port();'
}
migrate_database() {
    "$PY" "$ROOT/backend/manage.py" migrate --noinput --verbosity 2
    "$PY" "$ROOT/backend/manage.py" showmigrations practical_training
    "$PY" "$ROOT/backend/manage.py" makemigrations practical_training --check --dry-run
}
run_suite() {
    "$PY" "$ROOT/backend/manage.py" test practical_training --verbosity 2 --noinput
}
run_concurrency() {
    "$PG_BIN/psql" -X -v ON_ERROR_STOP=1 -c "ALTER DATABASE module5_r2 SET log_statement = 'all';"
    "$PY" "$ROOT/backend/scripts/r2_pg_concurrency.py"
    "$PG_BIN/psql" -X -a -v ON_ERROR_STOP=1 -f "$ROOT/backend/scripts/r2_pg_assertions.sql" > "$LOG/r2-pg-sql-results.log" 2>&1
}
case "${1:-}" in
    init) init_cluster ;;
    start) start_cluster ;;
    create) create_database ;;
    migrate) migrate_database ;;
    test) run_suite ;;
    concurrency) run_concurrency ;;
    stop) stop_cluster ;;
    status) pg_run "$PG_BIN/pg_ctl" -D "$RUNTIME/cluster" status ;;
    all)
        init_cluster
        start_cluster
        trap 'stop_cluster > "$LOG/r2-pg-shutdown.log" 2>&1' EXIT
        create_database > "$LOG/r2-pg-database.log" 2>&1
        migrate_database > "$LOG/r2-pg-migrate.log" 2>&1
        run_suite > "$LOG/r2-pg-tests.log" 2>&1
        run_concurrency > "$LOG/r2-pg-concurrency.log" 2>&1
        ;;
    *) printf 'Usage: %s {init|start|create|migrate|test|concurrency|stop|status|all}\n' "$0"; exit 2 ;;
esac
