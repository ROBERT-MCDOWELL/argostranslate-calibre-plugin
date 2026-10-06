from qt.core import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QPushButton, QTimer
from calibre.gui2 import error_dialog
from calibre_plugins.argos_translate.config import refresh_languages
from calibre_plugins.argos_translate.prefs import prefs
MODES = [('replace', 'Replace text with translation'), ('bilingual', 'Bilingual: original followed by translation')]
def select_data(combo, value)->None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
class TranslateDialog(QDialog):
    def __init__(self, parent, count:int):
        QDialog.__init__(self, parent)
        self.setWindowTitle(f"Argos Translate: {count} book(s)")
        layout = QFormLayout(self)
        self.src_combo = QComboBox(self)
        self.dst_combo = QComboBox(self)
        self.dst_combo.setEditable(True)
        self.dst_combo.lineEdit().setPlaceholderText('language code, e.g. fr')
        self.mode_combo = QComboBox(self)
        for key, label in MODES:
            self.mode_combo.addItem(label, key)
        select_data(self.mode_combo, prefs['mode'])
        refresh = QPushButton('Refresh language list', self)
        refresh.clicked.connect(self.refresh)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow('From:', self.src_combo)
        layout.addRow('To:', self.dst_combo)
        layout.addRow('Mode:', self.mode_combo)
        layout.addRow(refresh)
        layout.addRow(buttons)
        self.populate()
        if not prefs['pairs'] and not prefs['available']:
            QTimer.singleShot(0, self.auto_refresh)
    def populate(self)->None:
        names = prefs['languages']
        installed = [tuple(pair) for pair in prefs['pairs']]
        offered = installed + ([tuple(pair) for pair in prefs['available']] if prefs['auto_install'] else [])
        def fill(combo, codes:set, ready:set)->None:
            for code in sorted(codes, key=lambda code: names.get(code, code).lower()):
                combo.addItem(f"{names.get(code, code)} ({code})" + ('' if code in ready else ' - download'), code)
        self.src_combo.clear()
        self.dst_combo.clear()
        self.src_combo.addItem('Book language (from metadata)', '')
        fill(self.src_combo, {pair[0] for pair in offered}, {pair[0] for pair in installed})
        fill(self.dst_combo, {pair[1] for pair in offered}, {pair[1] for pair in installed})
        select_data(self.src_combo, prefs['src'])
        select_data(self.dst_combo, prefs['dst'])
    def refresh(self)->None:
        if refresh_languages(self, prefs['device'], update=True):
            self.populate()
    def auto_refresh(self)->None:
        if refresh_languages(self, prefs['device'], update=True, quiet=True):
            self.populate()
    @property
    def src(self)->str:
        return self.src_combo.currentData() or ''
    @property
    def dst(self)->str:
        index = self.dst_combo.currentIndex()
        text = self.dst_combo.currentText().strip()
        if index >= 0 and text == self.dst_combo.itemText(index):
            return self.dst_combo.itemData(index) or ''
        return text.lower()
    @property
    def mode(self)->str:
        return self.mode_combo.currentData() or 'replace'
    def accept(self)->None:
        if not self.dst:
            error_dialog(self, 'Argos Translate', 'Choose a target language, or type its code (e.g. fr).', show=True)
            return
        prefs['src'] = self.src
        prefs['dst'] = self.dst
        prefs['mode'] = self.mode
        QDialog.accept(self)
