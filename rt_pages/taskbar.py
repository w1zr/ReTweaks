"""One-click official TranslucentTB installation, only on a deliberate click."""
import queue
import threading
import tkinter as tk
from core.taskbar_download import download_and_install


class TaskbarPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self.busy = self.closed = False
        self.events = queue.Queue()
        g['page_header'](tab, 'RETWEAKS', 'Transparent TB (taskbar)')
        body = hub._scroll_area(tab)
        tk.Label(body, text='TranslucentTB makes the Windows taskbar transparent or translucent, with blur, '
                 'acrylic, and color options. Configure it from its tray icon after opening it.\n\n'
                 'Download downloads and installs the official TranslucentTB package for your Windows account '
                 'right away. Windows verifies the package signature. Then open TranslucentTB from Start to '
                 'choose your appearance.', bg=g['BG'], fg=g['MUTED'], font=(g['UI'], 11),
                 justify='left', wraplength=760).pack(anchor='w', pady=(6, 20))
        self.download = g['RButton'](body, 'Download', self.start, kind='primary')
        self.download.pack(anchor='w')
        self.status = tk.Label(body, text='', bg=g['BG'], fg=g['MUTED'], font=(g['UI'], 10),
                               justify='left', wraplength=760)
        self.status.pack(anchor='w', pady=12)

    def start(self):
        if self.busy or self.closed:
            return
        self.busy = True
        self.download.set_enabled(False)
        self.status.config(text='Starting download…')

        def work():
            try:
                message = download_and_install(lambda text: self.events.put(('progress', text)))
                self.events.put(('done', message))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.hub.after(100, self.poll)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, message = self.events.get_nowait()
                self.status.config(text=message, fg=self.g.get('RED', self.g['FG']) if kind == 'error'
                                   else self.g['MUTED'])
                if kind != 'progress':
                    self.busy = False
                    self.download.set_enabled(True)
                    self.hub.log_action('Transparent TB (taskbar)', 'Download and install TranslucentTB',
                                        'Installed' if kind == 'done' else 'Failed', message if kind == 'error' else '')
        except queue.Empty:
            pass
        if self.busy:
            self.hub.after(100, self.poll)

    def close(self):
        self.closed = True
