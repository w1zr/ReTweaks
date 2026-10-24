import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from core import dependencies as d
import rt_dependencies as ui


def test_existing_components_are_not_reinstalled(monkeypatch):
    monkeypatch.setattr(d,'available',lambda key:True)
    launch=Mock();monkeypatch.setattr(d,'run_installer',launch)
    assert d.install('pawnio')=='Already installed.'
    launch.assert_not_called()


def test_managed_presentmon_checks_hash_after_restart(tmp_path,monkeypatch):
    monkeypatch.setattr(d,'cache_dir',lambda:tmp_path)
    monkeypatch.setattr(d,'presentmon_path',lambda:str(tmp_path/'PresentMon.exe'))
    (tmp_path/'PresentMon.exe').write_bytes(b'tampered')
    assert not d.available('presentmon')


def test_checksum_failure_blocks_execution(tmp_path,monkeypatch):
    class Response(io.BytesIO):url='https://github.com/official/setup.exe'
    monkeypatch.setattr(d,'urlopen',lambda *a,**k:Response(b'bad installer'))
    with pytest.raises(OSError,match='checksum'):
        d.download('https://github.com/official/setup.exe',tmp_path/'setup.exe','0'*64)


def test_installer_failure_and_restart_are_reported(monkeypatch):
    monkeypatch.setattr(d.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=3010))
    assert d.run_installer(['setup.exe']) is True
    monkeypatch.setattr(d.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=5))
    with pytest.raises(OSError,match='code 5'):d.run_installer(['setup.exe'])


def test_concurrent_requests_share_one_worker(monkeypatch):
    monkeypatch.setattr(d,'enabled',lambda hub:True)
    state={'ready':False};monkeypatch.setattr(d,'available',lambda key:state['ready'])
    def install(key):state['ready']=True;return 'Installed.'
    installer=Mock(side_effect=install);monkeypatch.setattr(d,'install',installer)
    pending=[];callbacks=[]
    class Thread:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):pending.append(self.target)
    monkeypatch.setattr(ui.threading,'Thread',Thread)
    polls=[]
    hub=SimpleNamespace(settings={},sidebar_nav=SimpleNamespace(c=lambda name:'gray'),
                        set_status=Mock(),after=lambda delay,fn:polls.append(fn))
    assert ui.ensure(hub,'pawnio',lambda:callbacks.append(1))
    assert ui.ensure(hub,'pawnio',lambda:callbacks.append(2))
    assert len(pending)==1
    pending[0]();polls.pop(0)()
    assert callbacks==[1,2] and installer.call_count==1


def test_failed_setup_does_not_loop(monkeypatch):
    monkeypatch.setattr(d,'enabled',lambda hub:True)
    monkeypatch.setattr(d,'available',lambda key:False)
    hub=SimpleNamespace(_dependency_failures={'webview2'})
    assert ui.ensure(hub,'webview2') is False
