"""Bump the version of a module manifest, for the mergebot.

    python3 mergebot_version.py LEVEL < MANIFEST

LEVEL is major, minor or patch. The manifest with its new version goes to standard output, "old -> new" to
standard error. The manifest is edited as text: it is never imported nor evaluated.
"""
import ast
import re
import sys

LEVELS = ('major', 'minor', 'patch')
VERSION = re.compile(r"""(['"]version['"]\s*:\s*)(['"])([0-9.]+)(['"])""")


def bumped(version, level):
    """ `version` bumped by `level`: 1.2.3 (or 20.0.1.2.3, the series kept) gives 2.0.0, 1.3.0 or 1.2.4;
    1.2 is read as 1.2.0. """
    parts = [int(part) for part in version.split('.')]
    series = parts[:2] if len(parts) == 5 else []
    own = parts[2:] if len(parts) == 5 else parts
    own += [0] * (3 - len(own))
    position = LEVELS.index(level)
    own = [*own[:position], own[position] + 1] + [0] * (len(own) - position - 1)
    return '.'.join(str(part) for part in series + own)


def main():
    level = sys.argv[1]
    if level not in LEVELS:
        sys.exit(f'unknown level {level}')
    manifest = sys.stdin.read()
    match = VERSION.search(manifest)
    if not match:
        sys.exit('no version in the manifest')
    version = bumped(match[3], level)
    new = VERSION.sub(lambda found: f'{found[1]}{found[2]}{version}{found[4]}', manifest, count=1)
    ast.literal_eval(new)  # still a valid manifest
    sys.stdout.write(new)
    sys.stderr.write(f'{match[3]} -> {version}\n')


if __name__ == '__main__':
    main()
