"""Reversible sidebar reveal with synchronized content layout."""
import time
import tkinter as tk

class SidebarFade:
    # Keep the existing class name for callers; transitions now slide, not fade.
    DURATION = .16
    def __init__(self, root, sidebar, colors, apply_layout):
        self.root, self.sidebar, self.colors, self.apply_layout = root, sidebar, colors, apply_layout
        self.full_width = int(sidebar.cget('width'))
        self.width = self.full_width if root.sidebar_slot.winfo_manager() else 0
        self.overlay = None
        self.job = None
        self.closed = False

    def cancel(self):
        if self.job:
            try:self.root.after_cancel(self.job)
            except tk.TclError:pass
            self.job = None

    def transition(self, collapsed):
        self.cancel()
        if self.closed:return
        if not self.root.winfo_viewable() or self.root.state() == 'iconic':
            self.finish(collapsed)
            return
        start = self.width
        target = 0 if collapsed else self.full_width
        if not self.root.sidebar_slot.winfo_manager():
            self.root.sidebar_slot.configure(width=max(1,start))
            self.sidebar.place_configure(x=0)
            self.apply_layout(False)
        began = time.monotonic()
        def tick():
            if self.closed:return
            elapsed = min(1, (time.monotonic() - began) / self.DURATION)
            eased = elapsed * elapsed * (3 - 2 * elapsed)
            self.width = round(start + (target - start) * eased)
            self.root.sidebar_slot.configure(width=max(1,self.width))
            self.sidebar.place_configure(x=0)
            if elapsed >= 1:self.finish(collapsed)
            else:self.job = self.root.after(12, tick)
        tick()

    def finish(self, collapsed):
        self.cancel()
        self.width = 0 if collapsed else self.full_width
        self.root.sidebar_slot.configure(width=max(1,self.width))
        if collapsed:self.apply_layout(True)
        self.sidebar.place_configure(x=0)
        if not collapsed:self.apply_layout(False)

    def close(self):
        self.closed = True
        self.cancel()
