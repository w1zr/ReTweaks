# ui/widgets/preset_apply.py
"""Shared preset flow (v1.4.3) for the Profiles and Tweaks pages: read what the preset would change
from Windows, show it, and apply only after the user confirms. Every change is a normal tweak with
its own Undo."""

from PySide6.QtWidgets import QMessageBox

from core.profiles import apply_profile, preview


def start(page, name, on_status, on_finished=None):
    """on_status(text) shows progress; on_finished(results) runs after applying (or None if cancelled)."""
    on_status(f"Checking what {name} would change…")

    def previewed(items):
        if isinstance(items, tuple):          # the worker failed
            on_status(f"✖ Couldn't read your current settings: {items[1]}")
            return on_finished and on_finished(None)
        change = [i for i in items if i[3]]
        same = [i for i in items if not i[3]]
        if not change:
            on_status(f"{name}: everything is already set. Nothing to change.")
            return on_finished and on_finished(None)
        lines = [f"• {lbl}: {cur or '?'} → {want}" if want else f"• {lbl}" for lbl, cur, want, _ in change]
        text = f"{name} will change {len(change)} setting{'s' if len(change) != 1 else ''}:\n\n" + "\n".join(lines)
        if same:
            text += f"\n\nAlready set ({len(same)}): " + ", ".join(lbl for lbl, *_ in same)
        text += "\n\nEach one can be undone on the Tweaks page, or all at once with “Undo everything”."
        box = QMessageBox(QMessageBox.Question, f"Apply {name}?", text, QMessageBox.Yes | QMessageBox.Cancel, page)
        if box.exec() != QMessageBox.Yes:
            on_status("Cancelled. Nothing was changed.")
            return on_finished and on_finished(None)
        on_status(f"Applying {name}…")
        page.run_task(apply_profile, name, on_done=applied)

    def applied(results):
        if isinstance(results, tuple):
            results = [("Preset", False, results[1])]
        for step, ok, msg in results:
            page.ctx.log_action(f"Preset: {name}", step, "Success" if ok else "Failed", "" if ok else msg)
        failed = sum(1 for _, ok, _ in results if not ok)
        try:
            page.ctx.set_setting("last_preset", name)
        except Exception:
            pass
        lines = [f"{'✔' if ok else '✖'}  {s}: {m}" for s, ok, m in results]
        on_status(f"{name}: {len(results) - failed} of {len(results)} steps succeeded.\n\n" + "\n".join(lines))
        if on_finished:
            on_finished(results)

    page.run_task(preview, name, on_done=previewed)
