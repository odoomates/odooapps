# Where a traced method lives, opened the way the viewer can: in the editor of
# the machine when Odoo runs on it, else on the web page of its git repository.
import configparser
import functools
import glob
import os
import re
import shlex
import shutil
import subprocess

import odoo
import odoo.addons

# the editors, the first found wins: (name, commands, desktop file patterns, arguments)
EDITORS = [
    ('VS Code', ['code'], ['code.desktop'], lambda path, line: ['--goto', f'{path}:{line}']),
    ('Cursor', ['cursor'], ['cursor*.desktop'], lambda path, line: ['--goto', f'{path}:{line}']),
    ('PyCharm', ['pycharm', 'pycharm-professional', 'pycharm-community', 'charm'],
     ['jetbrains-pycharm*.desktop', 'pycharm*.desktop'], lambda path, line: ['--line', str(line), path]),
]
DESKTOP_DIRS = [
    '/usr/share/applications', '/usr/local/share/applications',
    os.path.expanduser('~/.local/share/applications'), '/var/lib/snapd/desktop/applications',
]
LOCAL_ADDRESSES = frozenset({'127.0.0.1', '::1', 'localhost'})


def _desktop_command(patterns):
    """ The program a desktop file of the editor starts, if any. """
    for directory in DESKTOP_DIRS:
        for pattern in patterns:
            for path in sorted(glob.glob(os.path.join(directory, pattern))):
                if 'url-handler' in path:
                    continue
                parser = configparser.RawConfigParser(strict=False, interpolation=None)
                try:
                    parser.read(path, encoding='utf-8')
                    command = parser.get('Desktop Entry', 'Exec')
                except (configparser.Error, OSError, UnicodeDecodeError):
                    continue
                words = [word for word in shlex.split(command) if not word.startswith('%')]
                if words and (os.path.isabs(words[0]) and os.access(words[0], os.X_OK) or shutil.which(words[0])):
                    return words[0]
    return None


@functools.cache
def find_editor():
    """ (name, program, arguments) of the editor installed here, or None. """
    for name, commands, patterns, arguments in EDITORS:
        program = next((shutil.which(command) for command in commands if shutil.which(command)), None)
        program = program or _desktop_command(patterns)
        if program:
            return name, program, arguments
    return None


def is_source_file(path):
    """ Only the Python files of Odoo and of its addons are ever opened. """
    if not path or not path.endswith('.py') or not os.path.isfile(path):
        return False
    path = os.path.realpath(path)
    roots = [*odoo.__path__, *odoo.addons.__path__]
    return any(path.startswith(os.path.join(os.path.realpath(root), '')) for root in roots)


@functools.cache
def _git_root(directory):
    while directory and directory != os.path.dirname(directory):
        if os.path.exists(os.path.join(directory, '.git')):
            return directory
        directory = os.path.dirname(directory)
    return None


@functools.cache
def _git_web(root):
    """ (web URL of the repository, commit) of a git checkout, if it has one. """
    def git(*args):
        result = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, timeout=5, check=False)
        return result.stdout.strip() if result.returncode == 0 else ''
    try:
        remote = git('remote', 'get-url', 'origin')
        commit = git('rev-parse', 'HEAD')
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r'^(?:https?://|ssh://)?(?:[^@/]+@)?([^/:]+)[:/](.+?)(?:\.git)?/?$', remote)
    if not match or not commit:
        return None
    return f'https://{match[1]}/{match[2]}', commit


def web_url(path, line):
    """ The page of ``path`` at ``line`` on its repository's website (GitHub, GitLab), if any. """
    root = _git_root(os.path.dirname(os.path.realpath(path)))
    web = root and _git_web(root)
    if not web:
        return None
    base, commit = web
    relative = os.path.relpath(os.path.realpath(path), root).replace(os.sep, '/')
    blob = '/-/blob/' if 'gitlab' in base else '/blob/'
    return f'{base}{blob}{commit}/{relative}#L{line}'


def open_code(path, line, remote_address):
    """ Open ``path`` at ``line``: in the local editor when the viewer sits at
    this machine, else give the web page of the code. """
    if not is_source_file(path):
        return {'error': 'not_source'}
    line = max(int(line or 1), 1)
    editor = find_editor() if remote_address in LOCAL_ADDRESSES else None
    if editor:
        name, program, arguments = editor
        try:
            subprocess.Popen(  # noqa: S603 - a known editor, on a checked source file
                [program, *arguments(path, line)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {'opened': name}
        except OSError:
            pass
    url = web_url(path, line)
    return {'url': url} if url else {'error': 'no_link', 'path': short_path(path), 'line': line}


def short_path(path):
    """ ``stock/models/stock_rule.py``: the path from the addons folder. """
    real = os.path.realpath(path)
    for root in [*odoo.addons.__path__, *odoo.__path__]:
        root = os.path.join(os.path.realpath(root), '')
        if real.startswith(root):
            return real[len(root):]
    return os.path.basename(path)

