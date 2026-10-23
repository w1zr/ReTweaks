"""Constrained app-release review tests; no live AI or app downloads."""
import json,threading,subprocess
from unittest.mock import patch
from app_sources import latest_plan
metadata='Found Google Chrome [Google.Chrome]\nVersion: 999.1\nPublisher: Google LLC\nInstaller Url: https://dl.google.com/test.msi\nInstaller SHA256: testhash'
events=[]
with patch('app_sources.subprocess.run',return_value=subprocess.CompletedProcess([],0,metadata,'')),patch('drivers.ask_ai',return_value={'text':json.dumps({'items':[{'id':'chrome','package':'Google.Chrome','version':'999.1','approved':True}]})}) as ai:
    plan=latest_plan(['chrome'],'winget.exe',threading.Event(),events.append)
    assert plan['chrome']['ai'] and plan['chrome']['version']=='999.1'
    payload=ai.call_args.args[0]
    assert payload['task']=='apps' and len(payload['apps'])==1
    assert not any(k in payload for k in ('hardware','user','host','history'))
with patch('app_sources.subprocess.run',return_value=subprocess.CompletedProcess([],0,metadata,'')),patch('drivers.ask_ai',return_value={'text':json.dumps({'items':[{'id':'chrome','package':'Evil.Package','version':'1000','approved':True,'url':'https://bad.test/file.exe'}]})}):
    plan=latest_plan(['chrome'],'winget.exe',threading.Event(),events.append)
    assert not plan['chrome'].get('ai') and plan['chrome']['version']=='999.1'
    assert plan['chrome']['url']=='https://dl.google.com/test.msi'
with patch('app_sources.subprocess.run',return_value=subprocess.CompletedProcess([],0,metadata,'')),patch('drivers.ask_ai',side_effect=OSError('Offline')):
    plan=latest_plan(['chrome'],'winget.exe',threading.Event(),events.append)
    assert plan['chrome']['version']=='999.1' and any('unavailable' in str(e) for e in events)
stop=threading.Event();stop.set()
with patch('app_sources.subprocess.run') as process,patch('drivers.ask_ai') as ai:
    assert latest_plan(['chrome'],'winget.exe',stop,events.append)=={}
    process.assert_not_called();ai.assert_not_called()
print('PASS: live-source parsing, constrained AI approval, invented-package/version/URL rejection, offline fallback, bounded app-only payload and cancellation. No app installs/downloads or AI calls.')

# Bulk reviews have a bounded prompt and cannot approve an app outside the review.
from app_starter import APPS
keys=[k for k in APPS if k!='nvidia'][:21]
with patch('app_sources.subprocess.run',return_value=subprocess.CompletedProcess([],0,metadata,'')),patch('drivers.ask_ai',return_value={'text':json.dumps({'items':[{'id':keys[-1],'package':APPS[keys[-1]][3],'version':'999.1','approved':True}]})}) as ai:
    plan=latest_plan(keys,'winget.exe',threading.Event(),lambda _:None)
    assert len(ai.call_args.args[0]['apps'])==20
    assert not plan[keys[-1]].get('ai')
print('PASS: bulk AI release review stays bounded and cannot approve unreviewed packages.')
