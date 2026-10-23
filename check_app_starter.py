"""App Starter checks: fake processes only; never downloads or installs an app."""
import queue,tempfile,threading
from pathlib import Path
from unittest.mock import patch,Mock
from app_starter import APPS,PRESETS,command,Runner,nvidia_url,download_nvidia
assert len(APPS)==100 and len(PRESETS['Full setup'])==13
assert len({row[3] for key,row in APPS.items() if key!='nvidia'})==99
assert all(row[4].startswith('https://') for row in APPS.values())
for keys in PRESETS.values():assert all(k in APPS for k in keys)
args=command('winget.exe','chrome','download',Path('test downloads'))
assert args[:4]==['winget.exe','download','--id','Google.Chrome']
assert '--exact' in args and '--source' in args and args[-1].endswith('chrome')
args=command('winget.exe','steam','install',Path('.'))
assert '--silent' in args and '--allow-reboot' not in args
assert not any('ignore' in x or 'override' in x for x in args)
for bad in ('x','chrome;calc'):
    try:command('winget.exe',bad,'install',Path('.'))
    except ValueError:pass
    else:raise AssertionError('Unknown package accepted')
assert nvidia_url('https://us.download.nvidia.com/nvapp/test.exe')
for bad in ('https://nvidia.com.evil.test/test.exe','http://nvidia.com/test.exe','https://user@nvidia.com/test.exe'):
    assert not nvidia_url(bad)
plan_patch=patch('app_sources.latest_plan',return_value={});plan_patch.start()
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
    events=queue.Queue();runner=Runner(events,tmp)
    def downloaded(*args,**kwargs):
        path=Path(tmp)/'discord'/'setup.exe';path.parent.mkdir(exist_ok=True);path.write_bytes(b'test-payload');return 0
    with patch('app_starter.winget_path',return_value='winget.exe'),patch('app_starter.subprocess.Popen',side_effect=[Mock(wait=Mock(return_value=1)),Mock(wait=Mock(side_effect=downloaded))]) as launch:
        runner.work(['chrome','discord'],'download')
        assert launch.call_count==2 and all(c.args[0][1]=='download' for c in launch.call_args_list)
        messages=list(events.queue)
        assert messages[-1]==('done',[('chrome',False),('discord',True)],False)
        assert not runner.busy and (Path(tmp)/'logs/chrome.log').exists()
    with patch('app_starter.subprocess.Popen') as launch:
        runner.stop.set();runner.work(['chrome'],'install');launch.assert_not_called()
    with patch('app_starter.winget_path',return_value=None),patch('app_starter.subprocess.Popen') as launch:
        runner.stop.clear();runner.work(['chrome'],'download');launch.assert_not_called()
        assert any('WinGet missing' in str(e) for e in list(events.queue))
print('PASS: all 100 apps, bundles, exact download/install commands, official NVIDIA URL checks, failed-app continuation, stop queue and missing-WinGet fallback. No downloads or installs.')


# Direct NVIDIA downloads must pass publisher verification before the final file exists.
import io
class Response(io.BytesIO):
    headers={'Content-Type':'application/octet-stream'}
class Opener:
    def __init__(self):self.responses=iter([Response(b'<a href="https://us.download.nvidia.com/NVIDIA_app_test.exe">Download</a>'),Response(b'MZ-test-installer')])
    def open(self,*args,**kwargs):return next(self.responses)
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
    with patch('app_starter.build_opener',return_value=Opener()),patch('app_starter.subprocess.run',return_value=Mock(returncode=0)) as verify:
        result=download_nvidia(tmp,threading.Event(),lambda _:None)
        assert result.read_bytes()==b'MZ-test-installer'
        assert verify.call_args.kwargs['env']['RETWEAKS_INSTALLER_PATH'].endswith('.part')
    result.unlink()
    with patch('app_starter.build_opener',return_value=Opener()),patch('app_starter.subprocess.run',return_value=Mock(returncode=1)):
        try:download_nvidia(tmp,threading.Event(),lambda _:None)
        except OSError:pass
        else:raise AssertionError('Unverified installer accepted')
    assert not list((Path(tmp)/'nvidia').iterdir())
print('PASS: NVIDIA staged download, publisher verification and failed-signature cleanup (all network/process calls mocked).')

plan_patch.stop()
