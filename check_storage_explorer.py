"""Storage browser regression checks against disposable fixture files."""
import tempfile
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from unittest.mock import Mock
import retweaks as app
from storage_explorer import StorageExplorer,scan_directory,size_text,list_drives

def pump_until(condition):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        root.update()
        if condition():return
        time.sleep(.01)
    raise AssertionError('Browser did not settle')

fixture_root=(Path(__file__).resolve().parent/'verification').resolve()
fixture_root.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=fixture_root) as temp:
    base=Path(temp).resolve();assert base.is_relative_to(fixture_root)
    folder=base/'Nested folder';folder.mkdir()
    (folder/'child.txt').write_text('child')
    for i in range(301):(base/f'file-{i:03}.txt').write_bytes(b'x'*i)
    data=scan_directory(base)
    assert len(data['rows'])==302 and size_text(1024)=='1.0 KB'
    assert any(r['folder'] and r['size'] is None for r in data['rows'])
    assert list_drives()
    root=tk.Tk();root.geometry('1100x800');root.launch=Mock();ttk.Style(root).theme_use('clam')
    frame=tk.Frame(root);frame.pack(fill='both',expand=True)
    errors=[];root.report_callback_exception=lambda *args:errors.append(args)
    browser=StorageExplorer(root,frame,vars(app))
    try:
        browser.navigate(base)
        pump_until(lambda:browser.current==str(base) and len(browser.files.get_children())==302)
        browser.query.set('file-300');root.update()
        assert len(browser.files.get_children())==1
        browser.query.set('');pump_until(lambda:len(browser.files.get_children())==302)
        browser.sort('size');browser.sort('size')
        pump_until(lambda:len(browser.files.get_children())==302)
        assert browser.shown['0']['folder'] and browser.shown['1']['size']==300
        browser.navigate(folder);pump_until(lambda:browser.current==str(folder))
        browser.back();pump_until(lambda:browser.current==str(base))
        browser.navigate(base/'not-there')
        pump_until(lambda:'Cannot open' in browser.status.cget('text'))
        assert browser.current==str(base)
        browser.navigate(folder);browser.navigate(base)
        pump_until(lambda:browser.current==str(base) and len(browser.files.get_children())==302)
        assert not errors,errors
    finally:root.destroy()
    assert browser.closed and browser.cancel.is_set()
print('PASS: drive enumeration, folder browsing, file sizes, filtering, sort, back, stale scan cancellation, invalid paths, large folder batches and clean shutdown.')
