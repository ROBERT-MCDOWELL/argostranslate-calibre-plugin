import os
import shutil
from typing import Optional
from qt.core import QDialog, QMenu
from calibre.ebooks.metadata import title_sort
from calibre.gui2 import Dispatcher, error_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob
from calibre.ptempfile import PersistentTemporaryDirectory
from calibre.utils.localization import canonicalize_lang
from calibre_plugins.argos_translate.dialog import TranslateDialog
from calibre_plugins.argos_translate.jobs import run_translation, short_language
from calibre_plugins.argos_translate.prefs import prefs
from calibre_plugins.argos_translate.client import plugin_dir
FORMATS = ['EPUB', 'AZW3']
class ArgosTranslateAction(InterfaceAction):
    name = 'Argos Translate'
    action_spec = ('Translate', None, 'Translate the selected books offline with Argos Translate', None)
    action_type = 'current'
    dont_add_to = frozenset(['context-menu-device', 'toolbar-device', 'menubar-device'])
    def genesis(self)->None:
        self.qaction.setIcon(get_icons('images/icon.png', 'Argos Translate'))
        self.qaction.triggered.connect(self.translate_selected)
        menu = QMenu(self.gui)
        menu.addAction('Translate selected books…', self.translate_selected)
        menu.addAction('Settings…', self.show_settings)
        self.qaction.setMenu(menu)
    def show_settings(self)->None:
        self.interface_action_base_plugin.do_user_config(self.gui)
    def check(self, fmt:Optional[str], src:str, dst:str, pairs:set)->str:
        if fmt is None:
            return 'no EPUB or AZW3 format, convert it first'
        if not src:
            return 'book language unknown, pick a source language explicitly'
        if src == dst:
            return f"already in {dst}"
        if pairs and (src, dst) not in pairs:
            return f"pair {src} → {dst} not installed (refresh languages if you just installed it)"
        return ''
    def translate_selected(self)->None:
        book_ids = list(self.gui.library_view.get_selected_ids())
        if not book_ids:
            error_dialog(self.gui, 'Argos Translate', 'Select at least one book first.', show=True)
            return
        dialog = TranslateDialog(self.gui, len(book_ids))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        db = self.gui.current_db.new_api
        pairs = set() if prefs['auto_install'] else {tuple(pair) for pair in prefs['pairs']}
        skipped:list = []
        started = 0
        for book_id in book_ids:
            mi = db.get_metadata(book_id)
            formats = db.formats(book_id) or ()
            fmt = next((f for f in FORMATS if f in formats), None)
            src = dialog.src or short_language(mi.languages)
            problem = self.check(fmt, src, dialog.dst, pairs)
            if problem:
                skipped.append(f"{mi.title}: {problem}")
                continue
            self.start_job(book_id, mi.title, fmt, src, dialog.dst, dialog.mode)
            started += 1
        if started:
            self.gui.status_bar.show_message(f"Argos Translate: {started} job(s) queued", 5000)
        if skipped:
            error_dialog(self.gui, 'Argos Translate', f"{len(skipped)} book(s) skipped.", det_msg='\n'.join(skipped), show=True)
    def start_job(self, book_id:int, title:str, fmt:str, src:str, dst:str, mode:str)->None:
        db = self.gui.current_db.new_api
        tdir = PersistentTemporaryDirectory('_argos')
        src_path = os.path.join(tdir, f"source.{fmt.lower()}")
        shutil.copyfile(db.format_abspath(book_id, fmt), src_path)
        task = dict(library_id=db.library_id, book_id=book_id, tdir=tdir, src_path=src_path, out_path=os.path.join(tdir, f"translated.{fmt.lower()}"), src=src, dst=dst, mode=mode, root=plugin_dir(), allow_changes=False, device=prefs['device'], batch_size=prefs['batch_size'], use_cache=prefs['use_cache'], auto_install=prefs['auto_install'])
        job = ThreadedJob('argos_translate', f"Translate {title} ({src} → {dst})", run_translation, (task,), {}, Dispatcher(self.job_done), max_concurrent_count=1, killable=True)
        job.argos_task = task
        self.gui.job_manager.run_threaded_job(job)
    def job_done(self, job)->None:
        task = job.argos_task
        try:
            if job.failed:
                self.gui.job_exception(job, dialog_title='Argos Translate failed')
                return
            if self.gui.current_db.new_api.library_id != task['library_id']:
                error_dialog(self.gui, 'Argos Translate', 'The library was switched during translation, so the result was not added. Re-running is fast: every segment is cached.', show=True)
                return
            self.add_translation(task)
        finally:
            shutil.rmtree(task['tdir'], ignore_errors=True)
    def add_translation(self, task:dict)->None:
        legacy = self.gui.current_db
        db = legacy.new_api
        mi = db.get_metadata(task['book_id'])
        bilingual = task['mode'] == 'bilingual'
        mi.title = f"{mi.title} [{task['src']}+{task['dst']}]" if bilingual else f"{mi.title} [{task['dst']}]"
        mi.title_sort = title_sort(mi.title)
        mi.languages = [canonicalize_lang(code) or code for code in ([task['src'], task['dst']] if bilingual else [task['dst']])]
        new_id = legacy.import_book(mi, [task['out_path']])
        cover = db.cover(task['book_id'])
        if cover:
            db.set_cover({new_id: cover})
        model = self.gui.library_view.model()
        model.books_added(1)
        model.refresh_ids([new_id])
        self.gui.tags_view.recount()
        self.gui.status_bar.show_message(f"Argos Translate: added {mi.title}", 5000)
