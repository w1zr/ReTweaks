"""App-only failure reports and advisory AI help. Never executes suggested fixes."""
import json
import os
import re
from urllib.parse import urlsplit,urlunsplit

def redact(text,limit=10000):
    text=str(text or '')[-30000:]
    text=re.sub(r'\x1b\[[0-9;?]*[ -/]*[@-~]','',text)
    for key in ('USERPROFILE','LOCALAPPDATA','APPDATA','TEMP'):
        value=os.environ.get(key)
        if value:text=re.sub(re.escape(value),lambda _:f'%{key}%',text,flags=re.I)
    text=re.sub(r'(?i)[a-z]:[\\/]users[\\/][^\\/\s"\']+',r'%USERPROFILE%',text)
    text=re.sub(r'(?i)(authorization\s*[:=]\s*)([^\r\n]+)',r'\1[redacted]',text)
    text=re.sub(r'''(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[:=]\s*)(["'])(.*?)\2''',r'\1[redacted]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*["\']?\s*[:=]\s*["\']?)([^\s"\',;]+)',r'\1[redacted]',text)
    text=re.sub(r'AIza[A-Za-z0-9_-]{20,}|AQ\.[A-Za-z0-9_-]{20,}','[redacted]',text)
    text=re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b','[email redacted]',text)
    def url(match):
        try:
            p=urlsplit(match[0]);host=p.hostname or ''
            if p.port:host+=':'+str(p.port)
            return urlunsplit((p.scheme,host,p.path,'',''))
        except ValueError:return '[URL redacted]'
    text=re.sub(r'https?://[^\s<>"\']+',url,text)
    return text[-limit:]

def fallback(report):
    code=report.get('code');error=report.get('error','').lower()
    if code in (0x8A150011,0x8A15002D,0x8A15005E,0x8A150060) or any(s in error for s in ('signature','hash mismatch','security check','certificate')):
        cause='The installer did not pass an integrity, certificate, or publisher check.'
        steps=['Do not run the failed or partial installer.', 'Check the app’s official website and try again later; a publisher or package update may be needed.', 'Keep WinGet’s hash and security checks enabled.']
    elif code==0x8A150010:
        cause='WinGet could not find an installer compatible with this PC.'
        steps=['Check the app’s supported Windows version and CPU architecture.', 'Use Official site to find a compatible edition.']
    elif code in (0x8A150014,0x8A150017):
        cause='The requested app or release is not available from the selected package source.'
        steps=['Try again later or use the official website.', 'Update Microsoft App Installer if your package catalog is outdated.']
    elif code==0x8A15006C:
        cause='This package does not allow a standalone installer download through WinGet.'
        steps=['If you want to install it now, deliberately choose Install apps and select this app again.', 'Otherwise, use Official site for the vendor’s supported download options.']
    elif code in (0x80070070,112):
        cause='Windows reported insufficient disk space.'
        steps=['Check the free space on your system and Downloads drives.', 'Review and remove files you no longer need, then retry.']
    elif code in (0x8A15001B,0x8A15001C,0x8A15003A):
        cause='A Windows or organization policy blocked the operation.'
        steps=['On a managed computer, ask your administrator whether this app is permitted.', 'Do not bypass the organization’s installation policy.']
    elif 'winget missing' in error or code==0x8A150007:
        cause='Windows Package Manager is missing or needs an update.'
        steps=['Open Get Microsoft App Installer in App Starter and install or update it.', 'Reopen RETWEAKS, then retry the failed app.']
    elif code==0x8A150056:
        cause='This installer does not allow installation from an administrator process.'
        steps=['Use Official site to download the vendor’s installer.', 'Run that installer normally from your Windows account; RETWEAKS itself starts with administrator privileges.']
    elif code in (0x8A150019,5,0x80070005) or 'access denied' in error or 'permission' in error:
        cause='Windows could not access a required file, folder, or installation location.'
        steps=['Check that your Downloads folder is writable and has free space.', 'Close any running copy of the app, then retry.', 'For a managed computer, ask your administrator about installation policy.']
    elif 'timed out' in error or code in (0x8A150008,0x8A15002E) or any(s in error for s in ('network','connection','download','truncated')):
        cause='The download failed or did not produce a complete installer.'
        steps=['Check your internet connection and available disk space.', 'Retry this app. If the vendor is temporarily unavailable, try again later.', 'Use Official site if WinGet continues to fail.']
    else:
        cause='The app setup did not complete. The error and log excerpt may show a more specific cause.'
        steps=['Review the error details below.', 'Close an existing installer or running copy of the app, then retry.', 'Use Official site for vendor-specific setup instructions.']
    return {'summary':cause,'steps':steps,'source':'Local guidance'}

def failure_record(key,row,mode,error,code=None,log=''):
    return {'id':key,'name':row[1],'package':row[3],'mode':mode,
            'code':None if code is None else code&0xffffffff,'error':redact(error,1000),
            'log_excerpt':redact(log,6000),'official_site':row[4]}

def explain(report,enable_ai=True,ask=None):
    result=fallback(report)
    if not enable_ai:return {**result,'note':'AI is disabled. These suggestions are based on the error details.'}
    try:
        if ask is None:
            from drivers import ask_ai
            ask=ask_ai
        # Re-redact the complete bounded payload at the service boundary.
        fields=('id','name','package','mode','code','error','log_excerpt','official_site')
        payload={'task':'app_failure','failure':{k:redact(report[k],6000 if k=='log_excerpt' else 1000) if isinstance(report[k],str) else report[k] for k in fields if k in report}}
        answer=ask(payload).get('text','')
        data=json.loads(answer[answer.index('{'):answer.rindex('}')+1])
        summary=data.get('summary');steps=data.get('steps')
        if not isinstance(summary,str) or not summary.strip() or not isinstance(steps,list) or not 1<=len(steps)<=8 or any(not isinstance(s,str) or not s.strip() for s in steps):raise ValueError('Incomplete AI response')
        # No AI-generated commands or URLs become actionable UI controls.
        return {'summary':redact(summary,1500),'steps':[redact(s,1000) for s in steps],
                'source':'AI guidance','note':'This is an explanation, not a verified fix. Nothing has been changed.'}
    except Exception:
        return {**result,'note':'AI help is unavailable right now. Local guidance is shown instead; you can still retry or use the official site.'}
