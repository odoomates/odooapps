"""Check the messages of the commits of a pull request: the first line is ``[TAG] module: summary``.

- TAG: one of TAGS (the tags of Odoo, and MIG for a migration to a new version);
- module: the technical name of the module, several separated by ", ", or ``*``;
- summary: at most 50 characters, without a full stop at the end.

Merge commits are not checked. Reads the commits (GitHub API, one JSON object per line) from standard input,
writes the errors as GitHub annotations and in the summary of the job.
"""
import json
import os
import re
import sys

TAGS = ('FIX', 'IMP', 'ADD', 'REM', 'REF', 'REV', 'MOV', 'REL', 'MERGE', 'CLA', 'I18N', 'PERF', 'CLN', 'LINT',
        'MIG')
SUMMARY_LENGTH = 50
HEADER = re.compile(r'^\[(?P<tag>[^\]]+)\] (?P<modules>[\w.*]+(?:, [\w.*]+)*): (?P<summary>.*)$')
EXAMPLE = '[FIX] om_account_followup: level of paid invoices'


def errors_of(header):
    """ The errors of the first line of a commit message. """
    match = HEADER.match(header)
    if not match:
        return [f'the first line must read "[TAG] module: summary", for example "{EXAMPLE}"']
    errors = []
    if match['tag'] not in TAGS:
        errors.append(f'unknown tag [{match["tag"]}]: use one of {", ".join(f"[{tag}]" for tag in TAGS)}')
    summary = match['summary']
    if not summary.strip():
        errors.append('the summary after "module: " is empty')
    if len(summary) > SUMMARY_LENGTH:
        errors.append(f'the summary after "module: " has {len(summary)} characters: at most {SUMMARY_LENGTH}')
    if summary.endswith('.'):
        errors.append('the summary does not end with a full stop')
    return errors


def main():
    # one commit per line, as `gh api --paginate --jq '.[]'` writes them
    commits = [json.loads(line) for line in sys.stdin if line.strip()]
    report = []
    for commit in commits:
        if len(commit['parents']) > 1:
            continue
        header = commit['commit']['message'].splitlines()[0] if commit['commit']['message'] else ''
        for error in errors_of(header):
            report.append((commit['sha'][:8], header, error))
            print(f'::error title=Commit message {commit["sha"][:8]}::{header}: {error}')
    summary_file = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_file:
        with open(summary_file, 'a', encoding='utf-8') as summary:
            if report:
                summary.write('### Commit messages to fix\n\n| Commit | First line | Problem |\n|---|---|---|\n')
                for sha, header, error in report:
                    summary.write(f'| `{sha}` | `{header}` | {error} |\n')
                summary.write(f'\nThe format is `[TAG] module: summary`, for example `{EXAMPLE}`: see '
                              'CONTRIBUTING.md. Fix the messages with `git rebase -i` (reword), then force-push.\n')
            else:
                summary.write('All the commit messages follow `[TAG] module: summary`.\n')
    if report:
        print(f'{len(report)} problem(s) in the commit messages: see the summary of the job.')
        return 1
    print(f'{sum(len(c["parents"]) <= 1 for c in commits)} commit message(s) checked: all fine.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
