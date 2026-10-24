"""Fortnite-only UI check with a synthetic file and mocked writer; no game settings changed."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _tk_harness import FakeHub, g, pump
from fortnite_resolution_ui import FortniteResolutionPanel

hub = FakeHub()
with patch('fortnite_resolution_ui.fr.find_file', return_value=None):
    panel = FortniteResolutionPanel(hub, hub, g())
    assert pump(hub, lambda: "wasn't found" in panel.status.cget('text'))
panel.destroy() if hasattr(panel, 'destroy') else None
with patch('fortnite_resolution_ui.fr.find_file', return_value='C:/Users/R/GameUserSettings.ini'):
    panel = FortniteResolutionPanel(hub, hub, g())
    assert pump(hub, lambda: 'Found Fortnite settings' in panel.status.cget('text'))
    assert panel.target().endswith('GameUserSettings.ini')
try:
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'GameUserSettings.ini'
        target.write_text('[/Script/FortniteGame.FortGameUserSettings]\nResolutionSizeX=1920\n'
                          'ResolutionSizeY=1080\nFullscreenMode=1\n', encoding='utf-8')
        panel.path = str(target)
        panel.choose('1280 × 960 (4:3)')
        assert panel.width.get() == '1280' and panel.height.get() == '960'
        with patch('fortnite_resolution_ui.messagebox.askyesno', return_value=False), \
             patch('fortnite_resolution_ui.fr.apply') as apply:
            panel.apply()
            apply.assert_not_called()
        with patch('fortnite_resolution_ui.messagebox.askyesno', return_value=True), \
             patch('fortnite_resolution_ui.fr.apply', return_value='Saved game settings') as apply:
            panel.apply()
            assert pump(hub, lambda: not panel.busy)
            apply.assert_called_once_with(str(target), '1280', '960', lock=True)
        assert panel.status.cget('text') == 'Saved game settings'
        with patch('fortnite_resolution_ui.messagebox.askyesno', return_value=True), \
             patch('fortnite_resolution_ui.fr.restore', return_value='Restored game settings') as restore:
            panel.restore()
            assert pump(hub, lambda: not panel.busy)
            restore.assert_called_once_with(str(target))
        panel.lock.set(False); panel.lock_changed()
        assert hub.settings['fortnite_resolution_lock'] is False
        with patch('fortnite_resolution_ui.fr.mode_check', return_value=(False, {})):
            assert 'does not offer 1440 × 1080' in panel.mode_note('1440', '1080')
        with patch('fortnite_resolution_ui.fr.mode_check', return_value=(None, None)):
            assert panel.mode_note('1440', '1080') == ''
        panel.width.set('invalid')
        panel.apply()
        assert 'whole numbers' in panel.status.cget('text')
    print('PASS: Fortnite-only picker, consent, apply, restore and invalid input; writer mocked.')
finally:
    hub.destroy()
