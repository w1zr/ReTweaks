import io
from types import SimpleNamespace as NS
import pytest
from core import taskbar_download as tb


DESCRIPTOR = b'''<AppInstaller xmlns="http://schemas.microsoft.com/appx/appinstaller/2018">
<MainBundle Name="28017CharlesMilette.TranslucentTB" Uri="https://github.com/TranslucentTB/TranslucentTB/releases/download/2026.2/bundle.msixbundle"/>
</AppInstaller>'''


class Response(io.BytesIO):
    def geturl(self):
        return tb.SOURCE


def test_combined_download_install_uses_official_descriptor_and_checks_exit(tmp_path):
    calls, progress = [], []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return NS(returncode=0, stdout='Installed TranslucentTB 2026.2', stderr='')
    result = tb.download_and_install(progress.append, tmp_path,
                                    opener=lambda *a, **k: Response(DESCRIPTOR), runner=run)
    assert 'Installed' in result
    assert calls[0][1]['env']['RETWEAKS_TB_PACKAGE'] == '28017CharlesMilette.TranslucentTB'
    assert (tmp_path / 'TranslucentTB.appinstaller').read_bytes() == DESCRIPTOR
    assert len(progress) == 2 and 'Add-AppxPackage' in calls[0][0][-1]


def test_windows_failure_is_reported_as_failure(tmp_path):
    with pytest.raises(OSError, match='Blocked by Windows'):
        tb.download_and_install(lambda _: None, tmp_path,
            opener=lambda *a, **k: Response(DESCRIPTOR),
            runner=lambda *a, **k: NS(returncode=1, stdout='Blocked by Windows', stderr=''))


def test_bad_package_is_not_installed(tmp_path):
    calls = []
    with pytest.raises(ValueError):
        tb.download_and_install(lambda _: None, tmp_path,
            opener=lambda *a, **k: Response(DESCRIPTOR.replace(
                b'https://github.com/TranslucentTB/TranslucentTB/releases/download/2026.2/', b'https://example.com/')),
            runner=lambda *a, **k: calls.append(a))
    assert not calls


def test_official_redirect_hosts_do_not_accept_lookalikes():
    assert tb.official_url(tb.SOURCE)
    assert tb.official_url('https://release-assets.githubusercontent.com/github-production-release-asset/x')
    for url in ('http://github.com/TranslucentTB/TranslucentTB/releases/x',
                'https://github.com/other/repo/releases/x',
                'https://github.com.evil.test/TranslucentTB/TranslucentTB/releases/x'):
        assert not tb.official_url(url)
