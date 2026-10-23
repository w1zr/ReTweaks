"""Clicker tests with a simulated mouse sink; never generates OS input."""
import ctypes,sys,time
from automation import DEFAULT,Engine,INPUT,KEYS,Native,config_valid,next_interval_s
class Sink:
    def __init__(self):self.events=[];self.escape=False
    def emit(self,kind,values):self.events.append((kind,values[:],time.perf_counter()))
    def down(self,vk):return self.escape and vk==27
    def cursor(self):return [10,20]
def wait(engine):
    engine.thread.join(2);assert engine.mode=='idle',engine.status
if sys.platform=='win32':assert ctypes.sizeof(INPUT)==(40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)  # Windows type sizes
for invalid in ({'interval_ms':0},{'click_key':'Escape'},{'double':1}):
    try:config_valid(invalid)
    except ValueError:pass
    else:raise AssertionError(invalid)
assert set(config_valid({**DEFAULT,'record_key':'F7','repeats':10,'speed':2}))==set(DEFAULT)
sink=Sink();engine=Engine(sink)
assert not hasattr(engine,'events') and not hasattr(engine,'_record')
for mode in ('recording','playing'):
    try:engine.start(mode,DEFAULT)
    except ValueError:pass
    else:raise AssertionError('Removed mode was allowed')
try:Native().emit('key',[65,30,0])
except ValueError:pass
else:raise AssertionError('Keyboard input was allowed')
engine.start('clicking',{**DEFAULT,'click_count':3,'interval_ms':20,'fixed':True,'x':-10,'y':20})
wait(engine)
assert [(k,v) for k,v,t in sink.events]==[('move',[-10,20]),('button',[0,1]),('button',[0,0])]*3
assert sink.events[-1][2]-sink.events[0][2]>=.03
sink.events=[]
engine.start('clicking',{**DEFAULT,'click_count':1,'double':True,'button':'right'})
wait(engine)
assert [(k,v) for k,v,t in sink.events]==[('button',[1,1]),('button',[1,0])]*2
sink.events=[]
engine.start('clicking',{**DEFAULT,'interval_ms':10000})
time.sleep(.04);engine.stop();wait(engine)
assert len(sink.events)==2
sink.events=[];engine.start('clicking',{**DEFAULT,'interval_ms':10000})
sink.escape=True;wait(engine)
assert all(k in ('move','button') for k,v,t in sink.events)
# Failed mouse-up must still be retried during cleanup.
class FailingSink(Sink):
    def __init__(self):super().__init__();self.failed=False
    def emit(self,kind,values):
        if values==[0,0] and not self.failed:self.failed=True;raise OSError('Test mouse-up failure')
        super().emit(kind,values)
failing=FailingSink();engine=Engine(failing);engine.start('clicking',{**DEFAULT,'click_count':1});wait(engine)
assert failing.events[-1][:2]==('button',[0,0])
# ---- RETWEAKS additions
old=config_valid({'interval_ms':50,'button':'left','double':False,'click_count':2,'fixed':False,'x':0,'y':0,'click_key':'F6'})
assert old['stop_key']=='F8' and old['speed_mode']=='Interval (ms)'      # version-2 files still load
for invalid in ({'cps':0},{'cps':101.0},{'start_delay_s':11},{'random_min_ms':200,'random_max_ms':100},
                {'stop_key':'F6'},{'run_seconds':-1},{'cps':float('nan')},{'speed_mode':'fast'},{'random':1}):
    try:config_valid({**DEFAULT,**invalid})
    except ValueError:pass
    else:raise AssertionError(invalid)
assert abs(next_interval_s({**DEFAULT,'speed_mode':'Clicks per second','cps':20.0})-0.05)<1e-9
assert next_interval_s({**DEFAULT,'interval_ms':250})==0.25
class R:
    def uniform(self,a,b):return b
assert next_interval_s({**DEFAULT,'random':True,'random_min_ms':100,'random_max_ms':300},R())==0.3
# CPS mode timing and stats
sink=Sink();engine=Engine(sink)
engine.start('clicking',{**DEFAULT,'speed_mode':'Clicks per second','cps':50.0,'click_count':4})
wait(engine)
assert engine.stats['clicks']==4 and engine.stats['cycles']==4 and engine.stats['reason']=='count'
assert sink.events[-1][2]-sink.events[0][2]>=.05
# Start delay: nothing is clicked before the delay
sink=Sink();engine=Engine(sink);t0=time.perf_counter()
engine.start('clicking',{**DEFAULT,'click_count':1,'start_delay_s':0.2});wait(engine)
assert sink.events[0][2]-t0>=0.18
# Stop during the start delay: no clicks at all
sink=Sink();engine=Engine(sink)
engine.start('clicking',{**DEFAULT,'start_delay_s':5.0});time.sleep(.05);engine.stop();wait(engine)
assert sink.events==[] and engine.status=='Stopped'
# Run-time limit
sink=Sink();engine=Engine(sink)
engine.start('clicking',{**DEFAULT,'interval_ms':20,'run_seconds':1});wait_t=time.perf_counter()
engine.thread.join(3);assert engine.mode=='idle' and engine.stats['reason']=='time'
assert 0.9<=engine.stats['elapsed']<=1.6,engine.stats
# Emergency-stop key (not Esc) stops clicking
class KeySink(Sink):
    def __init__(self):super().__init__();self.key=False
    def down(self,vk):return self.key and vk==KEYS['F9']
ks=KeySink();engine=Engine(ks)
engine.start('clicking',{**DEFAULT,'interval_ms':30,'stop_key':'F9'});time.sleep(.1);ks.key=True;wait(engine)
assert engine.stats['reason']=='emergency' and engine.status=='Emergency stop'
print('PASS: click timing, fixed/double clicks, stop/Esc, mouse-button cleanup, configuration validation and removed modes rejected; CPS mode, random range, start delay, run-time limit, emergency-stop key, stats and old configs. No OS input generated.')
