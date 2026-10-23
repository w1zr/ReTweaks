"""Brief start/stop-hotkey registration check; generates no input."""
import queue
import automation as a
q=queue.Queue();hotkeys=a.Hotkeys(q)
try:
    for key in ('F9','F10','F12','F5'):
        hotkeys.update({'click_key':key})
        kind,data=q.get(timeout=4)
        if kind=='hotkeys':break
    assert kind=='hotkeys',(kind,data)
finally:hotkeys.close();hotkeys.thread.join(2)
assert not hotkeys.thread.is_alive()
assert not hasattr(a,'HOOK') and not hasattr(a,'KHOOK')
print('PASS: single clicker hotkey registers and unregisters; no recorder hooks. No input generated.')
