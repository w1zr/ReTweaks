"""Real Tk taskbar controls with a fake installer; no software is installed."""
import os
import sys
import threading
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _tk_harness import FakeHub, g, pump
from rt_pages.taskbar import TaskbarPage

hub = FakeHub()
page = TaskbarPage(hub, hub, g())
gate = threading.Event()
calls = []
def install(progress):
    calls.append(True)
    progress('Installing test package')
    gate.wait(2)
    return 'Installed test package'
try:
    assert not calls and not page.busy
    with patch('rt_pages.taskbar.download_and_install', install):
        page.start()
        page.start()
        assert page.busy
        gate.set()
        assert pump(hub, lambda: not page.busy)
    assert len(calls) == 1 and 'Installed test package' in page.status.cget('text')
    with patch('rt_pages.taskbar.download_and_install', side_effect=OSError('Network unavailable')):
        page.start()
        assert pump(hub, lambda: not page.busy)
    assert 'Network unavailable' in page.status.cget('text')
    assert hub.logs[-1][2] == 'Failed'
    print('PASS: no install on open; one click starts once; completion and failure shown. Installer mocked.')
finally:
    page.close()
    hub.destroy()
