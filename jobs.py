import os
from calibre_plugins.argos_translate.cache import TranslationCache
from calibre_plugins.argos_translate.client import ArgosClient, plugin_dir
from calibre_plugins.argos_translate.runtime import ensure_runtime
from calibre_plugins.argos_translate.translator import apply_segment, has_letters, normalize, prepare_document
def short_language(codes)->str:
    from calibre.utils.localization import lang_as_iso639_1
    for code in codes or []:
        short = lang_as_iso639_1(code)
        if short:
            return short
    return ''
def nav_names(container)->set:
    hrefs = container.opf_xpath('//opf:manifest/opf:item[contains(concat(" ", normalize-space(@properties), " "), " nav ")]/@href')
    return {container.href_to_name(href, container.opf_name) for href in hrefs}
class WorkerSession:
    def __init__(self):
        self.runtime = None
        self.client = None
        self.key = None
        self.pairs:set = set()
    def client_for(self, task:dict, notifications, abort, log)->ArgosClient:
        key = (task['root'], task['device'])
        if self.client is None or self.key != key:
            self.close()
            self.runtime = ensure_runtime(task['root'], task.get('allow_changes', False), notifications, abort, log)
            log(f"Argos runtime: {self.runtime.python}, models in {self.runtime.models}")
            self.client = ArgosClient(self.runtime.python, self.runtime.models, task['device'])
            self.key = key
        pair = (task['src'], task['dst'])
        if pair not in self.pairs:
            if task.get('auto_install', True):
                notifications.put((0.0, f"Checking the {task['src']} → {task['dst']} model, downloading it if missing"))
                installed = self.client.ensure(task['src'], task['dst'])
                if installed:
                    log(f"Downloaded Argos model(s): {', '.join(installed)}")
                    self.client.close()
                    self.client = None
                    self.client = ArgosClient(self.runtime.python, self.runtime.models, task['device'])
                    self.pairs = set()
            self.pairs.add(pair)
        return self.client
    def close(self)->None:
        if self.client is not None:
            self.client.close()
        self.client = None
        self.pairs = set()
def translate_texts(texts:list[str], task:dict, notifications, abort, log)->dict:
    cache = TranslationCache(os.path.join(plugin_dir(), 'cache.sqlite'), task['src'], task['dst']) if task['use_cache'] else None
    shared = task.get('session')
    session = shared or WorkerSession()
    try:
        done = cache.get_many(texts) if cache else {}
        todo = [text for text in texts if text not in done]
        log(f"{len(texts)} unique segments, {len(done)} cached, {len(todo)} to translate")
        if not todo:
            return done
        total = sum(len(text) for text in todo)
        sent = 0
        size = task['batch_size']
        client = session.client_for(task, notifications, abort, log)
        for start in range(0, len(todo), size):
            if abort.is_set():
                raise RuntimeError('Translation aborted')
            chunk = todo[start:start + size]
            fresh = {original: result for original, result in zip(chunk, client.translate(task['src'], task['dst'], chunk)) if result}
            done.update(fresh)
            if cache:
                cache.put_many(fresh)
            sent += sum(len(text) for text in chunk)
            notifications.put((sent / total, f"Translated {start + len(chunk)}/{len(todo)} segments"))
        return done
    finally:
        if shared is None:
            session.close()
        if cache:
            cache.close()
def run_translation(task:dict, notifications=None, abort=None, log=None)->str:
    from calibre.ebooks.oeb.polish.container import get_container
    from calibre.ebooks.oeb.polish.toc import commit_toc, get_toc
    notifications.put((0.0, 'Parsing book'))
    container = get_container(task['src_path'], log=log, tweak_mode=True)
    if not task['src']:
        task['src'] = short_language([el.text.strip() for el in container.opf_xpath('//dc:language') if el.text and el.text.strip()])
        if not task['src']:
            raise ValueError('book language unknown, set the source language explicitly (--from on the command line)')
        log(f"Source language from the book: {task['src']}")
    if task['src'] == task['dst']:
        raise ValueError(f"book is already in {task['dst']}")
    skip = nav_names(container) if task['mode'] == 'bilingual' else set()
    segments:list = []
    for name, _ in container.spine_names:
        if name in skip:
            continue
        found = prepare_document(container.parsed(name), task['mode'], task['src'], task['dst'])
        if found or task['mode'] == 'replace':
            container.dirty(name)
        segments.extend(found)
    toc = None
    toc_nodes:list = []
    if task['mode'] == 'replace':
        try:
            toc = get_toc(container)
            toc_nodes = [node for node in toc.iterdescendants() if node.title and has_letters(node.title)]
        except Exception:
            log.exception('Cannot read the table of contents, it will stay untranslated')
    texts = list(dict.fromkeys([segment.core for segment in segments] + [normalize(node.title) for node in toc_nodes]))
    log(f"{len(segments)} segments in {task['src_path']}")
    translated = translate_texts(texts, task, notifications, abort, log)
    for segment in segments:
        apply_segment(segment, translated.get(segment.core))
    if toc_nodes:
        for node in toc_nodes:
            node.title = translated.get(normalize(node.title)) or node.title
        try:
            commit_toc(container, toc, lang=task['dst'])
        except Exception:
            log.exception('Cannot write the translated table of contents')
    if task['mode'] == 'replace':
        languages = container.opf_xpath('//dc:language')
        if languages:
            languages[0].text = task['dst']
            container.dirty(container.opf_name)
    notifications.put((1.0, 'Writing book'))
    container.commit(task['out_path'])
    return task['out_path']
