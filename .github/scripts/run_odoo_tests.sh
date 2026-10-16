#!/usr/bin/env bash
# Install modules on a new database, run their tests, and fail on a failed test or an ERROR, CRITICAL or WARNING
# line in the log. The database is dropped at the end.
#
#   run_odoo_tests.sh <database> <modules to install> [test tags]
#
# The test tags default to the tests of every module of the repository. Environment:
#   ODOO_PATH  the Odoo source (default: ../odoo next to the repository)
#   PYTHON     the Python of Odoo (default: python3)
#   PGHOST, PGPORT, PGUSER, PGPASSWORD  the PostgreSQL server
#   LOG_DIR    where the log is written (default: a temporary folder)
set -uo pipefail

db=${1:?database}
modules=${2:?modules to install}
repo=$(cd "$(dirname "$0")/../.." && pwd)
tags=${3:-$(cd "$repo" && ls -d */__manifest__.py | cut -d/ -f1 | sed 's#^#/#' | paste -sd, -)}
odoo=${ODOO_PATH:-$repo/../odoo}
python=${PYTHON:-python3}
log_dir=${LOG_DIR:-$(mktemp -d)}
mkdir -p "$log_dir"
log=$log_dir/$db.log
conf=$(mktemp)

cat > "$conf" <<CONF
[options]
addons_path = $odoo/addons,$odoo/odoo/addons,$repo
db_host = ${PGHOST:-localhost}
db_port = ${PGPORT:-5432}
db_user = ${PGUSER:-odoo}
db_password = ${PGPASSWORD:-odoo}
data_dir = $(mktemp -d)
CONF

drop() { dropdb --if-exists "$db" >/dev/null 2>&1; rm -f "$conf"; }
trap drop EXIT
dropdb --if-exists "$db" >/dev/null 2>&1
# the way Odoo creates its databases: the C collation keeps parent_path ranges
# (child_of, moving a record with its children) right
createdb --encoding=UTF8 --lc-collate=C --template=template0 "$db" || exit 1

echo "Installing $modules on $db, testing $tags"
"$python" "$odoo/odoo-bin" -c "$conf" -d "$db" -i "$modules" --with-demo --test-tags "$tags" \
    --stop-after-init --http-port "${HTTP_PORT:-8069}" > "$log" 2>&1
status=$?

result=$(grep -oE '[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests' "$log" | tail -1)
problems=$(grep -E ' (WARNING|ERROR|CRITICAL) ' "$log")
echo "Result: ${result:-no test result} (exit $status)"
if [ -n "$problems" ]; then
    echo "Log problems:"
    echo "$problems" | cut -c1-400
fi
if [ $status -ne 0 ] || [ -z "$result" ] || [ "${result%% failed*}" != 0 ] \
        || [ "$(echo "$result" | grep -oE '[0-9]+ error' | cut -d' ' -f1)" != 0 ] || [ -n "$problems" ]; then
    echo "FAILED: see $log"
    exit 1
fi
echo "Passed"
