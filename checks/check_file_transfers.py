"""Exercise real Tk controls without uploading any user files."""
import time
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

import retweaks as app
from rt_pages.file_transfers import FileTransfersPage
from core import file_transfers as t
from rt_pages.transfer_picker import TransferPicker

hub = tk.Tk()
hub.geometry('1100x900')
hub._scroll_area = lambda tab: tab
tab = tk.Frame(hub, bg=app.BG)
tab.pack(fill='both', expand=True)
with patch.object(t, 'send') as sender:
    page = FileTransfersPage(hub, tab, vars(app))
    hub.update()
    sender.assert_not_called()
page.upload()
assert 'Choose files' in page.status.cget('text')
page._add(['C:/test/folder', 'C:/test/file.txt', 'C:/test/file.txt'])
assert len(page.paths) == 2
code = t.make_code('abcdef.zip', b'x' * 32, int(time.time()) + 3600)

def wait():
    deadline = time.monotonic() + 5
    while page.busy and time.monotonic() < deadline:
        hub.update()
        time.sleep(.02)
    assert not page.busy

with patch.object(t, 'send', return_value={'code': code, 'expires': int(time.time()) + 3600}) as sender:
    page.upload()
    wait()
    assert sender.call_args.args[0] == page.paths
    assert sender.call_args.args[1] == '72h'
    assert page.code.get() == code
    assert 'Upload complete' in page.status.cget('text')
    page.copy_code()
    assert hub.clipboard_get() == code
page.receive_code.set('bad code')
page.download()
assert 'complete ReTweaks share code' in page.status.cget('text')
page.receive_code.set(code)
with patch('rt_pages.file_transfers.filedialog.asksaveasfilename', return_value='C:/test/received.zip'), \
        patch.object(t, 'receive', return_value='C:/test/received.zip') as receiver:
    page.download()
    wait()
    receiver.assert_called_once()
    assert receiver.call_args.args[:2] == (code, 'C:/test/received.zip')
    assert 'Download complete' in page.status.cget('text')
with patch.object(t, 'send', side_effect=t.TransferError('Service unavailable')):
    page.upload()
    wait()
    assert page.status.cget('text') == 'Service unavailable'
page.clear()
assert not page.paths
# Select a file and a directory together, then add another location to the same basket.
with tempfile.TemporaryDirectory(dir='verification', prefix='mixed-picker-') as work:
    root = Path(work).resolve()
    (root / 'folder').mkdir()
    (root / 'file.txt').write_text('test')
    (root / 'folder' / 'nested.txt').write_text('nested')
    picked = []
    picker = TransferPicker(hub, vars(app), picked.extend, start=root)
    def loaded():
        deadline = time.monotonic() + 5
        while picker.job is not None and time.monotonic() < deadline:
            hub.update()
            time.sleep(.02)
        assert picker.entries
    loaded()
    picker.list.selection_set(0, 'end')
    picker.add_highlighted()
    assert set(picker.basket) == {str(root / 'folder'), str(root / 'file.txt')}
    picker.load(root / 'folder')
    loaded()
    picker.list.selection_set(0)
    picker.finish()
    assert picker.closed
    assert set(picked) == {str(root / 'folder'), str(root / 'file.txt'), str(root / 'folder' / 'nested.txt')}
    picker = TransferPicker(hub, vars(app), lambda items: None, start=root)
    picker.close()  # Closing during a directory scan must cancel the UI poll.
page.close()
assert page.cancel.is_set()
hub.destroy()
print('PASS: File Transfers UI selection, upload, expiry, clipboard, receive, errors and close cancellation.')
