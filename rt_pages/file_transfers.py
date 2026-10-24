"""Send files/folders or receive an encrypted transfer using a share code."""
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog

from core import file_transfers as transfer
from rt_pages.common import button_row, card, label


class FileTransfersPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self.paths = []
        self.closed = self.busy = False
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.job = None
        self.picker = None
        self.buttons = []
        g['page_header'](tab, 'RETWEAKS', 'File Transfers', 'Send files and folders with a share code.')
        root = hub._scroll_area(tab)
        label(root, 'Transfer now or download later. Once uploading finishes, the sender can close ReTweaks. '
              'The recipient needs this File Transfers tab and the complete share code.', g, 10, padx=0)
        send = card(root, g, 'Send', 'Up to 1 GB per transfer, including the ZIP and encryption overhead.')
        row = button_row(send, g)
        self._button(row, 'Add files & folders', self.add_mixed, 'primary')
        self._button(row, 'Add files', self.add_files)
        self._button(row, 'Add folder', self.add_folder)
        self._button(row, 'Clear selection', self.clear)
        self.selection = label(send, 'No files or folders selected.', g, 10, wrap=760)
        self.lifetime = tk.StringVar(value='72 hours')
        row = button_row(send, g)
        label(row, 'Available for:', g, 10, padx=0)
        self.expiry = g['RSelect'](row, list(transfer.LIFETIMES), width=170,
                                  command=lambda value: self.lifetime.set(value))
        self.expiry.set('72 hours')
        self.expiry.pack(side='left', padx=(0, 10))
        self._button(row, 'Upload & create code', self.upload, 'primary')
        self.code = tk.StringVar()
        g['REntry'](send, self.code, width_px=680).pack(fill='x', padx=16, pady=6)
        row = button_row(send, g)
        self.copy_button = g['RButton'](row, 'Copy share code', self.copy_code)
        self.copy_button.pack(side='left')
        self.copy_button.set_enabled(False)
        self.expiration = label(send, '', g, 9, g['MUTED'])
        label(send, 'Limit: 1 GB total per transfer and up to 10,000 files/folders. ReTweaks has no daily '
              'transfer count or reset. The hosting service does not publish a daily quota/reset schedule. '
              'Expiry applies separately to each upload.', g, 9, g['MUTED'])

        receive = card(root, g, 'Receive', 'Paste the complete code from the sender. Your files are saved as a ZIP.')
        self.receive_code = tk.StringVar()
        g['REntry'](receive, self.receive_code, width_px=680).pack(fill='x', padx=16, pady=6)
        row = button_row(receive, g)
        self._button(row, 'Download to…', self.download, 'primary')
        self.status = label(root, '', g, 10, padx=0)
        self.cancel_button = g['RButton'](root, 'Cancel transfer', self.cancel_transfer)
        self.cancel_button.pack(anchor='w', pady=6)
        self.cancel_button.set_enabled(False)
        label(root, 'Hosted temporarily by Litterbox (catbox.moe). Files and filenames are encrypted on your PC '
              'before upload. Anyone with the share code can download and decrypt them. Codes are not saved '
              'between launches. Keep the code until the recipient has downloaded. Transfers expire automatically; '
              'availability depends on the hosting service. Downloaded ZIPs are never opened or extracted automatically.',
              g, 9, g['MUTED'], padx=0)

    def _button(self, row, text, command, kind='default'):
        button = self.g['RButton'](row, text, command, kind=kind)
        button.pack(side='left', padx=(0, 8))
        self.buttons.append(button)
        return button

    def add_files(self):
        if not self.busy:
            self._add(filedialog.askopenfilenames(parent=self.hub, title='Choose files to share'))

    def add_mixed(self):
        if self.busy or self.closed:
            return
        if self.picker is not None and not self.picker.closed:
            self.picker.window.lift()
            return
        from rt_pages.transfer_picker import TransferPicker
        self.picker = TransferPicker(self.hub, self.g, self._add)

    def add_folder(self):
        if not self.busy:
            path = filedialog.askdirectory(parent=self.hub, title='Choose a folder to share')
            self._add([path] if path else [])

    def _add(self, paths):
        for path in paths:
            if path not in self.paths:
                self.paths.append(path)
        names = [Path(p).name for p in self.paths]
        self.selection.config(text=(f'{len(names)} selected: ' + ', '.join(names[:12]) +
                                    (' …' if len(names) > 12 else '')) if names else 'No files or folders selected.')

    def clear(self):
        if not self.busy:
            self.paths.clear()
            self._add([])

    def copy_code(self):
        if self.code.get():
            self.hub.clipboard_clear()
            self.hub.clipboard_append(self.code.get())
            self.status.config(text='Share code copied. Send it privately to the recipient.')

    def upload(self):
        if self.busy:
            return
        if not self.paths:
            self.status.config(text='Choose files or a folder first.')
            return
        paths = list(self.paths)
        lifetime = transfer.LIFETIMES[self.lifetime.get()]
        self._start('send', lambda progress: transfer.send(paths, lifetime, self.cancel, progress))

    def download(self):
        if self.busy:
            return
        code = self.receive_code.get()
        try:
            transfer.parse_code(code)
        except transfer.TransferError as exc:
            self.status.config(text=str(exc))
            return
        path = filedialog.asksaveasfilename(parent=self.hub, title='Save received files as ZIP',
                                          initialfile='ReTweaks transfer.zip', defaultextension='.zip',
                                          filetypes=[('ZIP archive', '*.zip')])
        if path:
            self._start('receive', lambda progress: transfer.receive(code, path, self.cancel, progress))

    def _start(self, kind, fn):
        if self.closed:
            return
        self.busy = True
        self.cancel.clear()
        for button in self.buttons:
            button.set_enabled(False)
        self.cancel_button.set_enabled(True)
        self.status.config(text='Starting transfer…')

        def progress(message):
            # Coalesce frequent progress updates; do not accumulate per-chunk events.
            self.progress = message

        self.progress = ''

        def work():
            try:
                self.events.put((kind, fn(progress), None))
            except Exception as exc:
                self.events.put((kind, None, exc))

        threading.Thread(target=work, name='FileTransfer', daemon=True).start()
        self.job = self.hub.after(100, self._poll)

    def _poll(self):
        self.job = None
        if self.closed:
            return
        if self.progress:
            self.status.config(text=self.progress)
        try:
            kind, result, error = self.events.get_nowait()
        except queue.Empty:
            self.job = self.hub.after(100, self._poll)
            return
        self.busy = False
        for button in self.buttons:
            button.set_enabled(True)
        self.cancel_button.set_enabled(False)
        if error:
            # Exception text may contain filenames but never a code/key or raw service response.
            self.status.config(text=str(error))
        elif kind == 'send':
            self.code.set(result['code'])
            self.copy_button.set_enabled(True)
            expires = datetime.fromtimestamp(result['expires']).strftime('%b %d, %Y at %I:%M %p')
            self.expiration.config(text=f'Expires by {expires} (this PC’s local time).')
            self.status.config(text='Upload complete. Copy the code and send it to the recipient. You can close ReTweaks now.')
        else:
            self.status.config(text=f'Download complete: {result}\nOpen the ZIP in Windows to access the files.')

    def cancel_transfer(self):
        self.cancel.set()
        self.status.config(text='Cancelling… Network operations may take up to 90 seconds to stop.')

    def close(self):
        self.closed = True
        self.cancel.set()
        if self.picker is not None:
            self.picker.close()
        if self.job is not None:
            try:
                self.hub.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
