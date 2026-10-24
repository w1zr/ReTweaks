from pathlib import Path

import embedded_browser as browser


def test_frozen_browser_uses_bundle_data_not_module_or_working_directory(tmp_path,monkeypatch):
    bundle=tmp_path/'bundle';(bundle/'ai').mkdir(parents=True)
    helper=bundle/'ai'/'EmbeddedBrowser.exe';helper.write_bytes(b'test')
    monkeypatch.setattr(browser.sys,'_MEIPASS',str(bundle),raising=False)
    monkeypatch.setattr(browser,'__file__',str(tmp_path/'unrelated'/'embedded_browser.py'))
    monkeypatch.delenv('RETWEAKS_BROWSER_CMD',raising=False)
    monkeypatch.chdir(tmp_path)
    assert browser.available()
    assert browser.command(42)==[str(helper),'42']


def test_source_browser_uses_module_directory(monkeypatch):
    monkeypatch.delattr(browser.sys,'_MEIPASS',raising=False)
    assert browser.ai_folder()==Path(browser.__file__).resolve().parent/'ai'
