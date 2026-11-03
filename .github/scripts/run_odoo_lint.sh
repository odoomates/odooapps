#!/usr/bin/env bash
# Lint the files a pull request edits, with the rules of this version of Odoo: its test_lint module, and pylint with
# its gettext checker. Any finding in an edited file fails: see lint_report.py.
#
#   run_odoo_lint.sh <database> <base commit>
#
# Left out: the docstrings and ESLint of Odoo; for now, until they are reviewed: the indexes, the SQL injections and
# the raises in unlink.
# Environment: as run_odoo_tests.sh.
set -uo pipefail

db=${1:?database}
base=${2:?base commit}
repo=$(cd "$(dirname "$0")/../.." && pwd)
odoo=${ODOO_PATH:-$repo/../odoo}
python=${PYTHON:-python3}
log_dir=${LOG_DIR:-$(mktemp -d)}
mkdir -p "$log_dir"
log=$log_dir/$db.log
pylint_log=$log_dir/$db.pylint.log
edited=$log_dir/$db.edited.txt
conf=$(mktemp)
excluded=TestPyLint,TestESLint,TestDocstring,TestIndex,TestIndexMeta,TestTableObjects,TestSqlInjection

# the edited files of the modules, the removed ones apart
git -C "$repo" diff --name-only --diff-filter=d "$base" > "$edited.all" || exit 1
modules=$(cut -d/ -f1 "$edited.all" | sort -u | while read -r name; do
    [ -f "$repo/$name/__manifest__.py" ] && echo "$name"
done)
if [ -z "$modules" ]; then
    echo "No module is edited: nothing to lint"
    exit 0
fi
grep -E "^($(echo "$modules" | paste -sd'|' -))/" "$edited.all" > "$edited"
echo "Edited files:"
cat "$edited"

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
createdb --encoding=UTF8 --lc-collate=C --template=template0 "$db" || exit 1

# pylint on the edited Python files, with the checker of this version of Odoo
: > "$pylint_log"
python_files=$(grep -E '\.py$' "$edited")
if [ -n "$python_files" ]; then
    checkers=$odoo/odoo/addons/test_lint/tests
    (cd "$repo" && PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$checkers:$odoo" "$python" -m pylint \
        --rcfile=/dev/null --disable=all,useless-option-value,unknown-option-value --reports=n --score=n \
        --enable=used-before-assignment,undefined-variable,eval-used,unreachable,function-redefined,missing-gettext,gettext-variable,gettext-placeholders,gettext-repr \
        --load-plugins=_odoo_checker_gettext '--msg-template={symbol}|{path}|{line}|{msg}' $python_files) > "$pylint_log" 2>&1
    pylint_status=$?
    # 1: a fatal message; 32: a usage error; the other bits are the findings
    if [ $((pylint_status & 33)) -ne 0 ]; then
        echo "::error::pylint failed (exit $pylint_status)"
        tail -20 "$pylint_log" | cut -c1-300
        exit 1
    fi
fi

# the tests of test_lint, with the edited modules: the demo data are of no use (the option is gone since Odoo 19,
# without demo data by default)
demo=$("$python" "$odoo/odoo-bin" --help 2>/dev/null | grep -q -- --without-demo && echo --without-demo=all)
tags=/test_lint$(printf ',-/test_lint:%s' ${excluded//,/ })
echo "Installing the edited modules on $db, testing $tags"
"$python" "$odoo/odoo-bin" -c "$conf" -d "$db" -i "test_lint,$(echo "$modules" | paste -sd, -)" $demo --test-tags "$tags" \
    --stop-after-init --http-port "${HTTP_PORT:-8069}" > "$log" 2>&1

"$python" "$repo/.github/scripts/lint_report.py" "$pylint_log" "$log" "$edited"
