"""Bump the version of a module manifest, for the mergebot.

    python3 mergebot_version.py LEVEL BASE_MANIFEST < HEAD_MANIFEST

LEVEL is major, minor or patch. The new version is the version of BASE_MANIFEST (the module on the target
branch) bumped by LEVEL, written in the manifest read from standard input (the module of the pull request),
which goes to standard output. Nothing is written when the pull request already raised the version.

The manifest is edited as text: it is never imported nor evaluated.
"""
import ast
import re
import sys

LEVELS = ('major', 'minor', 'patch')
VERSION = re.compile(r"""(['"]version['"]\s*:\s*)(['"])([0-9.]+)(['"])""")


def version_of(text):
    """ The version of a manifest, read as a literal. """
    match = VERSION.search(text)
    return match[3] if match else None


def bumped(version, level):
    """ `version` bumped by `level`: 1.2.3 (or 20.0.1.2.3, the series kept) gives 2.0.0, 1.3.0 or 1.2.4;
    1.2 gives 2.0 or 1.3. """
    parts = [int(part) for part in version.split('.')]
    series = parts[:2] if len(parts) == 5 else []
    own = parts[2:] if len(parts) == 5 else parts
    position = min(LEVELS.index(level), len(own) - 1)
    own = [*own[:position], own[position] + 1] + [0] * (len(own) - position - 1)
    return '.'.join(str(part) for part in series + own)


def as_tuple(version):
    return tuple(int(part) for part in version.split('.'))


def main():
    level, base_path = sys.argv[1], sys.argv[2]
    if level not in LEVELS:
        sys.exit(f'unknown level {level}')
    base_version = version_of(open(base_path, encoding='utf-8').read())
    head = sys.stdin.read()
    head_version = version_of(head)
    if not base_version or not head_version:
        sys.exit('no version in the manifest')
    if as_tuple(head_version) > as_tuple(base_version):
        return 1  # bumped already by the pull request
    new_version = bumped(base_version, level)
    new = VERSION.sub(lambda match: f'{match[1]}{match[2]}{new_version}{match[4]}', head, count=1)
    ast.literal_eval(new)  # still a valid manifest
    sys.stdout.write(new)
    sys.stderr.write(f'{head_version} -> {new_version}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
