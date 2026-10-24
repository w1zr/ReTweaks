"""Tk-thread progress and one worker per missing feature dependency."""
import queue
import threading
from core import dependencies as deps


def ensure(hub,key,done=None):
    if not deps.enabled(hub):return False
    if deps.available(key):
        if done:done()
        return False
    jobs=getattr(hub,'_dependency_jobs',None)
    if jobs is None:jobs=hub._dependency_jobs={}
    if key in jobs:
        if done:jobs[key].append(done)
        return True
    failures=getattr(hub,'_dependency_failures',set())
    if key in failures:return False
    jobs[key]=[done] if done else []
    hub.set_status('Installing missing '+deps.TITLES[key]+'...',hub.sidebar_nav.c('MUTED'))
    result=queue.Queue()
    def work():
        try:result.put((True,deps.install(key)))
        except Exception as exc:result.put((False,str(exc)))
    def poll():
        try:ok,message=result.get_nowait()
        except queue.Empty:
            hub.after(150,poll);return
        callbacks=jobs.pop(key,[])
        hub.set_status(deps.TITLES[key]+': '+message,hub.sidebar_nav.c('MUTED'))
        if not ok:
            failures.add(key);hub._dependency_failures=failures
        if ok and deps.available(key):
            for callback in callbacks:callback()
    threading.Thread(target=work,daemon=True).start()
    hub.after(150,poll)
    return True


def on_page(hub,index):
    if not deps.enabled(hub):return
    tabs=getattr(hub,'rt_tabs',{})
    if index in (19,25,28,29,tabs.get('Browser')):
        def restart():
            page=getattr(hub,'rt_pages',{}).get('Browser')
            if index==tabs.get('Browser'):
                if page and page.bridge is not None:page.restart()
                return
            prefix={19:'site',25:'builder',28:'activation',29:'windhawk'}.get(index)
            bridge=getattr(hub,prefix+'_bridge',None)
            if bridge:bridge.start()
        if not deps.available('webview2'):ensure(hub,'webview2',restart)
    if index in (tabs.get('Temperatures'),tabs.get('Fan control')):
        def rescan():
            sampler=getattr(hub,'temperatures',None)
            if sampler:sampler.full_scan()
        if not deps.available('pawnio'):ensure(hub,'pawnio',rescan)
    if index==tabs.get('FPS overlay'):
        page=hub.rt_pages.get('FPS overlay')
        if page and not page.path_var.get().strip():
            def connect():
                page.path_var.set(deps.presentmon_path());page._path_typed()
            ensure(hub,'presentmon',connect)
