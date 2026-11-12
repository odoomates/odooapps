"""Report the lint findings of the files edited by a pull request, from the logs of run_odoo_lint.sh: any of them
fails the job. The rest of the code is cleaned when it is edited.

    lint_report.py PYLINT_OUTPUT ODOO_LOG EDITED_FILES
"""
import os
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
RECORD = re.compile(r'(?m)^(?=\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ )')
LOG_LINE = re.compile(r'\S+ \S+ \d+ (WARNING|ERROR|CRITICAL) \S+ (\S+): (.*)', re.S)
SUBTEST = re.compile(r"^(?:FAIL|ERROR): Subtest (\w+)\.\w+ \((.*?)\)$", re.M)
FAILURE = re.compile(r"^(?:FAIL|ERROR): (\w+)\.\w+", re.M)
SUBTEST_ATTRIBUTE = re.compile(r"(\w+)='([^']*)'")
REASON = re.compile(r'^(?:\w*Error|\w*Exception): (.*)$', re.M)
# what Odoo's linter reports and we leave out: values equal to the default of a manifest, and the key of the Odoo
# Apps store that older versions do not know
NOISE = re.compile(r'Setting manifest key \w+ to the default manifest value')
KNOWN_MANIFEST_KEYS = {'support'}
# a private repository holds paid modules: the Odoo Proprietary License is allowed there, not the LGPL Odoo asks for
PRIVATE_REPO = os.environ.get('LINT_PRIVATE_REPO') == 'true'
PAID_LICENSE = re.compile(r"^'LGPL-3' != 'OPL-1'$")


def clean(text):
    text = text.replace(f'{REPO}/', '')
    # a set is printed in a random order
    text = re.sub(r'\{([^{}]*)\}', lambda match: '{%s}' % ', '.join(sorted(match[1].split(', '))), text)
    return re.sub(r'\s+', ' ', text).strip()[:300]


def defines(path, method):
    """ Whether an edited file defines the method: an override names its module and method, not its file. """
    file = REPO / path
    return path.endswith('.py') and file.exists() and re.search(
        rf'^\s*def {re.escape(method)}\(', file.read_text(encoding='utf-8', errors='replace'), re.M)


def edited_by(text, edited):
    """ Whether the text of a finding names an edited file, or a Python module of one. """
    text = text.replace(f'{REPO}/', '')
    python_modules = {path[:-3].replace('/', '.') for path in edited if path.endswith('.py')}
    return any(path in text for path in edited) or any(f'odoo.addons.{name}' in text for name in python_modules)


def pylint_findings(path, edited):
    """ The lines of pylint are "symbol|path|line|message". """
    findings = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        parts = line.split('|', 3)
        if len(parts) == 4 and parts[1] in edited:
            findings.append(f'{parts[1]}:{parts[2]}: {parts[0]}: {parts[3]}')
    return findings


def subtest_finding(subtest, message, edited):
    attributes = dict(SUBTEST_ATTRIBUTE.findall(subtest[2]))
    module = attributes.get('module', '')
    file = attributes.get('file', '')
    if file:
        hit = file in edited
    elif module and attributes.get('method'):
        hit = any(path.startswith(f'{module}/') and defines(path, attributes['method']) for path in edited)
    elif module:
        hit = f'{module}/__manifest__.py' in edited
    else:
        # a deprecated attribute of a model: the message names its Python module
        hit = edited_by(message, edited)
    if not hit:
        return None
    if module:
        attributes.pop('model', None)
    reason = REASON.search(message)
    reason = reason[1] if reason else ''
    if PRIVATE_REPO and PAID_LICENSE.match(reason):
        return None
    if reason.startswith('Items in the first set'):
        keys = set(re.findall(r"^'(\w+)'", message, re.M)) - KNOWN_MANIFEST_KEYS
        if not keys:
            return None
        reason = f"Unknown manifest keys: {', '.join(sorted(keys))}"
    # without the model, which some versions repeat in the message
    reason = re.sub(r'^Invalid override .*?, ', 'Invalid override: ', reason)
    reason = re.sub(r' in [\w.]+ for ', ' of ', reason)
    name = ' '.join(f'{key}={value}' for key, value in sorted(attributes.items()))
    return clean(f'{subtest[1]} {name} {reason}')


def odoo_findings(path, edited):
    findings = []
    for record in RECORD.split(path.read_text(encoding='utf-8', errors='replace')):
        match = LOG_LINE.match(record)
        if not match or 'test_lint' not in match[2] or NOISE.search(match[3]):
            continue
        message = match[3]
        lines = message.splitlines()
        subtest = SUBTEST.search(message)
        failure = FAILURE.search(message)
        if subtest:
            finding = subtest_finding(subtest, message, edited)
            if finding and finding not in findings:
                findings.append(finding)
        elif failure:
            # a failed test listing its findings, a line each
            findings += [
                clean(f'{failure[1]} {line}') for line in lines[1:]
                if edited_by(line, edited) and not line.lstrip().startswith('File "')
            ]
        else:
            # a message of the linter, naming a file or the module of a manifest
            manifest = re.search(r'manifest value \w+ in module (\w+)', lines[0])
            if edited_by(lines[0], edited) or (manifest and f'{manifest[1]}/__manifest__.py' in edited):
                findings.append(clean(lines[0]))
    return findings


def main():
    log = pathlib.Path(sys.argv[2])
    edited = set(pathlib.Path(sys.argv[3]).read_text(encoding='utf-8').splitlines())
    if not re.search(r'[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests', log.read_text(encoding='utf-8', errors='replace')):
        print('::error::The lint tests did not run: see the log')
        return 1
    findings = pylint_findings(pathlib.Path(sys.argv[1]), edited) + odoo_findings(log, edited)
    for line in sorted(findings):
        print(f'::error::{line}')
    print(f'{len(findings)} findings in {len(edited)} edited files')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
