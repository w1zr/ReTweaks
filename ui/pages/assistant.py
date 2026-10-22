# ui/pages/assistant.py
"""AI Assistant: advice-only chat (Google Gemini, bring your own free key)."""

import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QTextBrowser, QVBoxLayout, QWidget)

from core import ai_assistant as AI
from ui.widgets.common import Card, Notice, Page, label, set_role

STARTERS = ["Why does Fortnite stutter on my PC?", "Is my GPU driver up to date?",
            "What should I fix first?"]


class ChatInput(QPlainTextEdit):
    """Enter sends, Shift+Enter makes a new line."""
    submitted = Signal()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(e)


class Bubble(QFrame):
    """One chat message. User text is plain; assistant text is rendered Markdown."""

    def __init__(self, role, text, theme, parent=None):
        super().__init__(parent)
        self.role = role
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.view = QTextBrowser()
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setOpenExternalLinks(True)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.viewport().setAutoFillBackground(False)
        self.view.setStyleSheet("background: transparent; border: none;")
        if role == "model":
            self.view.setMarkdown(text)
        else:
            self.view.setPlainText(text)
        self.view.document().documentLayout().documentSizeChanged.connect(lambda _s: self._fit())
        lay.addWidget(self.view)
        self.apply_theme(theme)

    def apply_theme(self, t):
        user = self.role == "user"
        bg = t["accent"] if user else t["card"]
        fg = t["on_accent"] if user else t["text"]
        self.setObjectName("chatBubble")
        self.setStyleSheet(
            f"QFrame#chatBubble {{ background: {bg}; border: 1px solid {t['border']}; "
            f"border-radius: 12px; }} QTextBrowser {{ color: {fg}; }}")

    def _fit(self):
        doc = self.view.document()
        doc.setTextWidth(max(self.view.viewport().width(), 50))
        self.view.setFixedHeight(int(doc.size().height()) + 6)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._fit)


class AssistantPage(Page):
    title = "AI Assistant"
    subtitle = "Ask about your PC, performance and games. It gives advice only; it never changes anything."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.history = []          # [{"role": "user"|"model", "text": ...}]
        self._bubbles = []
        self._req = 0              # id of the request whose result we still want
        self._pending = False
        self._thinking = None
        self._models = list(AI.FALLBACK_MODELS)
        self._last_text = ""

        # ---- unavailable (non-Windows) ----
        self.unavailable = Notice(
            "The AI Assistant is unavailable here: it stores your API key in Windows Credential "
            "Manager, which isn't available on this system.")
        self.content.addWidget(self.unavailable)

        # ---- first-run setup ----
        self.setup = Card("Set up the assistant")
        self.setup.body.addWidget(label(
            "The assistant uses Google's Gemini API with your own free key. RYTWEAKS contains no "
            "key. Yours is stored in Windows Credential Manager on this PC.", wrap=True))
        link = QPushButton("Get a free key (aistudio.google.com/apikey)")
        link.clicked.connect(lambda: webbrowser.open(AI.KEY_URL))
        row = QHBoxLayout()
        row.addWidget(link)
        row.addStretch(1)
        self.setup.body.addLayout(row)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your Gemini API key")
        self.key_edit.textChanged.connect(self._update_save_enabled)
        self.setup.body.addWidget(self.key_edit)
        self.age_chk = QCheckBox("I'm 18 or older (required by Google's Gemini API terms)")
        self.terms_chk = QCheckBox("I accept Google's Gemini API terms")
        for c in (self.age_chk, self.terms_chk):
            c.toggled.connect(self._update_save_enabled)
            self.setup.body.addWidget(c)
        terms = QPushButton("Read Google's Gemini API terms")
        terms.clicked.connect(lambda: webbrowser.open(AI.TERMS_URL))
        row = QHBoxLayout()
        row.addWidget(terms)
        row.addStretch(1)
        self.setup.body.addLayout(row)
        self.setup.body.addWidget(label(
            "Free-tier chats may be reviewed by people at Google and used to improve Google "
            "products. Don't share personal information.", "warn", wrap=True))
        self.save_btn = set_role(QPushButton("Save key and start"), "primary")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_key)
        self.setup_status = label("", "muted", wrap=True)
        row = QHBoxLayout()
        row.addWidget(self.save_btn)
        row.addWidget(self.setup_status, 1)
        self.setup.body.addLayout(row)
        self.content.addWidget(self.setup)

        # ---- chat ----
        self.chat = QWidget()
        cl = QVBoxLayout(self.chat)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)

        opts = Card("Options")
        r1 = QHBoxLayout()
        self.specs_chk = QCheckBox("Include my PC specs")
        self.specs_chk.setChecked(bool(ctx.settings.get("ai_share_specs", True)))
        self.specs_chk.toggled.connect(lambda v: ctx.set_setting("ai_share_specs", bool(v)))
        self.see_btn = QPushButton("See what's shared")
        self.see_btn.clicked.connect(self._show_shared)
        r1.addWidget(self.specs_chk)
        r1.addWidget(self.see_btn)
        r1.addStretch(1)
        r1.addWidget(label("Model", "muted"))
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.setMinimumWidth(200)
        self._fill_models(ctx.settings.get("ai_model") or AI.DEFAULT_MODEL)
        self.model_box.currentTextChanged.connect(self._model_changed)
        r1.addWidget(self.model_box)
        self.refresh_btn = QPushButton("Refresh models")
        self.refresh_btn.clicked.connect(self._refresh_models)
        r1.addWidget(self.refresh_btn)
        self.remove_btn = QPushButton("Remove key")
        self.remove_btn.clicked.connect(self._remove_key)
        r1.addWidget(self.remove_btn)
        opts.body.addLayout(r1)
        self.opts_status = label("", "muted", wrap=True)
        opts.body.addWidget(self.opts_status)
        cl.addWidget(opts)

        self.msgs_host = QWidget()
        self.msgs = QVBoxLayout(self.msgs_host)
        self.msgs.setContentsMargins(0, 0, 0, 0)
        self.msgs.setSpacing(10)
        cl.addWidget(self.msgs_host)

        self.starters = QWidget()
        sl = QHBoxLayout(self.starters)
        sl.setContentsMargins(0, 0, 0, 0)
        for q in STARTERS:
            b = QPushButton(q)
            b.clicked.connect(lambda _c=False, q=q: self._send(q))
            sl.addWidget(b)
        sl.addStretch(1)
        cl.addWidget(self.starters)

        self.input = ChatInput()
        self.input.setPlaceholderText("Ask about your PC. Enter sends, Shift+Enter adds a line.")
        self.input.setFixedHeight(80)
        self.input.submitted.connect(lambda: self._send(None))
        cl.addWidget(self.input)
        row = QHBoxLayout()
        self.send_btn = set_role(QPushButton("Send"), "primary")
        self.send_btn.clicked.connect(self._send_or_stop)
        self.clear_btn = QPushButton("Clear chat")
        self.clear_btn.clicked.connect(self._clear)
        self.status = label("", "muted")
        row.addWidget(self.send_btn)
        row.addWidget(self.clear_btn)
        row.addWidget(self.status, 1)
        cl.addLayout(row)
        cl.addWidget(label("Answers can be wrong. Check anything risky before you act on it. "
                           "Nothing here is run for you.", "muted", wrap=True))
        self.content.addWidget(self.chat)

        self.finish()
        self._refresh_mode()

    # ------------------------------------------------------------ mode / key handling

    def _refresh_mode(self):
        ok = AI.credentials_available()
        has_key = ok and AI.load_key() is not None
        self.unavailable.setVisible(not ok)
        self.setup.setVisible(ok and not has_key)
        self.chat.setVisible(has_key)

    def on_shown(self):
        self._refresh_mode()

    def _update_save_enabled(self, *_):
        self.save_btn.setEnabled(bool(self.key_edit.text().strip()) and self.age_chk.isChecked()
                                 and self.terms_chk.isChecked())

    def _save_key(self):
        try:
            AI.save_key(self.key_edit.text())
        except Exception as e:
            self.setup_status.setText(f"Couldn't save the key: {e}")
            self.ctx.log_action("AI Assistant", "Save API key", "Failed", str(e))
            return
        if AI.load_key() is None:
            self.setup_status.setText("Windows didn't keep the key. Nothing was saved.")
            self.ctx.log_action("AI Assistant", "Save API key", "Failed", "read-back failed")
            return
        self.key_edit.clear()
        self.setup_status.setText("")
        self.age_chk.setChecked(False)
        self.terms_chk.setChecked(False)
        self.ctx.log_action("AI Assistant", "Save API key to Windows Credential Manager", "Saved")
        self._refresh_mode()

    def _remove_key(self):
        if QMessageBox.question(self, "Remove key",
                                "Remove your Gemini API key from Windows Credential Manager?\n"
                                "The chat on screen will be cleared.") != QMessageBox.Yes:
            return
        self._cancel_request()
        if AI.delete_key():
            self.ctx.log_action("AI Assistant", "Remove API key", "Removed")
            self._clear()
        else:
            self.ctx.log_action("AI Assistant", "Remove API key", "Failed")
            self.opts_status.setText("Windows couldn't remove the key.")
        self._refresh_mode()

    # ------------------------------------------------------------ models

    def _fill_models(self, current):
        self.model_box.blockSignals(True)
        self.model_box.clear()
        items = list(self._models)
        if current not in items:
            items.insert(0, current)
        self.model_box.addItems(items)
        self.model_box.setCurrentText(current)
        self.model_box.blockSignals(False)

    def _model_name(self):
        return self.model_box.currentText().strip() or AI.DEFAULT_MODEL

    def _model_changed(self, text):
        text = text.strip()
        if text:
            self.ctx.set_setting("ai_model", text)

    def _refresh_models(self):
        key = AI.load_key()
        if not key:
            return
        self.refresh_btn.setEnabled(False)
        self.opts_status.setText("Asking Google for the model list…")

        def work():
            try:
                return ("ok", AI.list_models(key))
            except AI.AIError as e:
                return ("err", str(e))
            except Exception:
                return ("err", "Couldn't get the model list.")

        def done(res):
            self.refresh_btn.setEnabled(True)
            kind, val = res
            if kind == "ok" and val:
                self._models = val
                self._fill_models(self._model_name())
                self.opts_status.setText(f"{len(val)} models available to your key. "
                                         "Which are free depends on Google's current plan.")
            elif kind == "ok":
                self.opts_status.setText("Google listed no matching models for your key.")
            else:
                self.opts_status.setText(val)
        self.run_task(work, on_done=done)

    # ------------------------------------------------------------ specs

    def _screens(self):
        out = []
        for s in QGuiApplication.screens():
            r = s.devicePixelRatio() or 1.0
            out.append({"width": round(s.size().width() * r), "height": round(s.size().height() * r),
                        "hz": s.refreshRate()})
        return out

    def specs_text(self):
        if not self.specs_chk.isChecked():
            return None
        text = AI.build_specs_summary(self.ctx.static, self.ctx.last_sample, self._screens())
        return text or None

    def _show_shared(self):
        specs = self.specs_text()
        full = AI.build_system_text(specs)
        head = ("Sent with every question:\n\n" if specs else
                "PC specs are OFF. Only these instructions are sent with your questions:\n\n")
        box = QMessageBox(self)
        box.setWindowTitle("What's shared")
        box.setText(head + "Your chat messages (last " + str(AI.MAX_HISTORY) + ") are sent too.")
        box.setDetailedText(full)
        box.setInformativeText(specs or "No PC specs included.")
        box.exec()

    # ------------------------------------------------------------ chat

    def _add_bubble(self, role, text):
        b = Bubble(role, text, self.ctx.theme)
        self._bubbles.append(b)
        self.msgs.addWidget(b)
        self.starters.setVisible(False)
        QTimer.singleShot(50, self._scroll_down)
        return b

    def _scroll_down(self):
        sa = self.findChild(QScrollArea)
        if sa is not None:
            sa.verticalScrollBar().setValue(sa.verticalScrollBar().maximum())

    def _send_or_stop(self):
        if self._pending:
            self._cancel_request()
        else:
            self._send(None)

    def _send(self, preset):
        if self._pending:
            return
        text = (preset if preset is not None else self.input.toPlainText()).strip()
        key = AI.load_key()
        if not text or not key:
            return
        self.input.clear()
        self._last_text = text
        self._add_bubble("user", text)
        self.history.append({"role": "user", "text": text})
        history = list(self.history)
        specs = self.specs_text()
        model = self._model_name()
        self._req += 1
        rid = self._req
        self._pending = True
        self.send_btn.setText("Stop")
        self.status.setText("Thinking…")
        self._thinking = self._add_bubble("model", "Thinking…")

        def work():
            try:
                return (rid, "ok", AI.generate(key, model, history, specs))
            except AI.AIError as e:
                return (rid, "err", str(e))
            except Exception:
                return (rid, "err", "Something went wrong talking to Google.")

        self.run_task(work, on_done=self._done)

    def _done(self, res):
        rid, kind, val = res
        if rid != self._req or not self._pending:
            return  # stopped or cleared: ignore the late result
        self._pending = False
        self.send_btn.setText("Send")
        self.status.setText("")
        self._drop_thinking()
        if kind == "ok":
            self.history.append({"role": "model", "text": val})
            self._add_bubble("model", val)
        else:
            # keep alternating roles: forget the question and give the text back to the user
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
            self.input.setPlainText(self._last_text)
            self._add_bubble("model", f"**Couldn't get an answer.** {val}")

    def _drop_thinking(self):
        b, self._thinking = self._thinking, None
        if b is not None:
            if b in self._bubbles:
                self._bubbles.remove(b)
            b.setParent(None)
            b.deleteLater()

    def _cancel_request(self):
        """Stop: the request can't be recalled, so its late result is ignored."""
        if not self._pending:
            return
        self._req += 1
        self._pending = False
        self.send_btn.setText("Send")
        self.status.setText("Stopped.")
        self._drop_thinking()
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()
        self.input.setPlainText(self._last_text)

    def _clear(self):
        self._cancel_request()
        self.history.clear()
        for b in self._bubbles:
            b.setParent(None)
            b.deleteLater()
        self._bubbles.clear()
        self.starters.setVisible(True)
        self.status.setText("")

    def on_theme(self, theme):
        for b in self._bubbles:
            b.apply_theme(theme)
