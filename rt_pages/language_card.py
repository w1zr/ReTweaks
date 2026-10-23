"""Settings → Language: one-click language buttons, first card on the Settings page (owner request 2026-10-22).

Each language is shown in its own name and never translated, so someone who picked a language they can't
read can still find their own. The card's heading reads "<word for Language> · Language" in every language
(catalog entry "Language"). Switching is live (rt_i18n.set_language saves the `language` setting)."""
import tkinter as tk

import rt_i18n
from rt_pages.common import card, label


class LanguageCard:
    def __init__(self, hub, root, g):
        self.hub, self.g = hub, g
        body = card(root, g, "Language")
        label(body, "Menus, pages and messages switch to this language.", g, 9, g["MUTED"])
        row = tk.Frame(body, bg=body.cget("bg"))
        row.pack(fill="x", padx=16, pady=(6, 4))
        self.buttons = {}
        for code, name in rt_i18n.LANGUAGES.items():
            b = g["RButton"](row, name, lambda c=code: self.choose(c), kind="ghost")
            b.pack(side="left", padx=(0, 8), pady=2)
            self.buttons[code] = b
        label(body, rt_i18n.NOTE, g, 9, g["MUTED"])
        self.mark()
        try:
            hub.bind("<<LanguageChanged>>", lambda e: self.mark(), add="+")
        except tk.TclError:
            pass

    def mark(self):
        cur = rt_i18n.language()
        for code, b in self.buttons.items():
            try:
                if b.winfo_exists():
                    b.set_kind("primary" if code == cur else "ghost")
            except tk.TclError:
                pass

    def choose(self, code):
        if code != rt_i18n.language():
            rt_i18n.set_language(self.hub, code)
        self.mark()
