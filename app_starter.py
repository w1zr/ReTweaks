"""App Starter: deliberate batch downloads/installs through Windows Package Manager."""
import html
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler

from app_catalog import CATALOG,DETAILS,CATEGORIES
from app_troubleshooting import failure_record,explain

APPS={r[0]:r for r in CATALOG}
PRESETS={
 'Everyday':('chrome','discord','spotify','drive'),
 'Gaming':('chrome','epic','discord','steam','spotify','medal'),
 'Creator':('chrome','drive','capcut','obs','medal'),
 'Full setup':tuple(r[0] for r in CATALOG[:13]),
 'New PC essentials':('chrome','sevenzip','vlc','sumatra','bitwarden','powertoys','everything','sharex'),
 'Developer':('vscode','git','github','python','node','terminal','notepadplusplus'),
 'Creative tools':('obs','gimp','inkscape','krita','blender','audacity','handbrake','kdenlive')}


def winget_path():
    found=shutil.which('winget.exe')
    if found:return found
    candidate=Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft/WindowsApps/winget.exe'
    return str(candidate) if candidate.is_file() else None


def command(executable,key,mode,destination):
    if key not in APPS or not APPS[key][3]:raise ValueError('Unknown package')
    if mode not in ('download','install'):raise ValueError('Unknown action')
    args=[executable,mode,'--id',APPS[key][3],'--exact','--source','winget','--accept-source-agreements','--accept-package-agreements','--disable-interactivity']
    if mode=='download':args+=['--download-directory',str(Path(destination)/key)]
    else:args+=['--silent']
    return args


def nvidia_url(url):
    try:
        p=urlsplit(url);host=(p.hostname or '').lower()
        return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and (host=='nvidia.com' or host.endswith('.nvidia.com'))
    except ValueError:return False


class NvidiaRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        if not nvidia_url(newurl):raise ValueError('Download left NVIDIA’s official site')
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def nvidia_link():
    opener=build_opener(NvidiaRedirect())
    req=Request(APPS['nvidia'][4],headers={'User-Agent':'RETWEAKS App Starter/1.0'})
    with opener.open(req,timeout=25) as response:page=response.read(3000000).decode('utf-8',errors='replace')
    links=[html.unescape(u) for u in re.findall(r'https://[^\s\"<>]+?\.exe',page) if 'nvidia_app' in u.lower()]
    link=next((u for u in links if nvidia_url(u)),None)
    if not link:raise OSError('Automatic download unavailable; use Official site below.')
    return link


def download_nvidia(destination,cancel,progress,link=None):
    link=link or nvidia_link()
    if not nvidia_url(link):raise ValueError('Invalid NVIDIA download source')
    opener=build_opener(NvidiaRedirect())
    target=Path(destination)/'nvidia';target.mkdir(parents=True,exist_ok=True)
    final=target/'NVIDIA-App-Setup.exe';partial=target/'NVIDIA-App-Setup.exe.part'
    try:
        with opener.open(Request(link,headers={'User-Agent':'RETWEAKS App Starter/1.0'}),timeout=30) as response,partial.open('wb') as out:
            if 'text/html' in response.headers.get('Content-Type','').lower():raise OSError('Server returned a web page instead of an installer')
            total=int(response.headers.get('Content-Length') or 0);received=0;last=0
            while True:
                if cancel.is_set():raise InterruptedError('Download stopped')
                chunk=response.read(262144)
                if not chunk:break
                out.write(chunk);received+=len(chunk)
                if received>1500000000:raise OSError('Unexpected installer size')
                if time.monotonic()-last>0.5:
                    progress(f'Downloading {received//1048576} MB'+(f' / {total//1048576} MB' if total else ''));last=time.monotonic()
        if not received or (total and received!=total):raise OSError('Download was truncated or empty; please retry.')
        # Do not run a direct download unless Windows verifies its publisher signature.
        script="$s=Get-AuthenticodeSignature -LiteralPath $env:RETWEAKS_INSTALLER_PATH; if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'NVIDIA'){exit 0}else{exit 1}"
        check=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env={**os.environ,'RETWEAKS_INSTALLER_PATH':str(partial)},capture_output=True,timeout=45,creationflags=0x08000000)
        if check.returncode:raise OSError('NVIDIA publisher signature could not be verified; use Official site.')
        partial.replace(final);return final
    finally:
        if partial.exists():partial.unlink()


def log_tail(path):
    if path is None:return ''
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0,2);stream.seek(max(0,stream.tell()-12000));return stream.read().decode('utf-8',errors='replace')
    except OSError:return ''


def downloaded_payload(folder):
    return any(p.is_file() and p.stat().st_size>0 and p.suffix.lower() in ('.exe','.msi','.msix','.msixbundle','.appx','.appxbundle','.zip','.7z') for p in Path(folder).rglob('*'))


class Runner:
    def __init__(self,events,destination,enable_ai=True):
        self.events=events;self.enable_ai=enable_ai;self.destination=Path(destination);self.stop=threading.Event();self.busy=False
    def start(self,keys,mode):
        keys=list(dict.fromkeys(keys))
        if self.busy or not keys:return False
        if mode not in ('download','install') or any(k not in APPS for k in keys):raise ValueError('Invalid app selection')
        self.stop.clear();self.busy=True
        threading.Thread(target=self.work,args=(keys,mode),daemon=True).start();return True
    def work(self,keys,mode):
        results=[];executable=winget_path()
        try:
            self.destination.mkdir(parents=True,exist_ok=True)
            from app_sources import latest_plan
            plan=latest_plan(keys,executable,self.stop,self.events.put,self.enable_ai)
            for index,key in enumerate(keys,1):
                if self.stop.is_set():break
                self.events.put(('status',key,f'{index}/{len(keys)} • '+('Downloading…' if mode=='download' else 'Installing…')))
                code=None;log_path=None
                try:
                    if key=='nvidia':
                        path=download_nvidia(self.destination,self.stop,lambda value:self.events.put(('status',key,value)),link=plan.get(key,{}).get('url'))
                        if mode=='install':
                            os.startfile(str(path));status='Installer opened — complete NVIDIA setup'
                        else:status='Downloaded • publisher verified'
                    else:
                        if not executable:raise OSError('WinGet missing — use Get App Installer or Official site.')
                        if mode=='download':(self.destination/key).mkdir(parents=True,exist_ok=True)
                        args=command(executable,key,mode,self.destination)
                        version=plan.get(key,{}).get('version','')
                        if version and re.fullmatch(r'[A-Za-z0-9._+~-]{1,100}',version):args+=['--version',version]
                        # Drain output to a per-app log, avoiding pipe deadlocks on large installers.
                        log_dir=self.destination/'logs';log_dir.mkdir(exist_ok=True)
                        log_path=log_dir/(key+'.log')
                        with log_path.open('w',encoding='utf-8') as log:
                            process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
                            try:code=process.wait(timeout=1800)
                            except subprocess.TimeoutExpired:
                                process.terminate();process.wait(timeout=10);raise OSError('Timed out — check the log and retry.')
                        unsigned=code & 0xffffffff
                        if unsigned==0:
                            if mode=='download' and not downloaded_payload(self.destination/key):raise OSError('Download reported success but no complete installer was found. Open the log or retry.')
                            status='Downloaded' if mode=='download' else 'Installed'
                        elif mode=='install' and unsigned in (0x8A15002B,0x8A150061):status='Already installed / no update available'
                        else:raise OSError(f'Needs attention ({unsigned:#x}) — open logs or Official site.')
                    results.append((key,True));self.events.put(('success',key));self.events.put(('status',key,status))
                except InterruptedError:
                    self.events.put(('status',key,'Stopped'));break
                except Exception as exc:
                    results.append((key,False));self.events.put(('status',key,str(exc)[:230]))
                    self.events.put(('failure',key,failure_record(key,APPS[key],mode,str(exc),code,log_tail(log_path))))
        except Exception as exc:
            self.events.put(('error',str(exc)[:230]))
            finished={key for key,_ in results}
            for key in keys:
                if key not in finished:
                    results.append((key,False))
                    self.events.put(('failure',key,failure_record(key,APPS[key],mode,str(exc))))
        finally:
            self.busy=False;self.events.put(('done',results,self.stop.is_set()))


class AppStarterPage:
    def __init__(self,hub,tab,g,root):
        self.hub=hub;self.g=g;self.events=queue.Queue();self.closed=False;self.rows={};self.choices={};self.releases={};self.statuses={};self.expanded=set();self.checking=False;self.review_stop=threading.Event();self.failures={};self.help_windows={};self.filter_job=None;self.cards={}
        self.destination=Path.home()/'Downloads'/'RETWEAKS Apps';self.runner=Runner(self.events,self.destination,enable_ai=hub.enable_ai)
        body=hub.page(tab,'App Starter','100 useful apps for a new PC. Browse by category, review a package, and choose what to install.')
        hub.label(body,'Install downloads and sets up the selected apps, or updates an existing version. Starting accepts their license agreements. Some vendor setups need your input.',10,g['MUTED'])
        toolbar=tk.Frame(body,bg=g['BG']);toolbar.pack(fill='x',padx=16,pady=8)
        self.mode=g['RSelect'](toolbar,['Install apps','Download installers'],width=220);self.mode.pack(side='left')
        g['RButton'](toolbar,'Open downloads',lambda:self.open_folder(self.destination)).pack(side='left',padx=8)
        g['RButton'](toolbar,'Open logs',lambda:self.open_folder(self.destination/'logs')).pack(side='left')
        hub.label(body,'CHOOSE A PACKAGE',11,g['ACC'])
        desc={'Everyday':'Browser, chat, music and files','Gaming':'Launchers, chat, music and clips','Creator':'Editing, streaming and file sync','Full setup':'Original 13-app package, including device utilities'}
        self.buttons=[]
        desc.update({'New PC essentials':'A focused starting selection for everyday use','Developer':'Editors, runtimes and version-control tools','Creative tools':'Open-source media and design tools'})
        for pair in (('Everyday','Gaming'),('Creator','Full setup'),('New PC essentials','Developer'),('Creative tools',)):
            line=tk.Frame(body,bg=g['BG']);line.pack(fill='x',pady=4)
            for name in pair:
                card=g['Card'](line);card.pack(side='left',fill='both',expand=True,padx=(0,10))
                hub.label(card.body,name,15);hub.label(card.body,desc[name],9,g['MUTED'])
                button=g['RButton'](card.body,'Review package',lambda n=name:self.preset(n));button.pack(anchor='w',padx=16,pady=(4,12));self.buttons.append((button,name))
        self.status=hub.label(body,'Choose a package to review it. Nothing installs until you press Install selected.',10,g['MUTED'])
        self.selection_title=hub.label(body,'All apps',18)
        actions=tk.Frame(body,bg=g['BG']);actions.pack(fill='x',padx=16,pady=8)
        self.start_button=g['RButton'](actions,'Install selected',self.start_selected,kind='primary');self.start_button.pack(side='left')
        self.check_button=g['RButton'](actions,'Check latest with AI',self.check_latest);self.check_button.pack(side='left',padx=8)
        self.stop_button=g['RButton'](actions,'Stop queue',self.stop);self.stop_button.pack(side='left')
        controls=tk.Frame(body,bg=g['BG']);controls.pack(fill='x',padx=16,pady=4)
        for label,callback in [('Add / browse all apps',self.browse_all),('Select shown apps',self.select_shown),('Clear selection',self.clear)]:g['RButton'](controls,label,callback).pack(side='left',padx=(0,8))
        self.retry_button=g['RButton'](controls,'Retry failed',self.retry_failed);self.retry_button.pack(side='left')
        filters=tk.Frame(body,bg=g['BG']);filters.pack(fill='x',padx=16,pady=8)
        self.search=tk.StringVar();g['REntry'](filters,self.search,width_px=300).pack(side='left')
        self.category=g['RSelect'](filters,['All categories']+CATEGORIES,width=230,command=lambda *_:self.filter_apps());self.category.pack(side='left',padx=8)
        self.search.trace_add('write',lambda *_:self.queue_filter())
        self.page_label=hub.label(body,'',10,g['MUTED'])
        hub.label(body,'Search by app name or use category filters. This is a curated library, not a measured download ranking. Scroll to see every app. Your selections stay selected when searching or filtering.',9,g['MUTED'])
        self.count=hub.label(body,'0 apps selected',10,g['ACC'])
        self.failure_picker=g['RSelect'](body,['No failed apps'],width=370,command=self.pick_failure)
        self.failure_picker.pack(anchor='w',padx=16,pady=5)
        hub.label(body,'AI checks current source information; WinGet resolves and verifies the actual installer. NVIDIA downloads use its official site and a publisher-signature check.',9,g['MUTED'])
        self.grid=tk.Frame(body,bg=g['BG']);self.grid.pack(fill='x',padx=(0,12))
        from branding import ASSETS
        from PIL import Image,ImageTk,ImageDraw
        self.logos={}
        for key in APPS:
            path=ASSETS/'apps'/(key+'.png')
            if path.is_file():
                with Image.open(path) as source:
                    image=source.convert('RGBA')
                    # Give near-black/white artwork contrast in both app themes.
                    pixels=list(image.resize((24,24),Image.Resampling.BOX).getdata());weight=sum(pixel[3] for pixel in pixels) or 1
                    brightness=sum(sum(pixel[:3])*pixel[3] for pixel in pixels)/(3*weight)
                    if brightness<80 or brightness>200:
                        plate=Image.new('RGBA',image.size)
                        ImageDraw.Draw(plate).rounded_rectangle((0,0,image.width-1,image.height-1),radius=32,fill='#edf2f7' if brightness<80 else '#253044')
                        plate.alpha_composite(image);image=plate
                    image.thumbnail((80,80),Image.Resampling.LANCZOS)
                    self.logos[key]=ImageTk.PhotoImage(image,master=hub)
            else:self.logos[key]=None
        for key in APPS:self.choices[key]=tk.BooleanVar(value=False)
        self.base_keys=list(APPS);self.visible=list(APPS);self.render_apps()
        hub.action(body,'Get Microsoft App Installer',lambda:hub.launch('https://apps.microsoft.com/detail/9nblggh4nns1'))
        self.mode.command=lambda *args:self.update_mode()
        hub.bind('<Destroy>',self.destroy,add='+');self.poll()
    def queue_filter(self):
        if self.filter_job:self.hub.after_cancel(self.filter_job)
        self.filter_job=self.hub.after(180,self.filter_apps)
    def filter_apps(self):
        if self.filter_job:self.hub.after_cancel(self.filter_job);self.filter_job=None
        query=self.search.get().strip().casefold();category=self.category.get()
        self.visible=[k for k in self.base_keys if (category=='All categories' or APPS[k][2]==category) and all(word in (' '.join(str(v or '') for v in APPS[k])+' '+DETAILS[k]).casefold() for word in query.split())]
        self.render_apps()
    def retry_failed(self):
        if not self.idle():return
        keys=[key for key,report in self.failures.items() if report['mode']==self.action_mode()]
        if not keys:self.status.config(text='No failed apps for the currently selected install/download mode.');return
        for key,var in self.choices.items():var.set(key in keys)
        self.update_count();self.start_selected()
    def refresh_failures(self):
        self.failure_picker.values=[APPS[key][1] for key in self.failures] or ['No failed apps']
        self.failure_picker.set(f'{len(self.failures)} failed apps - choose for help' if self.failures else 'No failed apps')
    def pick_failure(self,name):
        key=next((key for key in self.failures if APPS[key][1]==name),None)
        if key:self.help_failure(key)
    def help_text(self,report,result):
        code=report.get('code');code='Not available' if code is None else f'{code:#010x}'
        return (result['source']+'\n\n'+result['summary']+'\n\n'+'\n'.join(f'{i}. {step}' for i,step in enumerate(result['steps'],1))+
                '\n\n'+result.get('note','')+'\n\nAction: '+report['mode']+'\nPackage: '+str(report.get('package') or 'Official NVIDIA download')+
                '\nReturn code: '+code+'\nError: '+report['error']+'\n\nRedacted log excerpt:\n'+(report.get('log_excerpt') or 'No log output was available.'))
    def close_help(self,info):
        info['token'].closed=True
        process=info['token'].lookup_process
        if process is not None and process.poll() is None:
            try:process.terminate()
            except OSError:pass
        if info['window'].winfo_exists():info['window'].destroy()
    def help_failure(self,key):
        if key not in self.failures:return
        current=self.help_windows.get(key)
        if current and current['window'].winfo_exists():current['window'].lift();return
        from types import SimpleNamespace
        from app_troubleshooting import fallback
        report=dict(self.failures[key]);window=tk.Toplevel(self.hub);window.title('Download help - '+APPS[key][1]);window.geometry('780x650');window.configure(bg=self.g['BG']);window.transient(self.hub)
        self.hub.label(window,APPS[key][1]+' - '+report['mode']+' needs attention',16)
        self.hub.label(window,'AI help sends only the error, app identity and the redacted log excerpt below. Suggested fixes are never run automatically.',10,self.g['MUTED'])
        text_frame=tk.Frame(window,bg=self.g['PANEL']);text_frame.pack(fill='both',expand=True,padx=16,pady=8)
        text=tk.Text(text_frame,wrap='word',bg=self.g['PANEL'],fg=self.g['FG'],font=(self.g['UI'],10),relief='flat',padx=14,pady=14)
        scroll=tk.Scrollbar(text_frame,command=text.yview);scroll.pack(side='right',fill='y');text.config(yscrollcommand=scroll.set)
        text.pack(side='left',fill='both',expand=True);text.insert('end',self.help_text(report,fallback(report)));text.config(state='disabled')
        buttons=tk.Frame(window,bg=self.g['BG']);buttons.pack(fill='x',padx=16,pady=10)
        token=SimpleNamespace(closed=False,lookup_process=None)
        def ask():
            button.set_enabled(False);text.config(state='normal');text.delete('1.0','end');text.insert('end','AI is reviewing this app error...');text.config(state='disabled')
            def work():
                from drivers import ask_ai
                result=explain(report,self.hub.enable_ai,ask=lambda data:ask_ai(data,owner=token))
                if not token.closed:self.events.put(('diagnosis',key,token,result))
            threading.Thread(target=work,daemon=True).start()
        button=self.g['RButton'](buttons,'Ask AI to explain',ask);button.pack(side='left',padx=(0,8))
        def retry():
            if not self.idle():self.status.config(text='Wait for the current queue before retrying.');return
            for k,var in self.choices.items():var.set(k==key)
            self.update_count();self.start_keys([key],report['mode'])
        self.g['RButton'](buttons,'Retry '+report['mode'],retry).pack(side='left',padx=(0,8))
        self.g['RButton'](buttons,'Official site',lambda:self.hub.launch(APPS[key][4])).pack(side='left')
        info={'window':window,'text':text,'button':button,'token':token,'report':report};self.help_windows[key]=info
        window.protocol('WM_DELETE_WINDOW',lambda:self.close_help(info))

    def action_mode(self):return 'install' if self.mode.get()=='Install apps' else 'download'
    def update_mode(self):
        self.start_button.label=('Install' if self.action_mode()=='install' else 'Download')+' selected';self.start_button._draw()
    def update_count(self):self.count.config(text=f'{sum(v.get() for v in self.choices.values())} apps selected')
    def idle(self):return not self.runner.busy and not self.checking
    def lock(self,busy):
        self.start_button.set_enabled(not busy);self.check_button.set_enabled(not busy)
        for b,_ in self.buttons:b.set_enabled(not busy)
    def clear(self):
        if not self.idle():return
        for var in self.choices.values():var.set(False)
        self.update_count()
    def select_shown(self):
        if not self.idle():return
        for key in self.visible:self.choices[key].set(True)
        self.update_count()
    def browse_all(self):
        if not self.idle():return
        self.base_keys=list(APPS);self.search.set('');self.category.set('All categories');self.selection_title.config(text='All 100 apps');self.filter_apps()
    def preset(self,name):
        if not self.idle():return
        for key,var in self.choices.items():var.set(key in PRESETS[name])
        self.base_keys=list(PRESETS[name]);self.search.set('');self.category.set('All categories');self.visible=list(self.base_keys);self.selection_title.config(text=name+' package - select what you want')
        self.render_apps();self.update_count();self.status.config(text='Review app details or untick anything you do not want, then press Install selected.')
        if self.hub.enable_ai:self.check_latest()
    def render_apps(self):
        # Reuse cards so typing and switching filters do not rebuild 100 widget trees.
        for item in self.cards.values():item['card'].grid_remove()
        self.rows={};self.detail_labels={}
        for column in range(3):self.grid.columnconfigure(column,weight=1,uniform='apps')
        self.page_label.config(text=f'{len(self.visible)} matching apps | {len(APPS)} in library - scroll to browse')
        for i,key in enumerate(self.visible):
            if key not in self.cards:self.build_card(key)
            item=self.cards[key]
            item['card'].grid(row=i//3,column=i%3,sticky='nsew',padx=(0,8),pady=5)
            item['status'].config(text=self.statuses.get(key,'Ready to check'))
            item['detail'].config(text=self.detail_text(key))
            self.rows[key]=item['status'];self.detail_labels[key]=item['detail']
            self.refresh_card(key)
        if hasattr(self,'empty_label'):self.empty_label.destroy()
        if not self.visible:
            self.empty_label=tk.Label(self.grid,text='No apps match. Try another name or category.',bg=self.g['BG'],fg=self.g['MUTED'])
            self.empty_label.grid(row=0,column=0,columnspan=3,pady=24)
    def build_card(self,key):
        _,name,category,package,website=APPS[key]
        # Scrolling can clip native child windows on Windows. Keep the outer
        # card height independent of those temporary allocated child sizes.
        card=self.g['Card'](self.grid,elastic=True)
        tk.Label(card.body,image=self.logos[key],text='' if self.logos[key] else name[:2].upper(),font=(self.g['UI'],24,'bold'),fg=self.g['ACC'],bg=self.g['PANEL'],height=80 if self.logos[key] else 2).pack(pady=(14,3))
        label=self.hub.label(card.body,name,13);label.config(anchor='center',justify='center',wraplength=220)
        label=self.hub.label(card.body,category,9,self.g['MUTED']);label.config(anchor='center',justify='center',wraplength=220)
        self.g['RCheck'](card.body,'Include',self.choices[key],command=self.update_count).pack(pady=4)
        toggle=self.g['RButton'](card.body,'View details',lambda k=key:self.toggle_details(k));toggle.pack(pady=4)
        status=self.hub.label(card.body,'Ready to check',9,self.g['MUTED']);status.config(wraplength=220)
        detail=self.hub.label(card.body,self.detail_text(key),9,self.g['MUTED']);detail.config(wraplength=220);detail.pack_forget()
        site=self.g['RButton'](card.body,'Official site',lambda k=key:self.hub.launch(APPS[k][4]));site.pack(pady=(3,12))
        help_button=self.g['RButton'](card.body,'Help fix this',lambda k=key:self.help_failure(k))
        self.cards[key]={'card':card,'status':status,'detail':detail,'toggle':toggle,'site':site,'help':help_button,'fit_job':None}
        card.body.bind('<Configure>',lambda event,k=key:self.queue_card_fit(k),add='+')
    def queue_card_fit(self,key):
        item=self.cards.get(key)
        if not item or item['fit_job'] is not None:return
        item['fit_job']=self.hub.after_idle(lambda:self.fit_card(key))
    def fit_card(self,key):
        item=self.cards.get(key)
        if not item:return
        item['fit_job']=None;card=item['card']
        if not card.winfo_exists():return
        height=card.body.winfo_reqheight()+2*card.inset
        if int(card.cget('height'))!=height:card.configure(height=height)
    def refresh_card(self,key):
        if key not in self.cards:return
        item=self.cards[key];expanded=key in self.expanded
        item['toggle'].label='Hide details' if expanded else 'View details';item['toggle']._draw()
        if expanded:item['detail'].pack(fill='x',padx=16,pady=4,before=item['site'])
        else:item['detail'].pack_forget()
        if key in self.failures:item['help'].pack(pady=(3,12))
        else:item['help'].pack_forget()
        self.queue_card_fit(key)
    def detail_text(self,key):
        record=self.releases.get(key,{})
        text=DETAILS[key]+'\n\nLatest: '+(record.get('version') or 'Resolved from the live source when you start.')
        text+='\nSource: '+record.get('source',APPS[key][3] or 'NVIDIA official download page')
        if record.get('ai'):text+='\nAI matched to current release evidence.'
        elif record:text+='\nSource checked; AI confirmation unavailable.'
        if record.get('url'):text+='\nDownload host: '+(urlsplit(record['url']).hostname or '')
        return text
    def toggle_details(self,key):
        if key in self.expanded:self.expanded.remove(key)
        else:self.expanded.add(key)
        self.refresh_card(key)
    def check_latest(self):
        if not self.idle():return
        keys=[k for k,v in self.choices.items() if v.get()]
        if not keys:self.status.config(text='Select apps to check their latest releases.');return
        self.checking=True;self.review_stop.clear();self.lock(True);self.status.config(text='Checking current releases…')
        def work():
            try:
                from app_sources import latest_plan
                latest_plan(keys,winget_path(),self.review_stop,self.events.put,self.hub.enable_ai)
            finally:self.events.put(('checked',))
        threading.Thread(target=work,daemon=True).start()
    def start_selected(self):
        if not self.idle():return
        keys=[k for k,v in self.choices.items() if v.get()]
        if not keys:self.status.config(text='Select at least one app first.');return
        self.start_keys(keys,self.action_mode())
    def start_keys(self,keys,mode):
        if not self.idle():return
        for key in keys:
            self.failures.pop(key,None);self.refresh_card(key)
            self.statuses[key]='Queued'
            if key in self.rows:self.rows[key].config(text='Queued')
        self.refresh_failures()
        if self.runner.start(keys,mode):self.status.config(text=f'Checking latest sources for {len(keys)} apps…');self.lock(True)
    def stop(self):
        if self.checking:self.review_stop.set();self.status.config(text='Stopping the release check…')
        if self.runner.busy:self.runner.stop.set();self.status.config(text='Stopping after the current app. Remaining apps will not start.')
    def open_folder(self,path):
        try:path.mkdir(parents=True,exist_ok=True);os.startfile(str(path))
        except OSError as exc:self.status.config(text=str(exc))
    def poll(self):
        if self.closed:return
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='status':
                    self.statuses[event[1]]=event[2]
                    if event[1] in self.rows:self.rows[event[1]].config(text=event[2])
                    self.status.config(text=APPS[event[1]][1]+' • '+event[2])
                elif event[0]=='failure':
                    self.failures[event[1]]=event[2];self.refresh_failures()
                    self.refresh_card(event[1])
                elif event[0]=='success':
                    self.failures.pop(event[1],None);self.refresh_failures();self.refresh_card(event[1])
                elif event[0]=='diagnosis':
                    key,token,result=event[1:]
                    info=self.help_windows.get(key)
                    if info and info['token'] is token and info['window'].winfo_exists():
                        info['text'].config(state='normal');info['text'].delete('1.0','end');info['text'].insert('end',self.help_text(self.failures.get(key,info['report']),result));info['text'].config(state='disabled');info['button'].set_enabled(True)
                elif event[0]=='release':
                    self.releases[event[1]]=event[2]
                    text=('AI checked • ' if event[2].get('ai') else 'Source checked • ')+(event[2].get('version') or 'current installer')
                    self.statuses[event[1]]=text
                    if event[1] in self.rows:self.rows[event[1]].config(text=text)
                    if event[1] in self.detail_labels:self.detail_labels[event[1]].config(text=self.detail_text(event[1]))
                elif event[0] in ('error','phase'):self.status.config(text=event[1])
                elif event[0]=='checked':
                    self.checking=False;self.lock(False);self.status.config(text='Release check finished. Review the source details, then install your selection.')
                elif event[0]=='done':
                    ok=sum(success for _,success in event[1]);failed=len(event[1])-ok
                    self.status.config(text=f'{"Stopped" if event[2] else "Finished"}: {ok} completed, {failed} need attention.')
                    self.lock(False)
                    for key,text in list(self.statuses.items()):
                        if text=='Queued':
                            self.statuses[key]='Not started'
                            if key in self.rows:self.rows[key].config(text='Not started')
        except queue.Empty:pass
        self.job=self.hub.after(150,self.poll)
    def destroy(self,event):
        if event.widget is self.hub:
            self.closed=True;self.runner.stop.set();self.review_stop.set()
            for info in list(self.help_windows.values()):self.close_help(info)
            if self.filter_job:
                try:self.hub.after_cancel(self.filter_job)
                except tk.TclError:pass
            if hasattr(self,'job'):
                try:self.hub.after_cancel(self.job)
                except tk.TclError:pass

