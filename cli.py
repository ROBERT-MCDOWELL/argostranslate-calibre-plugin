import argparse
import glob
import os
import shutil
import sys
import threading
from calibre.utils.logging import Log
from calibre_plugins.argos_translate.client import ArgosClient, ArgosError
from typing import Optional
from calibre_plugins.argos_translate.jobs import WorkerSession, run_translation
from calibre_plugins.argos_translate.prefs import prefs
from calibre_plugins.argos_translate.runtime import ensure_runtime
FORMATS = ('.epub', '.azw3')
class Console:
    def __init__(self):
        self.tty = sys.stderr.isatty()
        self.columns = max(20, shutil.get_terminal_size((80, 20)).columns - 1)
        self.label = ''
        self.status = ''
        self.width = 0
        self.step = -1
    def start(self, label:str)->None:
        self.label = label if len(label) <= 40 else label[:37] + '...'
        self.status = ''
        self.step = -1
    def put(self, item:tuple)->None:
        fraction, message = item
        self.status = f"{self.label}: {fraction:6.1%} {message}"[:self.columns]
        if self.tty:
            self.draw()
        elif int(fraction * 10) != self.step:
            self.step = int(fraction * 10)
            print(self.status, file=sys.stderr, flush=True)
    def draw(self)->None:
        if self.tty and self.status:
            line = self.status.ljust(self.width)
            sys.stderr.write('\r' + line)
            sys.stderr.flush()
            self.width = len(line)
    def clear(self)->None:
        if self.tty and self.width:
            sys.stderr.write('\r' + ' ' * self.width + '\r')
            self.width = 0
    def finish(self)->None:
        if self.tty and self.width:
            sys.stderr.write('\n')
            self.width = 0
        self.status = ''
    def prints(self, level, *args, **kwargs)->None:
        self.clear()
        print(*args, sep=kwargs.get('sep', ' '), end=kwargs.get('end', '\n'), file=sys.stderr)
        self.draw()
    def flush(self)->None:
        sys.stderr.flush()
def make_log(console:Console)->Log:
    log = Log()
    log.outputs = [console]
    return log
def build_parser()->argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='calibre-debug -r "Argos Translate" --', fromfile_prefix_chars='@', description='Translate EPUB/AZW3 files offline with Argos Translate. Each run checks and installs what is missing: uv, the virtual environment (the active one, else ./python_env), argostranslate and the language models (./models/argos-translate). Output paths are printed on stdout, progress and logs go to stderr.')
    parser.add_argument('books', nargs='*', help='EPUB/AZW3 files or folders to translate; @list.txt reads paths from a file, one per line')
    parser.add_argument('-r', '--recursive', action='store_true', help='also look for books in subfolders of the given folders')
    parser.add_argument('--output-dir', help='write translations into this folder (subfolders are mirrored with -r) instead of next to each book')
    parser.add_argument('--overwrite', action='store_true', help='translate again even if the output file already exists')
    parser.add_argument('-t', '--to', dest='dst', help='target language code, e.g. fr')
    parser.add_argument('-f', '--from', dest='src', default='', help='source language code (default: read from each book)')
    parser.add_argument('-o', '--output', help='output file, single input only (default: <name>.<lang>.<ext> next to the input)')
    parser.add_argument('-m', '--mode', choices=['replace', 'bilingual'], default='replace')
    parser.add_argument('--allow-changes', action='store_true', help='if argostranslate has to be installed into an existing environment, install it even when packages already there would change version')
    parser.add_argument('--device', choices=['cpu', 'cuda', 'auto'], default=prefs['device'])
    parser.add_argument('--batch-size', type=int, default=prefs['batch_size'])
    parser.add_argument('--no-cache', action='store_true', help='neither read nor write the translation cache')
    parser.add_argument('--no-download', action='store_true', help='never download missing language models, fail instead')
    parser.add_argument('--list', action='store_true', help='list installed and downloadable language pairs and exit')
    return parser
def output_suffix(opts)->str:
    return f"{opts.dst}.bilingual" if opts.mode == 'bilingual' else opts.dst
def is_output_name(path:str, opts)->bool:
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.endswith(f".{opts.dst}") or stem.endswith(f".{opts.dst}.bilingual")
def expand_inputs(items:list[str], opts)->list:
    found:list = []
    for item in (entry.strip() for entry in items):
        if not item:
            continue
        if not os.path.isdir(item):
            found.append((item, None))
            continue
        pattern = os.path.join(glob.escape(item), '**', '*') if opts.recursive else os.path.join(glob.escape(item), '*')
        for path in sorted(glob.glob(pattern, recursive=opts.recursive)):
            if os.path.isfile(path) and os.path.splitext(path)[1].lower() in FORMATS and not is_output_name(path, opts):
                found.append((path, item))
    return found
def output_path(path:str, base:Optional[str], opts)->str:
    stem, ext = os.path.splitext(path)
    if opts.output:
        if os.path.splitext(opts.output)[1].lower() != ext.lower():
            raise ValueError(f"--output must keep the {ext} extension")
        return os.path.abspath(opts.output)
    name = f"{os.path.basename(stem)}.{output_suffix(opts)}{ext}"
    if not opts.output_dir:
        return os.path.abspath(os.path.join(os.path.dirname(path), name))
    sub = os.path.dirname(os.path.relpath(path, base)) if base else ''
    return os.path.abspath(os.path.join(opts.output_dir, sub, name))
def translate_file(path:str, out_path:str, opts, session:WorkerSession, console:Console, log:Log, label:str)->str:
    if not os.path.isfile(path):
        raise ValueError('not found')
    if os.path.splitext(path)[1].lower() not in FORMATS:
        raise ValueError('only EPUB and AZW3 are supported, convert it first with ebook-convert')
    if opts.src == opts.dst:
        raise ValueError(f"already in {opts.dst}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    task = dict(src_path=os.path.abspath(path), out_path=out_path, src=opts.src, dst=opts.dst, mode=opts.mode, root=os.getcwd(), allow_changes=opts.allow_changes, device=opts.device, batch_size=opts.batch_size, use_cache=prefs['use_cache'] and not opts.no_cache, auto_install=prefs['auto_install'] and not opts.no_download, session=session)
    console.start(label)
    try:
        return run_translation(task, notifications=console, abort=threading.Event(), log=log)
    finally:
        console.finish()
def list_pairs(opts, console:Console, log:Log)->int:
    console.start('checking')
    try:
        runtime = ensure_runtime(os.getcwd(), opts.allow_changes, console, threading.Event(), log)
        with ArgosClient(runtime.python, runtime.models, opts.device) as client:
            languages, pairs, available = client.languages(True)
    except Exception as e:
        console.finish()
        print(e, file=sys.stderr)
        return 1
    console.finish()
    def show(title:str, items:list)->None:
        print(title)
        for src, dst in items:
            print(f"  {src} -> {dst}\t{languages.get(src, src)} -> {languages.get(dst, dst)}")
        if not items:
            print('  (none)')
    show('Installed (including pairs routed through English):', pairs)
    show('Available for download, fetched automatically on first use:', [pair for pair in available if pair not in pairs])
    return 0
def main(argv:list[str])->int:
    parser = build_parser()
    opts = parser.parse_args(argv[1:] if argv[:1] == ['--'] else argv)
    console = Console()
    log = make_log(console)
    if opts.list:
        return list_pairs(opts, console, log)
    if not opts.books or not opts.dst:
        parser.error('give at least one book or folder and --to')
    books = expand_inputs(opts.books, opts)
    if not books:
        parser.error('no EPUB/AZW3 books found in the given paths')
    if opts.output and (len(books) > 1 or opts.output_dir):
        parser.error('--output needs exactly one input book and no --output-dir')
    session = WorkerSession()
    translated = skipped = failed = 0
    try:
        for index, (path, base) in enumerate(books, 1):
            label = f"[{index}/{len(books)}] {os.path.basename(path)}" if len(books) > 1 else os.path.basename(path)
            try:
                out_path = output_path(path, base, opts)
                if os.path.exists(out_path) and not opts.overwrite:
                    print(f"{path}: skipped, {out_path} already exists (use --overwrite)", file=sys.stderr)
                    skipped += 1
                    continue
                print(translate_file(path, out_path, opts, session, console, log, label), flush=True)
                translated += 1
            except Exception as e:
                print(f"{path}: {e}", file=sys.stderr)
                failed += 1
                if isinstance(e, ArgosError):
                    session.close()
    finally:
        session.close()
    if len(books) > 1:
        print(f"Batch done: {translated} translated, {skipped} skipped, {failed} failed", file=sys.stderr)
    return 1 if failed else 0
