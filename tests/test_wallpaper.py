import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
import pytest

from core import wallpaper as w
from core import lively_wallpaper as l


class FakeDesktop:
    def __init__(self,original):
        self.state={'position':3,'monitors':[{'monitor':'screen1','image':str(original)},
                                           {'monitor':'screen2','image':str(original)}]}
        self.fail=False
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def snapshot(self):return copy.deepcopy(self.state)
    def set_position(self,value):self.state['position']=value
    def set_image(self,path,monitor=None):
        if self.fail:raise w.WallpaperError('Windows rejected image')
        for entry in self.state['monitors']:
            if monitor is None or monitor==entry['monitor']:entry['image']=path
    def restore(self,state):self.state=copy.deepcopy(state)


def test_picture_apply_backup_and_restore_all_monitors(tmp_path):
    old=tmp_path/'old.jpg';Image.new('RGB',(16,16),'blue').save(old)
    new=tmp_path/'new.png';Image.new('RGB',(32,16),'red').save(new)
    desktop=FakeDesktop(old)
    previous=desktop.snapshot()
    folder=tmp_path/'managed'
    result=w.apply_picture(new,'Fill',folder,lambda:desktop)
    assert result.is_file() and new.is_file()
    assert all(m['image']==str(result) for m in desktop.state['monitors'])
    assert desktop.state['position']==4
    restored=w.restore_picture(folder,lambda:desktop)
    assert restored==previous


def test_failed_apply_rolls_back(tmp_path):
    old=tmp_path/'old.jpg';Image.new('RGB',(16,16),'blue').save(old)
    desktop=FakeDesktop(old);previous=desktop.snapshot();desktop.fail=True
    with pytest.raises(w.WallpaperError):w.apply_picture(old,'Stretch',tmp_path/'managed',lambda:desktop)
    assert desktop.state==previous


def test_restore_missing_file_does_not_change_desktop(tmp_path):
    old=tmp_path/'old.jpg';Image.new('RGB',(16,16),'blue').save(old)
    new=tmp_path/'new.jpg';Image.new('RGB',(16,16),'red').save(new)
    desktop=FakeDesktop(old)
    w.apply_picture(new,folder=tmp_path/'managed',factory=lambda:desktop)
    old.unlink()
    current=desktop.snapshot()
    with pytest.raises(w.WallpaperError,match='missing'):w.restore_picture(tmp_path/'managed',lambda:desktop)
    assert desktop.state==current


def test_local_preset_and_image_validation(tmp_path):
    path=w.preset_image('Ocean glow',tmp_path)
    with Image.open(path) as image:assert image.size==(1920,1080)
    assert w.preset_image('Ocean glow',tmp_path)==path
    with pytest.raises(w.WallpaperError):w.preset_image('missing',tmp_path)
    with pytest.raises(w.WallpaperError):w.apply_picture(path,'bad fit',tmp_path)


def test_lively_commands_quote_paths_and_do_not_claim_playback(tmp_path,monkeypatch):
    movie=tmp_path/'a video.mp4';movie.write_bytes(b'test fixture')
    runner=Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(l,'run',runner)
    import psutil
    monkeypatch.setattr(psutil,'process_iter',lambda fields:[SimpleNamespace(info={'name':'Lively.exe'})])
    result=l.command('C:/Lively Wallpaper/Lively.exe','set',movie,2)
    assert runner.call_args.args[0]==['C:/Lively Wallpaper/Lively.exe','setwp','--file',str(movie.resolve()),'--monitor','2']
    assert 'Request sent' in result
    l.command('lively.exe','pause');assert runner.call_args.args[0][-3:]==['app','--play','false']
    l.command('lively.exe','resume');assert runner.call_args.args[0][-1]=='true'
    l.command('lively.exe','stop');assert runner.call_args.args[0][-3:]==['closewp','--monitor','-1']
    with pytest.raises(w.WallpaperError):l.command(None,'set',movie)
    with pytest.raises(w.WallpaperError):l.command('lively.exe','set',tmp_path/'app.exe')
    with pytest.raises(w.WallpaperError):l.command('lively.exe','set',movie,0)


def test_lively_not_running_is_clear(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil,'process_iter',lambda fields:[])
    with pytest.raises(w.WallpaperError,match='Open Lively'):l.command('lively.exe','pause')
