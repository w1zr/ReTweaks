# ui/widgets/theme_maker.py
"""Theme maker (v1.4.3): pick every color, preview it live, save it, and share it as a code."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton)

from core import themes as T
from ui.widgets.common import Card, label, set_role


class ThemeMakerCard(Card):
    def __init__(self, ctx, on_saved=None, parent=None):
        super().__init__("Theme maker", parent)
        self.ctx = ctx
        self.on_saved = on_saved or (lambda: None)
        self.colors = T.editable_colors(ctx.settings.get("theme", "Midnight"))
        self.previewing = False

        self.body.addWidget(label("Pick every color yourself. Preview shows it on the whole app right away; "
                                  "nothing is saved until you press Save.", "muted", wrap=True))
        row = QHBoxLayout()
        row.addWidget(label("Start from", "cardLine"))
        self.base = QComboBox()
        self.base.addItems(list(T.THEMES.keys()) + T.custom_theme_names())
        self.base.setCurrentText(ctx.settings.get("theme", "Midnight"))
        self.base.currentTextChanged.connect(self._load_base)
        row.addWidget(self.base)
        row.addSpacing(16)
        row.addWidget(label("Name", "cardLine"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("My theme")
        self.name.setMaxLength(32)
        self.name.setMaximumWidth(200)
        row.addWidget(self.name)
        row.addStretch(1)
        self.body.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.swatches = {}
        for i, (key, title) in enumerate(T.EDITABLE):
            b = QPushButton()
            b.setFixedSize(34, 24)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(f"Change {title.lower()}")
            b.clicked.connect(lambda _c=False, k=key: self._pick(k))
            text = QLabel()
            text.setObjectName("cardLine")
            r, c = divmod(i, 5)
            cell = QHBoxLayout()
            cell.setSpacing(8)
            cell.addWidget(b)
            col = QLabel(title)
            col.setObjectName("cardLine")
            cell.addWidget(col)
            cell.addWidget(text)
            cell.addStretch(1)
            grid.addLayout(cell, r, c)
            self.swatches[key] = (b, text)
        self.body.addLayout(grid)

        self.contrast = label("", "muted", wrap=True)
        self.body.addWidget(self.contrast)

        row = QHBoxLayout()
        self.b_preview = QPushButton("Preview")
        self.b_preview.clicked.connect(self.preview)
        self.b_discard = QPushButton("Discard preview")
        self.b_discard.clicked.connect(self.discard)
        self.b_save = set_role(QPushButton("Save theme"), "primary")
        self.b_save.clicked.connect(self.save)
        self.b_copy = QPushButton("Copy share code")
        self.b_copy.clicked.connect(self.copy_code)
        self.b_import = QPushButton("Import code…")
        self.b_import.clicked.connect(self.import_code)
        self.b_delete = QPushButton("Delete this theme")
        self.b_delete.clicked.connect(self.delete)
        for b in (self.b_preview, self.b_discard, self.b_save, self.b_copy, self.b_import, self.b_delete):
            row.addWidget(b)
        row.addStretch(1)
        self.body.addLayout(row)
        self.msg = label("", "muted", wrap=True)
        self.body.addWidget(self.msg)
        self._refresh()

    # ------------------------------------------------------------ editing

    def _load_base(self, name):
        if not name:
            return
        self.colors = T.editable_colors(name)
        if name in T.custom_theme_names():
            self.name.setText(name)
        self._refresh()

    def _pick(self, key):
        start = QColor(self.colors[key])
        c = QColorDialog.getColor(start, self, f"Choose {dict(T.EDITABLE)[key].lower()}")
        if c.isValid():
            self.colors[key] = c.name().lower()
            self._refresh()
            if self.previewing:
                self.ctx.preview_theme(self.colors)

    def _refresh(self):
        for key, (b, text) in self.swatches.items():
            v = self.colors[key]
            b.setStyleSheet(f"QPushButton {{ background-color: {v}; border: 1px solid #808080; border-radius: 6px; }}")
            text.setText(v)
        c = self.colors
        ratios = [("Text on background", T.contrast(c["text"], c["bg"])),
                  ("Text on cards", T.contrast(c["text"], c["card"])),
                  ("Secondary text on cards", T.contrast(c["subtext"], c["card"]))]
        low = [f"{n} {r:.1f}:1" for n, r in ratios if r < 4.5]
        if low:
            self.contrast.setObjectName("warn")
            self.contrast.setText("Hard to read: " + ", ".join(low) + ". 4.5:1 or more is comfortable.")
        else:
            self.contrast.setObjectName("muted")
            self.contrast.setText("Readability: good (all text has at least 4.5:1 contrast).")
        self.contrast.style().unpolish(self.contrast)
        self.contrast.style().polish(self.contrast)
        self.b_delete.setEnabled(self._name() in T.custom_theme_names())

    def _name(self):
        return T.clean_theme_name(self.name.text())

    # ------------------------------------------------------------ actions

    def preview(self):
        self.previewing = True
        self.ctx.preview_theme(self.colors)
        self.msg.setText("Previewing. Press Save theme to keep it, or Discard preview to go back.")

    def discard(self):
        self.previewing = False
        self.ctx.end_preview()
        self.msg.setText("Back to your saved theme.")

    def save(self):
        name = self._name()
        if not name:
            self.msg.setText("Give your theme a name first.")
            return
        if name in T.THEMES or name == "__preview__":
            self.msg.setText(f"\"{name}\" is a built-in theme name. Pick another name.")
            return
        if name in T.custom_theme_names() and QMessageBox.question(
                self, "Theme maker", f"Replace your saved theme \"{name}\"?") != QMessageBox.Yes:
            return
        self.previewing = False
        self.ctx.save_custom_theme(name, self.colors)
        self.ctx.log_action("Theme maker", f"Save theme \"{name}\"", "Saved")
        self.msg.setText(f"Saved \"{name}\" and switched to it. Find it in the Theme list any time.")
        self._reload_lists(name)

    def delete(self):
        name = self._name()
        if name not in T.custom_theme_names():
            return
        if QMessageBox.question(self, "Theme maker", f"Delete your theme \"{name}\"?") != QMessageBox.Yes:
            return
        self.ctx.delete_custom_theme(name)
        self.ctx.log_action("Theme maker", f"Delete theme \"{name}\"", "Deleted")
        self.msg.setText(f"Deleted \"{name}\".")
        self._reload_lists(self.ctx.settings.get("theme", "Midnight"))

    def copy_code(self):
        code = T.export_code(self._name() or "My theme", self.colors)
        QGuiApplication.clipboard().setText(code)
        self.msg.setText("Share code copied. Anyone can paste it into Import code… in their RETWEAKS.")

    def import_code(self):
        code, ok = QInputDialog.getText(self, "Import theme", "Paste a RETWEAKS theme code (starts with RYT1-):")
        if not ok or not code.strip():
            return
        good, name_or_msg, colors = T.parse_code(code)
        if not good:
            self.msg.setText(name_or_msg)
            return
        self.colors = colors
        name = name_or_msg if name_or_msg not in T.THEMES else name_or_msg + " (shared)"
        self.name.setText(name)
        self._refresh()
        self.preview()
        self.msg.setText(f"Imported \"{name}\" and previewing it. Press Save theme to keep it.")

    def _reload_lists(self, current):
        self.base.blockSignals(True)
        self.base.clear()
        self.base.addItems(list(T.THEMES.keys()) + T.custom_theme_names())
        self.base.setCurrentText(current)
        self.base.blockSignals(False)
        self._refresh()
        self.on_saved()
