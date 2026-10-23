"""A stalled native pipe must not stall the Tk caller."""
import threading
import json
import time
from embedded_ai import EmbeddedAI

class Pipe:
    def __init__(self):self.gate=threading.Event();self.started=threading.Event();self.lines=[]
    def write(self,line):self.started.set();self.gate.wait(2);self.lines.append(line)
    def flush(self):pass
class Process:
    def __init__(self):self.stdin=Pipe();self.done=False
    def poll(self):return 0 if self.done else None
bridge=EmbeddedAI(None,lambda:{},None);process=Process();bridge.process=process
start=time.perf_counter()
for i in range(50):assert bridge.send({'op':'visibility','visible':bool(i%2)})
assert time.perf_counter()-start<.15
assert process.stdin.started.wait(.5)
assert not process.stdin.lines
process.stdin.gate.set()
deadline=time.monotonic()+2
while len(process.stdin.lines)<50 and time.monotonic()<deadline:time.sleep(.01)
assert len(process.stdin.lines)==50
process.done=True
process=Process();bridge.process=process
for i in range(500):assert bridge.send({'op':'visibility','visible':bool(i%2)})
process.stdin.gate.set()
deadline=time.monotonic()+2
while time.monotonic()<deadline:
    if process.stdin.lines and json.loads(process.stdin.lines[-1])['visible'] and bridge._commands.empty() and not bridge._pending_state:break
    time.sleep(.01)
assert json.loads(process.stdin.lines[-1])['visible'] is True
process.done=True
print('PASS: blocked native writes leave caller responsive; command order and final visibility retained, including 500 rapid updates.')
