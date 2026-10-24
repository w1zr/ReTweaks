"""A mixed file/folder picker with Ctrl/Shift selection and a reusable basket."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog

from rt_pages.common import button_row, label


class TransferPicker:
    def __init__(self, parent, g, done, start=None):
        self.g, self.done = g, done
        self.closed = False
        self.generation = 0
        self.basket = []
        self.entries = []
        self.events = queue.Queue()
        self.job = None
        self.window = tk.Toplevel(parent, bg=g['BG'])
        self.window.title('Add files & folders')
        self.window.geometry('800x650')
        self.window.minsize(620, 480)
        self.window.transient(parent)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda event: self.close())
        label(self.window, 'Select files and folders together', g, 15, bold=True, pady=(16, 4))
        label(self.window, 'Use Ctrl or Shift to select several items. Double-click a folder to open it. '
              'Add items from different locations to the same selection.', g, 10)
        row = button_row(self.window, g)
        self.path = tk.StringVar()
        field = g['REntry'](row, self.path, width_px=400)
        field.pack(side='left', fill='x', expand=True, padx=(0, 8))
        field.entry.bind('<Return>', lambda event: self.load(self.path.get()))
        for text, command in [('Go', lambda: self.load(self.path.get())), ('Up', self.up), ('Browse…', self.browse)]:
            g['RButton'](row, text, command).pack(side='left', padx=(0, 5))
        area = tk.Frame(self.window, bg=g['BG'])
        area.pack(fill='both', expand=True, padx=16)
        self.list = tk.Listbox(area, selectmode='extended', exportselection=False, bg=g['PANEL'],
                               fg=g['FG'], selectbackground=g['ACC'], selectforeground=g['BG'],
                               font=(g['UI'], 10), relief='flat', highlightthickness=1,
                               highlightbackground=g['LINE'])
        scroll = tk.Scrollbar(area, command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.list.pack(side='left', fill='both', expand=True)
        self.list.bind('<Double-Button-1>', self.open_folder)
        self.list.bind('<Control-a>', self.select_all)
        self.list.bind('<Control-A>', self.select_all)
        self.status = label(self.window, '', g, 9, g['MUTED'])
        self.summary = label(self.window, 'Nothing added yet.', g, 10)
        row = button_row(self.window, g)
        g['RButton'](row, 'Add highlighted', self.add_highlighted).pack(side='left', padx=(0, 8))
        g['RButton'](row, 'Clear selection', self.clear).pack(side='left')
        g['RButton'](row, 'Add to transfer', self.finish, kind='primary').pack(side='right', padx=(8, 0))
        g['RButton'](row, 'Cancel', self.close).pack(side='right')
        self.load(start or Path.home())
        self.window.grab_set()

    def load(self, directory):
        if self.closed:
            return
        self.generation += 1
        generation = self.generation
        self.list.delete(0, 'end')
        self.entries = []
        self.status.config(text='Reading folder…')

        def scan():
            try:
                target = Path(os.path.abspath(os.path.expanduser(str(directory))))
                # Reject links/junctions at the transfer backend; browsing them is allowed.
                with os.scandir(target) as items:
                    entries = [(Path(item.path), item.is_dir()) for item in items]
                entries.sort(key=lambda item: (not item[1], item[0].name.casefold()))
                self.events.put((generation, target, entries, None))
            except OSError as exc:
                self.events.put((generation, None, [], str(exc)))

        threading.Thread(target=scan, daemon=True, name='TransferPicker').start()
        if self.job is None:
            self.job = self.window.after(50, self.poll)

    def poll(self):
        self.job = None
        if self.closed:
            return
        pending = True
        try:
            while True:
                generation, directory, entries, error = self.events.get_nowait()
                if generation != self.generation:
                    continue
                pending = False
                if error:
                    self.status.config(text='Could not open folder: ' + error)
                    continue
                self.path.set(str(directory))
                self.entries = entries
                for path, is_dir in entries:
                    self.list.insert('end', ('Folder    ' if is_dir else 'File         ') + path.name)
                self.status.config(text=f'{len(entries)} items. Ctrl/Shift selects files and folders together.')
        except queue.Empty:
            pass
        if pending:
            self.job = self.window.after(50, self.poll)

    def up(self):
        self.load(Path(self.path.get()).parent)

    def browse(self):
        path = filedialog.askdirectory(parent=self.window, title='Browse to a folder')
        if path:
            self.load(path)

    def open_folder(self, event=None):
        selected = self.list.curselection()
        if len(selected) == 1 and self.entries[selected[0]][1]:
            self.load(self.entries[selected[0]][0])

    def select_all(self, event=None):
        self.list.selection_set(0, 'end')
        return 'break'

    def add_highlighted(self):
        for index in self.list.curselection():
            path = str(self.entries[index][0])
            if path not in self.basket:
                self.basket.append(path)
        self.list.selection_clear(0, 'end')
        names = [Path(p).name for p in self.basket]
        self.summary.config(text=(f'{len(names)} selected: ' + ', '.join(names[:6]) +
                                  (' …' if len(names) > 6 else '')) if names else 'Nothing added yet.')

    def clear(self):
        self.basket.clear()
        self.list.selection_clear(0, 'end')
        self.summary.config(text='Nothing added yet.')

    def finish(self):
        self.add_highlighted()
        if not self.basket:
            self.status.config(text='Highlight at least one file or folder first.')
            return
        paths = list(self.basket)
        self.close()
        self.done(paths)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.job is not None:
            self.window.after_cancel(self.job)
            self.job = None
        try:
            self.window.grab_release()
            self.window.destroy()
        except tk.TclError:
            pass
