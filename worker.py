import json
import os
import sys
import traceback
def open_channel():
    channel = os.fdopen(os.dup(1), 'w', encoding='utf-8', buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return channel
def send(channel, **message)->None:
    channel.write(json.dumps(message) + '\n')
    channel.flush()
def find_package(packages:list, src:str, dst:str):
    return next((item for item in packages if item.from_code == src and item.to_code == dst), None)
def has_route(packages:list, src:str, dst:str)->bool:
    if find_package(packages, src, dst) is not None:
        return True
    return 'en' not in (src, dst) and find_package(packages, src, 'en') is not None and find_package(packages, 'en', dst) is not None
def plan_route(packages:list, src:str, dst:str)->list:
    direct = find_package(packages, src, dst)
    if direct is not None:
        return [direct]
    if 'en' in (src, dst):
        return []
    legs = [find_package(packages, src, 'en'), find_package(packages, 'en', dst)]
    return legs if all(leg is not None for leg in legs) else []
def available_packages(package, update:bool)->list:
    if update:
        try:
            package.update_package_index()
        except Exception:
            traceback.print_exc()
    try:
        return package.get_available_packages()
    except Exception:
        traceback.print_exc()
        return []
def ensure_pair(src:str, dst:str)->list:
    from argostranslate import package
    installed = package.get_installed_packages()
    if has_route(installed, src, dst):
        return []
    plan = plan_route(available_packages(package, False), src, dst) or plan_route(available_packages(package, True), src, dst)
    if not plan:
        raise LookupError(f"no Argos model available for {src}->{dst}, not even through English")
    done:list = []
    for item in plan:
        if find_package(installed, item.from_code, item.to_code) is None:
            print(f"downloading {item.from_code}->{item.to_code}", file=sys.stderr, flush=True)
            package.install_from_path(item.download())
            done.append(f"{item.from_code}->{item.to_code}")
    return done
def list_languages(argos, update:bool)->dict:
    from argostranslate import package
    languages = argos.get_installed_languages()
    pairs = [[a.code, b.code] for a in languages for b in languages if a.code != b.code and a.get_translation(b) is not None]
    names = {lang.code: lang.name for lang in languages}
    available:list = []
    for item in available_packages(package, update):
        names.setdefault(item.from_code, getattr(item, 'from_name', item.from_code))
        names.setdefault(item.to_code, getattr(item, 'to_name', item.to_code))
        available.append([item.from_code, item.to_code])
    return dict(languages=names, pairs=pairs, available=available)
class Translator:
    def __init__(self, argos):
        self.argos = argos
        self.loaded:dict = {}
    def get(self, src:str, dst:str):
        key = (src, dst)
        if key not in self.loaded:
            languages = {lang.code: lang for lang in self.argos.get_installed_languages()}
            translation = languages[src].get_translation(languages[dst]) if src in languages and dst in languages else None
            if translation is None:
                raise LookupError(f"no installed Argos package for {src}->{dst}")
            self.loaded[key] = translation
        return self.loaded[key]
    def translate(self, src:str, dst:str, texts:list[str])->list:
        translation = self.get(src, dst)
        out:list = []
        for text in texts:
            try:
                out.append(translation.translate(text))
            except Exception as e:
                print(f"segment failed: {e!r}: {text[:80]!r}", file=sys.stderr, flush=True)
                out.append(None)
        return out
def main()->None:
    channel = open_channel()
    try:
        from argostranslate import translate as argos
    except Exception as e:
        traceback.print_exc()
        send(channel, ok=False, error=f"cannot import argostranslate in {sys.executable}: {e!r}. The plugin installs it automatically before a translation, see the log above if that step failed.")
        return
    translator = Translator(argos)
    send(channel, ok=True, ready=True, python=sys.version.split()[0])
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if request['cmd'] == 'languages':
                send(channel, ok=True, **list_languages(argos, bool(request.get('update'))))
            elif request['cmd'] == 'ensure':
                send(channel, ok=True, installed=ensure_pair(request['src'], request['dst']))
            elif request['cmd'] == 'translate':
                send(channel, ok=True, texts=translator.translate(request['src'], request['dst'], request['texts']))
            else:
                send(channel, ok=False, error=f"unknown command {request['cmd']!r}")
        except Exception as e:
            traceback.print_exc()
            send(channel, ok=False, error=repr(e))
if __name__ == '__main__':
    main()
