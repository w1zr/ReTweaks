"""Real local UI-host checks. Does not refresh models or send chat requests."""
import queue
import time
import tkinter as tk
from appearance import palette
from embedded_ai import EmbeddedAI

root=tk.Tk();root.title('RETWEAKS embedded AI verification');root.geometry('1000x760')
frame=tk.Frame(root);frame.pack(fill='both',expand=True)
root.update()
events=queue.Queue()
theme={**palette('Graphite'),'FG':'#edf1f4','MUTED':'#a0aab4'}
bridge=EmbeddedAI(frame,lambda:theme,events,offline_test=True)
bridge.start()
context_snapshot='{"cpu":"Test CPU"}'
def wait_for(kind,timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        root.update()
        try:data_kind,data=events.get_nowait()
        except queue.Empty:time.sleep(.025);continue
        assert data_kind=='ai_event'
        if data['type']=='error':raise AssertionError(data['message'])
        if data['type']=='context_request':bridge.send({'op':'context','instructions':'RETWEAKS offline test instructions','snapshot':context_snapshot})
        if data['type']==kind:return data
    raise AssertionError('Timed out waiting for '+kind)
try:
    ready=wait_for('ready')
    assert ready['embedded'] and not ready['topLevel']
    bridge.send({'op':'test-window-shortcuts'})
    wait_for('window_fullscreen');wait_for('window_escape')
    for name in ('Ember','Forest','Graphite'):
        theme.update(palette(name));bridge.update_theme()
        result=wait_for('theme')
        # Discard a prior initial-theme acknowledgement if necessary.
        while result['background'].lower()!=theme['BG'].lower():result=wait_for('theme')
        bridge.send({'op':'inspect'});state=wait_for('state')
        assert state['embedded'] and not state['topLevel']
        assert state['background'].lower()==theme['BG'].lower()
        assert state['inputBackground'].lower()==theme['PANEL'].lower()
        assert state['chatBackground'].lower()==theme['PANEL'].lower()
    bridge.send({'op':'insert','text':'Local UI verification draft; do not send.'})
    bridge.send({'op':'inspect'});draft=wait_for('state')
    assert draft['draftLength']==len('Local UI verification draft; do not send.')
    bridge.send({'op':'test-send'})
    deadline=time.monotonic()+4
    while True:
        time.sleep(.1);bridge.send({'op':'inspect'});sent=wait_for('state')
        if sent['testReply'] or time.monotonic()>deadline:break
    assert sent['testRequests']>0 and sent['testReply'] and sent['contextAttached'] and sent['testContextValid'],sent
    assert sent['inputWidth']>300 and sent['inputHeight']>25,sent
    context_snapshot=''
    bridge.send({'op':'test-error-send'})
    deadline=time.monotonic()+4
    while True:
        time.sleep(.1);bridge.send({'op':'inspect'});failed=wait_for('state')
        if failed['sendEnabled'] or time.monotonic()>deadline:break
    assert failed['draftLength']>0 and failed['sendEnabled'],failed
    assert 'Local simulated service error' in failed['visibleStatus'],failed
    assert not failed['contextAttached'] and failed['testContextValid'],failed
    assert draft['inputWidth']==sent['inputWidth'] and draft['inputHeight']==sent['inputHeight']
    # Reproduce leaving the native assistant for a normal component entry.
    for _ in range(3):
        bridge.send({'op':'visibility','visible':False})
        frame.pack_forget()
        entry=tk.Entry(root);entry.pack()
        root.update();root.focus_force();entry.focus_force();root.update()
        time.sleep(.15)
        bridge.send({'op':'inspect'});hidden=wait_for('state')
        assert not hidden['visible'] and not hidden['enabled'] and not hidden['inputFocused'],hidden
        assert root.focus_get() is entry
        for key in 'Ryzen5600':entry.event_generate('<KeyPress>',keysym=key)
        root.update()
        assert entry.get()=='Ryzen5600',entry.get()
        # A delayed AI draft must not steal focus from the component field.
        bridge.send({'op':'insert','text':'Deferred draft'})
        bridge.send({'op':'inspect'});hidden=wait_for('state')
        assert not hidden['inputFocused'] and root.focus_get() is entry,hidden
        before=hidden['draftLength']
        entry.event_generate('<KeyPress>',keysym='x');root.update()
        bridge.send({'op':'inspect'});assert wait_for('state')['draftLength']==before
        assert entry.get()=='Ryzen5600x'
        entry.destroy();frame.pack(fill='both',expand=True);root.update()
        bridge.send({'op':'visibility','visible':True})
        bridge.send({'op':'inspect'});shown=wait_for('state')
        assert shown['visible'] and shown['enabled'],shown
    root.geometry('1100x800');root.update();time.sleep(.2)
    bridge.send({'op':'inspect'});size=wait_for('state')
    assert size['width']==frame.winfo_width() and size['height']==frame.winfo_height(),size
    frame.pack_forget();root.update()
    frame.pack(fill='both',expand=True);root.update()
    bridge.send({'op':'inspect'});assert wait_for('state')['embedded']
    bridge.send({'op':'test-capture','path':r'C:/Users/gabri/Downloads/RETWEAKS/RETWEAKS/ai-preview.png'})
    wait_for('captured')
    process=bridge.process
    bridge.close();process.wait(timeout=5)
    assert process.poll() is not None
    print('PASS: embedded chat, send-button click through fake transport to displayed reply, themes, resize, hide/show, clean shutdown. No network requests sent.')
finally:
    bridge.close();root.destroy()

