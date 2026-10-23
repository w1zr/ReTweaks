"""Live app release evidence plus constrained AI review; no installer downloads."""
import concurrent.futures
import json
import re
import subprocess
from app_starter import APPS,nvidia_link


def latest_plan(keys,executable,stop,emit,enable_ai=True):
    def one(key):
        if stop.is_set():return key,{}
        row=APPS[key]
        emit(('status',key,'Checking newest compatible release…'))
        try:
            if key=='nvidia':
                url=nvidia_link();match=re.search(r'(?i)NVIDIA_app_v([0-9.]+)\.exe',url)
                return key,{'id':key,'package':None,'name':row[1],'version':match[1] if match else '', 'url':url,'source':'NVIDIA official download page','evidence':url}
            if not executable:return key,{}
            result=subprocess.run([executable,'show','--id',row[3],'--exact','--source','winget','--accept-source-agreements','--disable-interactivity'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=50,creationflags=0x08000000)
            if result.returncode:return key,{}
            text=re.sub(r'\x1b\[[0-9;?]*[ -/]*[@-~]','',result.stdout)[-18000:]
            version=re.search(r'(?m)^\s*Version:\s*(\S+)\s*$',text)
            url=re.search(r'(?mi)^\s*Installer Url:\s*(https://\S+)\s*$',text)
            return key,{'id':key,'package':row[3],'name':row[1],'version':version[1] if version else '', 'url':url[1] if url else '', 'source':'WinGet live compatible package','evidence':text}
        except Exception:return key,{}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:records=dict(pool.map(one,keys))
    records={key:record for key,record in records.items() if record}
    for key,record in records.items():emit(('release',key,record))
    if not records or stop.is_set() or not enable_ai:return records
    emit(('phase','AI is reviewing the current release sources…'))
    try:
        from drivers import ask_ai
        reviews=[{**record,'evidence':record['evidence'][:2000]} for record in list(records.values())[:20]]
        review_ids={record['id'] for record in reviews}
        answer=ask_ai({'task':'apps','apps':reviews})
        text=answer.get('text','');a=text.index('{');b=text.rindex('}')+1
        response=json.loads(text[a:b])
        for item in response.get('items',[]):
            key=item.get('id');record=records.get(key)
            if key not in review_ids:continue
            if not record or not record['version'] or item.get('version')!=record['version'] or item.get('package')!=record['package']:continue
            if item.get('approved') is not True:continue
            record['ai']=True
            record['note']='AI matched this release to the live source.'
            emit(('release',key,record))
        emit(('phase','Current releases checked. Preparing your selection…'))
    except Exception:emit(('phase','AI review unavailable. Using current verified package sources.'))
    return records
