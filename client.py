import json
import os
import shutil
import subprocess
from typing import Optional
from calibre.constants import cache_dir, isfrozen, iswindows
class ArgosError(Exception):
    pass
def plugin_dir()->str:
    path = os.path.join(cache_dir(), 'argos_translate')
    os.makedirs(path, exist_ok=True)
    return path
def worker_script()->str:
    path = os.path.join(plugin_dir(), 'worker.py')
    data = get_resources('worker.py')
    try:
        with open(path, 'rb') as f:
            current = f.read()
    except OSError:
        current = None
    if current != data:
        with open(path, 'wb') as f:
            f.write(data)
    return path
def clean_env()->dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith('PYTHON')}
    if isfrozen:
        for key in ('LD_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'SSL_CERT_FILE', 'OPENSSL_MODULES', 'OPENSSL_ENGINES', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH'):
            env.pop(key, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env
def worker_env(device:str, models:str)->dict:
    env = clean_env()
    env['PYTHONUNBUFFERED'] = '1'
    env['ARGOS_DEVICE_TYPE'] = device
    if models:
        env['XDG_CACHE_HOME'] = models
        env['XDG_DATA_HOME'] = models
        env['ARGOS_PACKAGES_DIR'] = os.path.join(models, 'argos-translate', 'packages')
    return env
class ArgosClient:
    def __init__(self, python:str, models:str='', device:str='cpu'):
        executable = shutil.which(python) if python else None
        if not executable:
            raise ArgosError(f"Python interpreter not found: {python!r}")
        self.log_path = os.path.join(plugin_dir(), 'worker.log')
        mode = 'w' if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > 2_000_000 else 'a'
        self.log_file = open(self.log_path, mode, encoding='utf-8')
        try:
            self.proc = subprocess.Popen([executable, '-u', worker_script()], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log_file, env=worker_env(device, models), text=True, encoding='utf-8', bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW if iswindows else 0)
        except OSError as e:
            self.log_file.close()
            raise ArgosError(f"Cannot start {executable}: {e}") from e
        try:
            self.read()
        except Exception:
            self.close()
            raise
    def __enter__(self):
        return self
    def __exit__(self, *exc)->None:
        self.close()
    def log_tail(self, size:int=4000)->str:
        try:
            self.log_file.flush()
            with open(self.log_path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - size))
                return f.read().decode('utf-8', 'replace')
        except (OSError, ValueError):
            return ''
    def exit_code(self)->Optional[int]:
        try:
            return self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return None
    def read(self)->dict:
        line = self.proc.stdout.readline()
        if not line:
            raise ArgosError(f"Argos worker exited with code {self.exit_code()}\n{self.log_tail()}")
        try:
            reply = json.loads(line)
        except ValueError as e:
            raise ArgosError(f"Invalid worker output: {line[:200]!r}") from e
        if not reply.get('ok'):
            raise ArgosError(f"{reply.get('error', 'unknown worker error')}\n{self.log_tail()}")
        return reply
    def request(self, message:dict)->dict:
        try:
            self.proc.stdin.write(json.dumps(message) + '\n')
            self.proc.stdin.flush()
        except OSError as e:
            raise ArgosError(f"Argos worker is gone: {e}\n{self.log_tail()}") from e
        return self.read()
    def languages(self, update:bool=False)->tuple:
        reply = self.request(dict(cmd='languages', update=update))
        return reply['languages'], reply['pairs'], reply.get('available', [])
    def ensure(self, src:str, dst:str)->list:
        return self.request(dict(cmd='ensure', src=src, dst=dst))['installed']
    def translate(self, src:str, dst:str, texts:list[str])->list:
        return self.request(dict(cmd='translate', src=src, dst=dst, texts=texts))['texts']
    def close(self)->None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait()
        self.proc.stdout.close()
        self.log_file.close()
