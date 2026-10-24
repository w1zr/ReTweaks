"""Real Tk rendering/control checks; no wallpaper changes or software installs."""
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

import retweaks as app
import appearance as ap
from rt_pages.wallpaper import WallpaperPage
from rt_pages import settings_store
from core import wallpaper

with tempfile.TemporaryDirectory(dir='verification',prefix='background-ui-') as work:
    os.environ['APPDATA']=str(Path(work).resolve())
    root=tk.Tk();root.geometry('1000x900')
    root.settings={'preserve_old_setting':42}
    root._scroll_area=lambda tab:tab
    tab=tk.Frame(root,bg=app.BG);tab.pack(fill='both',expand=True)
    with patch('core.lively_wallpaper.install') as install,patch.object(wallpaper,'apply_picture') as apply:
        page=WallpaperPage(root,tab,vars(app));root.update()
        install.assert_not_called();apply.assert_not_called()
    def wait():
        deadline=time.monotonic()+10
        while page.busy and time.monotonic()<deadline:root.update();time.sleep(.02)
        assert not page.busy
    page.choose_preset('Ocean glow');wait()
    assert page.photo is not None and page.picture
    assert 'Previewing' in page.status.cget('text')
    page.favorite('picture')
    assert settings_store.load()['wallpaper_favorites'][0]['kind']=='picture'
    assert settings_store.load()['preserve_old_setting']==42
    with patch.object(wallpaper,'apply_picture',return_value=Path(page.picture)) as apply:
        page.apply_picture();wait();apply.assert_called_once()
        assert 'Windows confirmed' in page.status.cget('text')
    with patch.object(wallpaper,'restore_picture',return_value={}) as restore:
        page.restore();wait();restore.assert_called_once()
    with patch.object(wallpaper,'apply_picture',side_effect=wallpaper.WallpaperError('Denied')):
        page.apply_picture();wait();assert page.status.cget('text')=='Denied'
    page.remove_favorite();assert not settings_store.load()['wallpaper_favorites']
    page.close();tab.destroy()
    mode=['Particles'];options={'animation_height':100}
    accent=ap.Accent(root,lambda:{key:vars(app)[key] for key in ('PANEL','LINE','ACC')},lambda:mode[0],lambda:options)
    accent.pack(fill='x');root.update()
    for style in ap.ANIMATIONS:
        mode[0]=style;accent.refresh();root.update()
        assert accent.find_all() or style=='Off',style
    mode[0]='Aurora';accent.refresh();root.update()
    root.withdraw();root.update();time.sleep(.15);root.update()
    assert accent.job is None,'Hidden animation still schedules frames'
    root.deiconify();root.update();assert accent.job is not None
    root.destroy()
print('PASS: wallpaper preview/favorites/apply/restore/error wiring, all animation modes, hidden pause and resume.')
