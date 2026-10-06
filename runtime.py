import os
import platform
import shlex
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from typing import NamedTuple, Optional
from calibre.constants import ismacos, iswindows
from calibre_plugins.argos_translate.client import clean_env, plugin_dir
PYTHON_VERSION = '3.12'
UV_RELEASES = 'https://github.com/astral-sh/uv/releases/latest/download/'
NO_WINDOW = subprocess.CREATE_NO_WINDOW if iswindows else 0
class Runtime(NamedTuple):
    python:str
    models:str
def env_python(env_dir:str)->str:
    return os.path.join(env_dir, 'Scripts', 'python.exe') if iswindows else os.path.join(env_dir, 'bin', 'python')
def locate(root:str)->tuple:
    active = os.environ.get('VIRTUAL_ENV', '')
    env_dir = active if active and os.path.isfile(env_python(active)) else os.path.join(root, 'python_env')
    return env_dir, os.path.join(root, 'models')
def has_module(python:str, name:str)->bool:
    try:
        proc = subprocess.run([python, '-c', f"import importlib.util,sys;sys.exit(0 if importlib.util.find_spec({name!r}) else 1)"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=clean_env(), creationflags=NO_WINDOW, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0
def ready_runtime(root:str)->Optional[Runtime]:
    env_dir, models = locate(root)
    python = env_python(env_dir)
    return Runtime(python, models) if os.path.isfile(python) and has_module(python, 'argostranslate') else None
def package_changes(lines:list[str])->list[str]:
    removed:dict = {}
    added:dict = {}
    for line in lines:
        mark, _, spec = line.strip().partition(' ')
        if mark in ('-', '+') and '==' in spec:
            name, _, version = spec.partition('==')
            (removed if mark == '-' else added)[name.lower()] = version
    return [f"{name} {version} -> {added.get(name, 'removed')}" for name, version in sorted(removed.items())]
def run_command(args:list[str], log, abort)->list[str]:
    log('> ' + (subprocess.list2cmdline(args) if iswindows else shlex.join(args)))
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=clean_env(), text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
    lines:list = []
    try:
        for line in proc.stdout:
            if line.strip():
                lines.append(line.rstrip())
                log(line.rstrip())
            if abort.is_set():
                proc.kill()
                raise RuntimeError('Aborted')
    finally:
        proc.stdout.close()
        code = proc.wait()
    if code:
        raise RuntimeError(f"'{os.path.basename(args[0])} {args[1]}' failed with exit code {code}, see the log above")
    return lines
def uv_asset()->str:
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'x64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}.get(machine)
    if not arch:
        raise RuntimeError(f"no prebuilt uv for {machine}, install uv yourself and put it on PATH")
    if iswindows:
        return f"uv-{arch}-pc-windows-msvc.zip"
    if ismacos:
        return f"uv-{arch}-apple-darwin.tar.gz"
    return f"uv-{arch}-unknown-linux-gnu.tar.gz"
def find_uv(log)->str:
    found = shutil.which('uv')
    if found:
        return found
    folder = os.path.join(plugin_dir(), 'uv')
    exe = os.path.join(folder, 'uv.exe' if iswindows else 'uv')
    if os.path.isfile(exe):
        return exe
    asset = uv_asset()
    log(f"uv not found, downloading {UV_RELEASES}{asset}")
    os.makedirs(folder, exist_ok=True)
    archive = os.path.join(folder, asset)
    with urllib.request.urlopen(UV_RELEASES + asset, timeout=120) as response, open(archive, 'wb') as f:
        shutil.copyfileobj(response, f)
    try:
        name = os.path.basename(exe)
        if asset.endswith('.zip'):
            with zipfile.ZipFile(archive) as z:
                member = next((m for m in z.namelist() if os.path.basename(m) == name), None)
                if member is None:
                    raise RuntimeError(f"{asset} does not contain {name}")
                with z.open(member) as src, open(exe + '.part', 'wb') as dst:
                    shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(archive) as t:
                member = next((m for m in t.getmembers() if m.isfile() and os.path.basename(m.name) == name), None)
                if member is None:
                    raise RuntimeError(f"{asset} does not contain {name}")
                with t.extractfile(member) as src, open(exe + '.part', 'wb') as dst:
                    shutil.copyfileobj(src, dst)
            os.chmod(exe + '.part', 0o755)
        os.replace(exe + '.part', exe)
    finally:
        os.remove(archive)
    log(f"uv installed at {exe}")
    return exe
def ensure_runtime(root:str, allow_changes:bool, notifications, abort, log)->Runtime:
    env_dir, models = locate(root)
    python = env_python(env_dir)
    existed = os.path.isfile(python)
    if not existed:
        if os.path.isdir(env_dir) and os.listdir(env_dir):
            raise RuntimeError(f"{env_dir} exists but is not a usable Python virtual environment, move it away and run again")
        notifications.put((0.0, f"Creating {env_dir}"))
        run_command([find_uv(log), 'venv', '--python', PYTHON_VERSION, env_dir], log, abort)
    if not has_module(python, 'argostranslate'):
        uv = find_uv(log)
        if existed:
            notifications.put((0.0, 'Checking what installing argostranslate would change'))
            changes = package_changes(run_command([uv, 'pip', 'install', '--dry-run', '--python', python, 'argostranslate'], log, abort))
            if changes and not allow_changes:
                raise RuntimeError(f"installing argostranslate into {env_dir} would change packages it already uses:\n  " + '\n  '.join(changes) + '\nNothing was installed. Run again with --allow-changes if the application owning this environment works with those versions.')
        notifications.put((0.0, 'Installing argostranslate, the first time takes a few minutes'))
        run_command([uv, 'pip', 'install', '--python', python, 'argostranslate'], log, abort)
    return Runtime(python, models)
