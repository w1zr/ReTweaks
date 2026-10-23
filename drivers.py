"""Detected-component driver links with grounded AI lookup and official-site fallbacks."""
import concurrent.futures
import hashlib
import html
import json
import re
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import webbrowser

VENDORS={
 'nvidia':('NVIDIA','https://www.nvidia.com/en-us/drivers/',('nvidia.com',)),
 'amd':('AMD','https://www.amd.com/en/support/download/drivers.html',('amd.com',)),
 'intel':('Intel','https://www.intel.com/content/www/us/en/download-center/home.html',('intel.com',)),
 'realtek':('Realtek','https://www.realtek.com/Download/Index',('realtek.com',)),
 'qualcomm':('Qualcomm','https://www.qualcomm.com/support',('qualcomm.com',)),
 'broadcom':('Broadcom','https://www.broadcom.com/support/download-search',('broadcom.com',)),
 'mediatek':('MediaTek','https://www.mediatek.com/support',('mediatek.com',)),
 'samsung':('Samsung','https://semiconductor.samsung.com/consumer-storage/support/tools/',('samsung.com',)),
 'western digital':('Western Digital','https://support-en.wd.com/',('wd.com','sandisk.com')),
 'dell':('Dell','https://www.dell.com/support/home/en-us?app=drivers',('dell.com',)),
 'hp':('HP','https://support.hp.com/us-en/drivers',('hp.com',)),
 'lenovo':('Lenovo','https://pcsupport.lenovo.com/us/en/products?link=Drivers',('lenovo.com',)),
 'asus':('ASUS','https://www.asus.com/support/download-center/',('asus.com',)),
 'acer':('Acer','https://www.acer.com/us-en/support/drivers-and-manuals',('acer.com',)),
 'msi':('MSI','https://www.msi.com/support/download',('msi.com',)),
 'gigabyte':('GIGABYTE','https://www.gigabyte.com/Support/Consumer/Download',('gigabyte.com',)),
 'asrock':('ASRock','https://www.asrock.com/support/index.asp?cat=Drivers',('asrock.com',)),
 'microsoft':('Microsoft','https://support.microsoft.com/windows/update-drivers-manually-in-windows-ec62f46c-ff14-c91d-eead-d7126dc1f7b6',('microsoft.com','windowsupdate.com'))}
JUNK=('system manufacturer','system product name','to be filled','default string','unknown','not available')

def vendor(text):
    text=str(text).lower()
    for token,name in [('advanced micro devices','amd'),('ati technologies','amd'),('radeon','amd'),('geforce','nvidia'),('quadro','nvidia'),('micro-star','msi'),('micro star','msi'),('hewlett','hp'),('asustek','asus'),('aorus','gigabyte'),('killer','intel')]:
        if token in text:return name
    for key in VENDORS:
        if re.search(r'\b'+re.escape(key)+r'\b',text):return key
    return None

def clean(value,limit=220):return re.sub(r'[\x00-\x1f\x7f]',' ',str(value or ''))[:limit].strip()
def known(value):return bool(clean(value)) and not any(j in clean(value).lower() for j in JUNK)
def many(value):return value if isinstance(value,list) else ([value] if isinstance(value,dict) else [])

def physical_gpu(name,device_id=''):
    text=clean(name).lower()
    if re.search(r'virtual|remote|indirect|mirror|displaylink|spacedesk|parsec|iddsample|citrix|vmware|hyper-v|usb display|monitor|basic (?:display|render)|software|dummy',text):return False
    if device_id and not str(device_id).upper().startswith('PCI\\'):return False
    return vendor(text) in ('nvidia','amd','intel')


def components(info,devices):
    raw=info.get('raw') if isinstance(info.get('raw'),dict) else {}
    maker=vendor(raw.get('maker',''));model=clean(raw.get('model'))
    board=clean(raw.get('board'));oem=maker if maker in ('dell','hp','lenovo','asus','acer','msi','microsoft') and known(model) else None
    result=[];seen=set()
    def add(kind,name,provider='',version='',date='',hardware='',preferred=None):
        if not known(name) or (kind,name.lower()) in seen:return
        if kind=='Graphics' and not physical_gpu(name):return
        seen.add((kind,name.lower()));v=preferred or vendor(name+' '+provider) or oem or 'microsoft'
        title,url,domains=VENDORS[v]
        result.append({'id':f'component-{len(result)}','kind':kind,'name':clean(name),'vendor':title,'vendor_key':v,'installed':clean(version,80),'installed_date':clean(date,40),'hardware':clean(hardware,160),'url':url,'domains':domains,'oem':clean((raw.get('maker','')+' '+model).strip()) if oem else ''})
    for gpu in many(raw.get('gpus')):
        if physical_gpu(gpu.get('name'),gpu.get('pnp','')):add('Graphics',clean(gpu.get('name')),version=gpu.get('driver',''),date=gpu.get('date',''))
    if not many(raw.get('gpus')) and known(info.get('gpu')):
        for name in str(info['gpu']).split(', '):add('Graphics',name)
    cpu=clean(raw.get('cpu') or info.get('cpu'))
    if known(cpu):add('CPU / chipset',cpu,preferred=oem or vendor(board) or vendor(cpu))
    board_name=board if known(board) else clean(raw.get('maker','')+' '+model)
    if known(board_name):
        add('Motherboard',board_name,preferred=oem or vendor(board))
        add('BIOS',board_name,version=raw.get('bios',''),date=raw.get('bios_date',''),preferred=oem or vendor(board))
    for d in devices:
        if str(d.get('class','')).upper()!='DISPLAY' or not physical_gpu(d.get('name'),d.get('pnp','')):continue
        name=clean(d.get('name'))
        row=next((r for r in result if r['kind']=='Graphics' and r['name'].lower()==name.lower()),None)
        if row:
            if d.get('version'):row['installed']=clean(d['version'],80)
            if d.get('hardware'):row['hardware']=clean(d['hardware'],160)
        else:add('Graphics',name,clean(d.get('provider')),d.get('version',''),d.get('date',''),d.get('hardware',''))
    return result[:32]

SCAN=r'''$ErrorActionPreference='SilentlyContinue'; @(Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceClass -in @('DISPLAY') -and $_.DeviceID -match '^PCI\\' } | Select-Object -First 45 | ForEach-Object { $id=($_.DeviceID -split '\\')[1]; [ordered]@{name=$_.DeviceName; class=$_.DeviceClass; provider=$_.DriverProviderName; version=$_.DriverVersion; date=$(if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')}else{''}); hardware=$id; pnp=$(if($_.DeviceID -match '^PCI\\'){'PCI\\'}else{'OTHER'})} }) | ConvertTo-Json -Depth 3 -Compress'''
def inventory():
    completed=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',SCAN],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,creationflags=0x08000000)
    text=completed.stdout.lstrip('\ufeff').strip()
    if completed.returncode:raise OSError('Windows driver scan did not finish.')
    data=json.loads(text or '[]');return many(data)

def allowed_url(url,domains):
    if not isinstance(url,str) or len(url)>2000 or any(ord(ch)<33 for ch in url) or '\\' in url:return False
    try:
        p=urlsplit(url);host=(p.hostname or '').lower()
        return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and not host.startswith(('forum.','forums.','community.')) and not any(part in p.path.lower() for part in ('/forums/','/community/')) and any(host==d or host.endswith('.'+d) for d in domains)
    except ValueError:return False

def reachable(url,domains):
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self,request,fp,code,msg,headers,newurl):
            if not allowed_url(newurl,domains):raise ValueError('Redirect left the official vendor site.')
            return super().redirect_request(request,fp,code,msg,headers,newurl)
    try:
        if not allowed_url(url,domains):return False
        request=Request(url,method='HEAD',headers={'User-Agent':'RETWEAKS Driver Links/1.0'})
        with build_opener(Redirect()).open(request,timeout=8) as response:return 200<=response.status<400 and allowed_url(response.url,domains)
    except Exception:return False

def payload(info,rows):
    raw=info.get('raw') or {}
    return {'os':clean(info.get('os')),'architecture':clean(raw.get('os_arch')),'pc_model':clean(raw.get('model')),
            'components':[{k:r[k] for k in ('id','kind','name','vendor','installed','hardware','oem','url')} for r in rows]}
def fingerprint(data):return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
def ask_ai(data,offline=False,owner=None):
    exe=Path(__file__).with_name('ai')/'DriverAI.exe'
    process=subprocess.Popen([str(exe)]+(['--offline-test'] if offline else []),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=0x08000000)
    if owner is not None:
        owner.lookup_process=process
        if owner.closed:process.terminate()
    try:
        stdout,_=process.communicate(json.dumps(data,ensure_ascii=True)+'\n',timeout=85)
    except subprocess.TimeoutExpired:
        process.kill();process.communicate();raise OSError('The driver search timed out.')
    finally:
        if owner is not None:owner.lookup_process=None
    answer=json.loads(stdout.strip() or '{}')
    if not answer.get('ok'):raise OSError(answer.get('error','Driver search is unavailable.'))
    return answer

def vendor_results(rows,facts):
    result=[dict(r) for r in rows]
    for row in result:
        for fact in facts:
            if fact.get('component_id')==row['id'] and fact.get('verified') and allowed_url(fact.get('url'),row['domains']):
                row.update(url=fact['url'],version=clean(fact.get('version'),80),date=clean(fact.get('date'),24),note=clean(fact.get('note'),320),verified=True,reachable=True)
                if allowed_url(fact.get('download'),row['domains']):row['download']=fact['download']
    return result

def apply_results(rows,answer,checker=reachable):
    text=answer.get('text','')
    if not isinstance(text,str) or len(text)>150000:raise ValueError('Invalid driver search response.')
    start=text.find('{');end=text.rfind('}')
    data=json.loads(text[start:end+1]);items=data.get('items',[])
    if not isinstance(items,list):raise ValueError('Invalid driver result list.')
    evidence=answer.get('sources',[]) if answer.get('source_mode')=='official_pages' else []
    by_id={r['id']:dict(r) for r in rows};seen=set()
    for item in items[:64]:
        if not isinstance(item,dict):continue
        key=item.get('id');row=by_id.get(key)
        if row is None or key in seen or row.get('verified'):continue
        seen.add(key);url=item.get('url','')
        sources=[source for source in evidence if source.get('component_id')==key and allowed_url(source.get('url'),row['domains'])]
        candidates={row['url']}
        for source in sources:
            candidates.add(source['url'])
            candidates.update(link['url'] for link in source.get('links',[]) if allowed_url(link.get('url'),row['domains']))
        if not sources or not allowed_url(url,row['domains']) or url not in candidates:continue
        version=clean(item.get('version'),80)
        if len(version)<3 or not any(version in source.get('text','') for source in sources):version=''
        row.update(url=url,version=version,date=clean(item.get('date'),24) if version else '',note=clean(item.get('note'),320),ai=True)
    changed=[r for r in by_id.values() if r.get('ai')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(checker,r['url'],r['domains']):r for r in changed}
        for future,row in futures.items():row['reachable']=bool(future.result())
    return list(by_id.values()),'',bool(evidence)

class DriversPage:
    def __init__(self,hub,tab,g,cache_path,enabled=True):
        self.hub=hub;self.g=g;self.tab=tab;self.path=cache_path;self.enabled=enabled;self.started=False;self.busy=False;self.rows=[];self.closed=False;self.lookup_process=None
        body=hub.page(tab,'Drivers','CPU/chipset, GPU, motherboard and BIOS. Automatically matched to this PC; click an official link to continue.')
        toolbar=tk.Frame(body,bg=g['BG']);toolbar.pack(fill='x',pady=4)
        g['RButton'](toolbar,'Refresh driver links',lambda:self.start(True)).pack(side='left',padx=16)
        g['RButton'](toolbar,'Windows Update',lambda:hub.launch('ms-settings:windowsupdate-optionalupdates')).pack(side='left',padx=6)
        self.status=hub.label(body,'Open this page to detect components and find driver links.',10,g['MUTED'])
        hub.label(body,'AI search uses component models, hardware IDs (without serial numbers), installed versions and Windows version. Results are cached for 24 hours.',9,g['MUTED'])
        # in-app downloads from NVIDIA / AMD / Intel and Windows Update (driver_download_ui.py)
        self.downloads=None
        try:
            from driver_download_ui import DriverDownloads
            self.downloads=DriverDownloads(hub,body,g)
        except Exception as exc:hub.label(body,'Driver downloads are unavailable: '+clean(str(exc),160),9,g['MUTED'])
        self.results=tk.Frame(body,bg=g['BG']);self.results.pack(fill='x')
        tab.bind('<Map>',lambda event:self.open(),add='+');hub.bind('<Destroy>',self.destroy,add='+')
    def open(self):
        if self.downloads is not None:self.downloads.open()
        if self.enabled and not self.started:self.started=True;self.wait_info(time.monotonic())
    def wait_info(self,started):
        if self.closed:return
        if self.hub.info or time.monotonic()-started>150:self.start();return
        self.status.config(text='Waiting for the PC scan...');self.hub.after(500,lambda:self.wait_info(started))
    def start(self,force=False):
        if self.closed:return
        # say why nothing new starts instead of ignoring the click
        if not self.enabled:self.status.config(text='Driver lookup is turned off in this session.');return
        if self.busy:self.status.config(text='Already checking driver links… the list updates when it finishes.');return
        self.busy=True;self.status.config(text='Detecting installed drivers...');info=dict(self.hub.info or {})
        def worker():
            try:
                scan_error=''
                try:devices=inventory()
                except (OSError,ValueError,subprocess.TimeoutExpired) as exc:devices=[];scan_error='Some installed-driver details were unavailable. '
                if self.closed:return
                rows=components(info,devices);data=payload(info,rows);stamp=fingerprint(data)
                self.hub.q.put(('drivers',{'phase':'detected','rows':rows,'status':scan_error+'Checking current official vendor sources...'}))
                cached={}
                try:cached=json.loads(self.path.read_text(encoding='utf-8'))
                except (OSError,ValueError):pass
                if not isinstance(cached,dict):cached={}
                cache_time=cached.get('time',0)
                cache_ok=isinstance(cache_time,(int,float)) and isinstance(cached.get('answer'),dict) and cached.get('format')==2 and cached.get('fingerprint')==stamp and 0<=time.time()-cache_time<86400
                if not force and cache_ok:
                    answer=cached['answer'];facts=cached.get('facts',[]);cached_hit=True
                    rows=vendor_results(rows,facts)
                else:
                    from driver_sources import gather
                    evidence,facts=gather(info,rows)
                    if self.closed:return
                    rows=vendor_results(rows,facts)
                    self.hub.q.put(('drivers',{'phase':'sources','rows':rows,'status':'Current vendor sources loaded. AI is matching the remaining links...'}))
                    request={**data,'sources':evidence}
                    if not evidence:raise OSError('Official sites could not be checked right now.')
                    try:answer=ask_ai(request,owner=self)
                    except OSError as exc:
                        self.hub.q.put(('drivers',{'phase':'error','rows':rows,'status':clean(str(exc),240)}));return
                    answer['sources']=evidence;answer['source_mode']='official_pages';cached_hit=False
                found,_,has_evidence=apply_results(rows,answer)
                if not cached_hit:
                    try:
                        self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(json.dumps({'format':2,'fingerprint':stamp,'time':time.time(),'answer':answer,'facts':facts}),encoding='utf-8')
                    except OSError:pass
                count=sum(bool(r.get('ai') or r.get('verified')) for r in found)
                self.hub.q.put(('drivers',{'phase':'done','rows':found,'status':f'{count} matched official links. '+('Cached check - ' if cached_hit else 'Checked - ')+time.strftime('%b %d, %H:%M',time.localtime(cache_time if cached_hit else time.time()))}))
            except Exception as exc:self.hub.q.put(('drivers',{'phase':'error','status':clean(str(exc),240)+' You can still open the detected components’ official support pages.'}))
        threading.Thread(target=worker,daemon=True).start()
    def event(self,data):
        if self.closed:return
        self.status.config(text=data['status'])
        if 'rows' in data:self.rows=data['rows'];self.render()
        if data['phase'] in ('done','error'):self.busy=False
    def render(self):
        for child in self.results.winfo_children():child.destroy()
        for row in self.rows:
            text=f"{row['kind']} - {row['name']}"
            details=f"Installed: {row['installed'] or 'Version not available'}"
            if row['kind']=='CPU / chipset':details+='\nCPU updates are supplied through chipset drivers and Windows Update.'
            if row['kind']=='BIOS':details+='\nUse the exact motherboard model and revision shown on the official support page.'
            if row.get('ai') or row.get('verified'):
                label='Latest vendor-matched release' if row.get('verified') else 'Latest found by AI'
                details+=f"\n{label}: {row.get('version') or 'Version not confirmed'}"
                if row.get('date'):details+=' - '+row['date']
                details+='\n'+(row.get('note') or 'Matched using current web sources.')
                if not row.get('reachable'):details+='\nLink availability could not be checked.'
            else:details+='\nOfficial support page - latest release not verified.'
            box=self.hub.box(self.results,text,details)
            self.hub.action(box,'Open '+row['vendor']+(' BIOS support' if row['kind']=='BIOS' else ' driver page'),lambda r=row:self.open_link(r))
            if row.get('download'):self.hub.action(box,'Download official driver',lambda r=row:self.open_link({**r,'url':r['download']}))
            self.hub.label(box,urlsplit(row['url']).hostname,9,self.g['MUTED'])
    def open_link(self,row):
        if allowed_url(row['url'],row['domains']):webbrowser.open(row['url'])
    def theme(self):pass
    def destroy(self,event):
        if event.widget is self.hub:
            self.closed=True
            if self.downloads is not None:self.downloads.destroy()
            if self.lookup_process is not None:
                try:self.lookup_process.terminate()
                except OSError:pass
