import os
from qt.core import QApplication, QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QSpinBox, Qt, QWidget
from calibre.gui2 import error_dialog, info_dialog
from calibre_plugins.argos_translate.client import ArgosClient, plugin_dir
from calibre_plugins.argos_translate.prefs import prefs
from calibre_plugins.argos_translate.runtime import locate, ready_runtime
NOT_READY = 'The Argos environment does not exist yet. The first translation job creates it automatically (uv, Python 3.12, argostranslate) and downloads the language models it needs. Until then, type the target language code in the translate dialog.'
def refresh_languages(parent, device:str, update:bool=False, quiet:bool=False)->bool:
    error = ''
    runtime = None
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        runtime = ready_runtime(plugin_dir())
        if runtime is not None:
            with ArgosClient(runtime.python, runtime.models, device) as client:
                languages, pairs, available = client.languages(update)
            prefs['languages'] = languages
            prefs['pairs'] = pairs
            prefs['available'] = available
    except Exception as e:
        error = str(e)
    finally:
        QApplication.restoreOverrideCursor()
    if runtime is None:
        if not quiet:
            info_dialog(parent, 'Argos Translate', NOT_READY, show=True)
        return False
    if error:
        if not quiet:
            error_dialog(parent, 'Argos Translate', 'Could not query the Argos languages.', det_msg=error, show=True)
        return False
    return True
class ConfigWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        layout = QFormLayout(self)
        env_dir, models = locate(plugin_dir())
        where = QLabel(f"Environment: {env_dir}\nModels: {os.path.join(models, 'argos-translate')}\nBoth are created automatically by the first translation job.", self)
        where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        where.setWordWrap(True)
        layout.addRow(where)
        self.device_combo = QComboBox(self)
        self.device_combo.addItems(['cpu', 'cuda', 'auto'])
        self.device_combo.setCurrentText(prefs['device'])
        layout.addRow('Device:', self.device_combo)
        self.batch_spin = QSpinBox(self)
        self.batch_spin.setRange(1, 256)
        self.batch_spin.setValue(prefs['batch_size'])
        layout.addRow('Segments per batch:', self.batch_spin)
        self.cache_check = QCheckBox('Reuse previous translations (makes interrupted jobs resumable)', self)
        self.cache_check.setChecked(prefs['use_cache'])
        layout.addRow(self.cache_check)
        self.download_check = QCheckBox('Download missing language models automatically when a job needs them', self)
        self.download_check.setChecked(prefs['auto_install'])
        layout.addRow(self.download_check)
        test = QPushButton('Test worker and list installed pairs', self)
        test.clicked.connect(self.test)
        layout.addRow(test)
        clear = QPushButton('Clear translation cache', self)
        clear.clicked.connect(self.clear_cache)
        layout.addRow(clear)
    def test(self)->None:
        if refresh_languages(self, self.device_combo.currentText()):
            pairs = '\n'.join(f"{a} → {b}" for a, b in prefs['pairs']) or 'none yet'
            info_dialog(self, 'Argos Translate', f"Worker OK, {len(prefs['pairs'])} pair(s) installed. Missing pairs are downloaded on first use when enabled below.", det_msg=pairs, show=True)
    def clear_cache(self)->None:
        path = os.path.join(plugin_dir(), 'cache.sqlite')
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            error_dialog(self, 'Argos Translate', 'Could not clear the cache, is a translation running?', det_msg=str(e), show=True)
            return
        info_dialog(self, 'Argos Translate', 'Translation cache cleared.', show=True)
    def save_settings(self)->None:
        prefs['device'] = self.device_combo.currentText()
        prefs['batch_size'] = self.batch_spin.value()
        prefs['use_cache'] = self.cache_check.isChecked()
        prefs['auto_install'] = self.download_check.isChecked()
