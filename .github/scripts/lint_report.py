"""Report the lint findings of the modules of this repository, from the logs of run_odoo_lint.sh.

A finding fails the job unless .github/lint_skip.txt lists it. The list holds the known findings not fixed yet:
a line per finding, without line numbers, so that it survives edits around the code. It should only shrink.

    lint_report.py PYLINT_OUTPUT ODOO_LOG           report, exit 1 on a new finding
    lint_report.py PYLINT_OUTPUT ODOO_LOG --update  write the findings to the skip list
"""
import collections
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
SKIP_FILE = REPO / '.github' / 'lint_skip.txt'
HEADER = '# Known lint findings, not fixed yet: see .github/scripts/lint_report.py. This list should only shrink.\n'
RECORD = re.compile(r'(?m)^(?=\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ )')
LOG_LINE = re.compile(r'\S+ \S+ \d+ (WARNING|ERROR|CRITICAL) \S+ (\S+): (.*)', re.S)
SUBTEST = re.compile(r"^(?:FAIL|ERROR): Subtest (\w+)\.\w+ \((.*?)\)$", re.M)
FAILURE = re.compile(r"^(?:FAIL|ERROR): (\w+)\.\w+", re.M)
SUBTEST_ATTRIBUTE = re.compile(r"(\w+)='([^']*)'")
# what Odoo's linter reports and we leave out: values equal to the default of a manifest
NOISE = re.compile(r'Setting manifest key \w+ to the default manifest value')
# the key of the Odoo Apps store, that older versions do not know
KNOWN_MANIFEST_KEYS = {'support'}


def our_modules():
    return sorted(path.parent.name for path in REPO.glob('*/__manifest__.py'))


def clean(text):
    """ A line without what changes from a run to another: the folder of the repository, the numbers. """
    text = text.replace(f'{REPO}/', '').strip()
    # a set is printed in a random order
    text = re.sub(r'\{([^{}]*)\}', lambda match: '{%s}' % ', '.join(sorted(match[1].split(', '))), text)
    return re.sub(r'\s+', ' ', re.sub(r'\b\d+\b', 'N', text))[:300]


def pylint_findings(path, ours):
    """ The lines of pylint are "symbol|path|message": the file is enough, as the line number moves. """
    findings = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        parts = line.split('|', 2)
        if len(parts) == 3 and ours.search(parts[1]):
            findings.append(f'pylint {parts[0]} {clean(parts[1])}')
    return findings


def odoo_findings(path, ours):
    findings = []
    for record in RECORD.split(path.read_text(encoding='utf-8', errors='replace')):
        match = LOG_LINE.match(record)
        if not match or 'test_lint' not in match[2] or NOISE.search(match[3]):
            continue
        message = match[3]
        subtest = SUBTEST.search(message)
        if subtest:
            # "module" and "file" tell whose it is, and "model" repeats it for each model of an override of base.
            # Without them, as for a deprecated attribute of a model, it is ours until proven otherwise: Odoo passes
            # these checks on its own code.
            attributes = dict(SUBTEST_ATTRIBUTE.findall(subtest[2]))
            owner = attributes.get('module') or attributes.get('file')
            if not owner or ours.search(owner):
                if owner:
                    attributes.pop('model', None)
                reason = re.search(r'^(?:\w*Error|\w*Exception): (.*(?:\n.*)?)$', message, re.M)
                # without the model, which older versions repeat in the message
                reason = reason[1] if reason else ''
                if 'Items in the first set' in reason:
                    # one key a line, in a random order
                    keys = set(re.findall(r"^'(\w+)'", message, re.M)) - KNOWN_MANIFEST_KEYS
                    if not keys:
                        continue
                    reason = f"Unknown manifest keys: {', '.join(sorted(keys))}"
                reason = re.sub(r'^Invalid override .*?, ', 'Invalid override: ', reason)
                reason = re.sub(r' in [\w.]+ for ', ' of ', reason)
                name = ' '.join(f'{key}={value}' for key, value in sorted(attributes.items()))
                finding = clean(f'{subtest[1]} {name} {reason}')
                # once: the same override of base fails for each model
                if finding not in findings:
                    findings.append(finding)
            continue
        failure = FAILURE.search(message)
        lines = message.splitlines()
        if not failure:
            # a message of the linter, which names the file on its first line
            if ours.search(lines[0]):
                findings.append(clean(lines[0]))
            continue
        # a failed test listing its findings, a line each
        findings += [
            clean(f'{failure[1]} {line}') for line in lines[1:]
            if ours.search(line) and not line.lstrip().startswith('File "')
        ]
    return findings


def main():
    args = [arg for arg in sys.argv[1:] if arg != '--update']
    ours = re.compile(r'(?<![\w.-])(?:odoo\.addons\.)?(%s)\b' % '|'.join(map(re.escape, our_modules())))
    log = pathlib.Path(args[1])
    if not re.search(r'[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests', log.read_text(encoding='utf-8', errors='replace')):
        print('::error::The lint tests did not run: see the log')
        return 1
    found = collections.Counter(pylint_findings(pathlib.Path(args[0]), ours) + odoo_findings(log, ours))
    if '--update' in sys.argv:
        SKIP_FILE.write_text(HEADER + ''.join(f'{line}\n' for line in sorted(found.elements())), encoding='utf-8')
        print(f'{sum(found.values())} findings written to {SKIP_FILE.relative_to(REPO)}')
        return 0
    skipped = collections.Counter(
        line for line in (SKIP_FILE.read_text(encoding='utf-8').splitlines() if SKIP_FILE.exists() else [])
        if line and not line.startswith('#')
    )
    new = found - skipped
    fixed = skipped - found
    for line in sorted(fixed):
        print(f'::warning::Fixed, remove it from .github/lint_skip.txt: {line}')
    for line in sorted(new):
        print(f'::error::{line}')
    print(f'{sum(found.values())} findings, {sum(new.values())} new, {sum(fixed.values())} fixed')
    return 1 if new else 0


if __name__ == '__main__':
    sys.exit(main())
