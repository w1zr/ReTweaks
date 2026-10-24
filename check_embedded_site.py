"""Real WebView2 iframe/lifecycle test using local content only."""
import sys
import json
import queue
import time
import tkinter as tk
from embedded_site import EmbeddedSite

root=tk.Tk();root.title('RETWEAKS local embedded browser check');root.geometry('900x620')
frame=tk.Frame(root);frame.pack(fill='both',expand=True);root.update()
events=queue.Queue()
bridge=EmbeddedSite(frame,lambda:{'BG':'#101214'},events,offline_test=True, builder='--builder' in sys.argv, activation='--activation' in sys.argv, windhawk='--windhawk' in sys.argv)
def wait(kind,timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        root.update()
        try:_,event=events.get_nowait()
        except queue.Empty:time.sleep(.025);continue
        if event['type']=='error':raise AssertionError(event['message'])
        if event['type']==kind:return event
    raise AssertionError('Timed out waiting for '+kind)
try:
    bridge.start();wait('ready')
    deadline=time.monotonic()+10
    while True:
        bridge.send({'op':'inspect'});state=wait('state')
        document=json.loads(json.loads(state['document']))
        if document['iframe'] or time.monotonic()>deadline:break
        time.sleep(.1)
    assert state['url']==('https://windhawk.net/mods' if '--windhawk' in sys.argv else 'https://massgrave.dev/' if '--activation' in sys.argv else 'https://www.buildcores.com/new-build' if '--builder' in sys.argv else 'https://pc-builds.com/bottleneck-calculator/')
    assert state['embedded'] and document['iframe'] and document['src'] is None,state
    assert state['width']==frame.winfo_width() and state['height']==frame.winfo_height()
    bridge.send({'op':'visibility','visible':False});frame.pack_forget();root.update()
    bridge.send({'op':'inspect'});hidden=wait('state')
    assert not hidden['visible'] and not hidden['enabled'],hidden
    entry=tk.Entry(root);entry.pack();root.update();root.focus_force();entry.focus_force();root.update()
    for key in 'abc123':entry.event_generate('<KeyPress>',keysym=key)
    assert entry.get()=='abc123'
    entry.destroy();frame.pack(fill='both',expand=True);root.geometry('950x650');root.update()
    bridge.send({'op':'visibility','visible':True});time.sleep(.2)
    bridge.send({'op':'inspect'});shown=wait('state')
    assert shown['visible'] and shown['enabled'] and shown['width']==frame.winfo_width(),shown
    process=bridge.process;bridge.close(wait=True)
    assert process.poll() is not None
    print('PASS: real embedded WebView2, local HTML iframe, resize, hide/show, keyboard handoff and shutdown. No remote website loaded.')
finally:
    bridge.close(wait=True);root.destroy()
