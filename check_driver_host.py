"""Packaged driver helper check. --live-test uses public vendor metadata and ordinary AI generation."""
import sys,json
from drivers import ask_ai,components,payload,apply_results,vendor_results
live='--live-test' in sys.argv
info={'os':'Windows 11','gpu':'NVIDIA GeForce RTX 4060','raw':{'os_arch':'64-bit'}}
rows=components(info,[]);rows[0]['id']='gpu-0'
if live:
    from driver_sources import gather
    evidence,facts=gather(info,rows)
    assert facts and facts[0]['verified'],'No exact NVIDIA release found'
else:evidence=[{'component_id':'gpu-0','url':'https://www.nvidia.com/en-us/drivers/','text':'The current test-version driver','links':[]}];facts=[]
answer=ask_ai({**payload(info,rows),'sources':evidence},offline=not live)
answer['sources']=evidence;answer['source_mode']='official_pages'
found,_,has_sources=apply_results(rows,answer,checker=lambda *args:True)
assert found[0].get('ai'),'AI did not select a supplied official link'
assert found[0].get('version'),'AI did not identify the current release from live evidence'
if live:assert found[0]['version']==facts[0]['version']
print(json.dumps({'ok':True,'live':live,'ai_matched':True,'url':found[0]['url'],'version':found[0].get('version'),'vendor_verified':bool(facts)}))
