"""Check the lines a pull request adds against the Odoo coding guidelines: a debugger, a print, or the version of
another branch in a manifest fail; cr.commit() and SQL built from strings are warnings, as they can have a reason.

    check_guidelines.py BRANCH BASE_COMMIT
"""
import ast
import pathlib
import re
import subprocess
import sys

DEBUGGERS = {'pdb', 'ipdb', 'pudb'}
# scripts run by hand, not code of the module
SCRIPT_FOLDERS = {'tools', 'doc'}
HUNK = re.compile(r'^@@ -\S+ \+(\d+)(?:,(\d+))? @@')


def added_lines(base):
    """ {path: the numbers of the lines added since base}, for the Python files. """
    diff = subprocess.run(['git', 'diff', '-U0', '--diff-filter=d', base, '--', '*.py'],
                          capture_output=True, text=True, check=True).stdout
    added = {}
    path = None
    for line in diff.splitlines():
        if line.startswith('+++ '):
            path = line[6:]
            added[path] = set()
        elif match := HUNK.match(line):
            start, count = int(match[1]), int(match[2] or 1)
            added[path].update(range(start, start + count))
    return added


def check_manifest(source, branch):
    match = re.search(r"""^\s*['"]version['"]\s*:\s*['"](\d+\.0)\.[^'"]*['"]""", source, re.M)
    if match and match[1] != branch:
        line = source[:match.start(1)].count('\n') + 1
        yield 'error', line, f'This version is for Odoo {match[1]}, and this branch is {branch}.'


def check_python(source, script):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return  # installing the module reports it
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {alias.name.split('.')[0] for alias in node.names} | {(getattr(node, 'module', '') or '').split('.')[0]}
            if names & DEBUGGERS:
                yield 'error', node.lineno, 'Remove this debugger.'
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                if function.id == 'breakpoint':
                    yield 'error', node.lineno, 'Remove this debugger.'
                elif function.id == 'print' and not script:
                    yield 'error', node.lineno, 'Use logging, not print.'
            elif isinstance(function, ast.Attribute):
                if function.attr in ('commit', 'rollback') and getattr(function.value, 'attr', '') in ('cr', '_cr'):
                    yield 'warning', node.lineno, f'cr.{function.attr}(): Odoo manages the transaction.'
                elif function.attr == 'execute' and node.args and (
                        isinstance(node.args[0], (ast.JoinedStr, ast.BinOp))
                        or getattr(getattr(node.args[0], 'func', None), 'attr', '') == 'format'):
                    yield 'warning', node.lineno, 'SQL built from strings: pass the values as parameters.'


def main():
    branch, base = sys.argv[1:3]
    errors = 0
    for path, lines in sorted(added_lines(base).items()):
        file = pathlib.PurePath(path)
        if file.parts[0] == '.github' or not pathlib.Path(file.parts[0], '__manifest__.py').is_file():
            continue
        source = pathlib.Path(path).read_text(encoding='utf-8', errors='replace')
        if file.name == '__manifest__.py':
            findings = check_manifest(source, branch)
        else:
            findings = check_python(source, bool(SCRIPT_FOLDERS & set(file.parts[1:-1])))
        for level, line, message in findings:
            if line in lines:
                errors += level == 'error'
                print(f'::{level} file={path},line={line},title=Odoo guidelines::{message}')
    print(f'{errors} error(s).')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
