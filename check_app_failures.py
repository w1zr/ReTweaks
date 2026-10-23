"""Failed download detection and bounded, redacted AI guidance. No real installs/AI."""
import json
import queue
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from app_starter import APPS,Runner,downloaded_payload
from app_troubleshooting import redact,failure_record,explain,fallback

raw=r'C:\Users\Alice\Downloads\setup.exe password="very secret value" api_key=abc123 https://vendor.test/file?token=private#secret alice@example.com'
clean=redact(raw)
assert all(value not in clean for value in ('Alice','very secret value','abc123','token=private','alice@example.com')),clean
report=failure_record('chrome',APPS['chrome'],'download','Download failed',0x8A150008,raw)
seen=[]
def ai(payload):
    seen.append(payload)
    return {'text':json.dumps({'summary':'The server interrupted the download.','steps':['Check your connection.','Retry this download.']})}
result=explain(report,ask=ai)
assert result['source']=='AI guidance'
assert seen[0]['task']=='app_failure'
assert set(seen[0])=={'task','failure'}
assert 'Alice' not in json.dumps(seen) and len(json.dumps(seen))<14000
assert not any(k in seen[0]['failure'] for k in ('hardware','history','username','host'))
for reply in ({'text':'nonsense'},{'text':'{"summary":"x","steps":[]}'},{'text':'{"summary":"x","steps":[1]}'}):
    assert explain(report,ask=lambda _:reply)['source']=='Local guidance'
assert explain(report,False,ask=lambda _:(_ for _ in ()).throw(AssertionError()))['source']=='Local guidance'
with patch('drivers.ask_ai',side_effect=OSError('Quota')):
    assert explain(report)['source']=='Local guidance'
assert 'security checks enabled' in ' '.join(fallback({**report,'code':0x8A150011})['steps'])

with tempfile.TemporaryDirectory(dir='.') as tmp:
    q=queue.Queue();runner=Runner(q,tmp,enable_ai=False)
    # A zero exit code without an installer must not be called a successful download.
    with patch('app_sources.latest_plan',return_value={}),patch('app_starter.winget_path',return_value='winget.exe'),patch('app_starter.subprocess.Popen',return_value=Mock(wait=Mock(return_value=0))):
        runner.work(['chrome'],'download')
    events=list(q.queue)
    assert events[-1]==('done',[('chrome',False)],False)
    failures=[e[2] for e in events if e[0]=='failure']
    assert len(failures)==1 and 'no complete installer' in failures[0]['error']
    assert failures[0]['mode']=='download' and failures[0]['code']==0
    # An invalid signature cannot be converted to success or an alternate URL.
    q.queue.clear()
    with patch('app_sources.latest_plan',return_value={}),patch('app_starter.winget_path',return_value='winget.exe'),patch('app_starter.subprocess.Popen',return_value=Mock(wait=Mock(return_value=-1978335215))):
        runner.work(['chrome'],'install')
    failure=next(e[2] for e in list(q.queue) if e[0]=='failure')
    assert failure['code']==0x8A150011
    assert not downloaded_payload(Path(tmp)/'chrome')
print('PASS: failed/empty downloads, signed error codes, local fallbacks, malformed/disabled/unavailable AI, bounded app-only payload and log redaction. No installs or AI calls.')
