"""Driver matching checks; no network, downloads or system changes."""
import json
from drivers import components,payload,apply_results,allowed_url,fingerprint,vendor_results
info={'os':'Windows 11','gpu':'NVIDIA GeForce RTX 4060','cpu':'AMD Ryzen 9','raw':{'host':'SECRET-PC','user':'SECRET-USER','serial':'SECRET-SERIAL','model':'Test PC','maker':'Test Maker','board':'ASUSTeK TUF GAMING B650-PLUS','os_arch':'64-bit','gpus':[{'name':'NVIDIA GeForce RTX 4060','driver':'32.0.test'}]}}
rows=components(info,[{'name':'Intel Wi-Fi 6 AX200','class':'NET','provider':'Intel','version':'1.2','hardware':'VEN_8086&DEV_1234'}])
assert len(rows)==5
assert {r['kind'] for r in rows}=={'Graphics','CPU / chipset','Motherboard','BIOS','Network'}
assert any('Wi-Fi' in r['name'] for r in rows)
assert rows[0]['vendor']=='NVIDIA' and rows[1]['vendor']=='ASUS' and rows[2]['vendor']=='ASUS'
data=payload(info,rows)
assert 'SECRET' not in json.dumps(data)
assert fingerprint(data)==fingerprint(payload(info,rows))
for url in ('http://nvidia.com/test','https://nvidia.com.evil.example/test','https://nvidia.com@evil.example/test','https://evil.example/nvidia.com','https://www.nvidia.com:8080/test','https://forums.nvidia.com/test','file:///C:/test.exe','https://www.nvidia.com/ test'):
    assert not allowed_url(url,('nvidia.com',)),url
assert allowed_url('https://www.nvidia.com/en-us/drivers/',('nvidia.com',))
answer={'text':json.dumps({'items':[{'id':rows[0]['id'],'url':'https://www.nvidia.com/en-us/drivers/','version':'test-version','date':'','note':'A match'},{'id':rows[1]['id'],'url':'https://evil.example/driver.exe','version':'fake'},{'id':'unknown','url':'https://www.nvidia.com/'}]}),'source_mode':'official_pages','sources':[{'component_id':rows[0]['id'],'url':'https://www.nvidia.com/en-us/drivers/','text':'The current test-version driver','links':[]}]}
found,source,grounded=apply_results(rows,answer,checker=lambda *args:True)
assert grounded and found[0]['version']=='test-version' and found[0]['ai'] and found[0]['reachable']
assert not found[1].get('ai') and 'asus.com' in found[1]['url']
assert source==''
answer['sources']=[]
found,_,grounded=apply_results(rows,answer,checker=lambda *args:True)
assert not grounded and not any(r.get('ai') for r in found)
assert components({'gpu':'Unknown','cpu':'AMD Ryzen 9'},[])[0]['vendor']=='AMD'
oem=components({'raw':{'maker':'Dell Inc.','model':'XPS 15','board':'Dell 123'}},[{'name':'Realtek Audio','class':'MEDIA','provider':'Realtek'}])
assert all(r['vendor']=='Dell' for r in oem)
facts=[{'component_id':rows[0]['id'],'url':'https://www.nvidia.com/en-us/drivers/details/123/','version':'test-version','date':'2026-10-01','verified':True,'download':'https://us.download.nvidia.com/test.exe'}]
assert vendor_results(rows,facts)[0]['verified']
from driver_sources import nvidia,fetch
from unittest.mock import patch
selector='var nvProducts = ["GeForce | RTX 40 | NVIDIA GeForce RTX 4060"]; var nvProductsJson = [\'{"pst":"127","d2":"1023"}\'];'
release={'Success':'1','IsBeta':'0','IsWHQL':'1','Version':'test-version','ReleaseDateTime':'Tue Oct 06, 2026','DetailsURL':'https://www.nvidia.com/en-us/drivers/details/123/','DownloadURL':'https://us.download.nvidia.com/test.exe'}
with patch('driver_sources.fetch',side_effect=[selector,json.dumps({'IDS':[{'downloadInfo':release}]})]) as get:
    exact=nvidia(rows[0],{'os':'Windows 11'})
    assert exact['verified'] and exact['version']=='test-version'
    assert 'pfid=1023' in get.call_args.args[0] and 'osID=135' in get.call_args.args[0]
with patch('driver_sources.fetch',return_value=selector) as get:
    assert nvidia({**rows[0],'name':'NVIDIA GeForce RTX 4070'},{'os':'Windows 11'}) is None
    assert get.call_count==1
try:fetch('https://us.download.nvidia.com/test.exe',('nvidia.com',))
except ValueError:pass
else:raise AssertionError('An installer must never be fetched automatically')
print('PASS: hardware/OEM matching, installed versions, bounded private-data-free payload, official-domain checks, grounded results and ungrounded fallback. No network requests sent.')

# Virtual adapters must never become driver rows, even with a GPU vendor in the name.
from drivers import physical_gpu
for name in ('NVIDIA Virtual Monitor','AMD Remote Display','Intel Indirect Display','Microsoft Basic Display Adapter','Parsec Virtual Display','DisplayLink USB Graphics'):
    assert not physical_gpu(name),name
assert physical_gpu('NVIDIA GeForce RTX 4060','PCI\\')
assert not physical_gpu('NVIDIA GeForce RTX 4060','ROOT\\DISPLAY')
filtered=components({'raw':{'gpus':[{'name':'NVIDIA GeForce RTX 4060','pnp':'PCI\\'},{'name':'NVIDIA Virtual Monitor','pnp':'OTHER'},{'name':'Intel UHD Graphics','pnp':'OTHER'}]}},[{'name':'Parsec Virtual Display','class':'DISPLAY'}])
assert [r['name'] for r in filtered]==['NVIDIA GeForce RTX 4060']
print('PASS: physical GPU filtering excludes virtual, remote, software and monitor adapters.')
