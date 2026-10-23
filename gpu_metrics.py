"""Read-only Windows GPU engine counters; busiest physical engine, summed across processes."""
import ctypes as c
from ctypes import wintypes as w
import math
import re
import threading

class ValueUnion(c.Union):
    _fields_=[('number',c.c_double),('large',c.c_longlong)]
class Value(c.Structure):
    _anonymous_=('value',)
    _fields_=[('status',w.DWORD),('value',ValueUnion)]
class Item(c.Structure):
    _fields_=[('name',w.LPWSTR),('value',Value)]

def aggregate(rows):
    engines={}
    for name,value in rows:
        if not math.isfinite(value) or value<0:continue
        match=re.search(r'(luid_.*?_phys_\d+_eng_\d+)_engtype_',name)
        if match:engines[match[1]]=engines.get(match[1],0)+value
    return min(100,max(engines.values())) if engines else None

class GpuSampler:
    def __init__(self):
        self.value=None;self.message='Collecting GPU samples';self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        query=c.c_void_p();counter=c.c_void_p()
        try:
            pdh=c.WinDLL('pdh.dll')
            pdh.PdhOpenQueryW.argtypes=[w.LPCWSTR,c.c_size_t,c.POINTER(c.c_void_p)]
            pdh.PdhAddEnglishCounterW.argtypes=[c.c_void_p,w.LPCWSTR,c.c_size_t,c.POINTER(c.c_void_p)]
            pdh.PdhCollectQueryData.argtypes=[c.c_void_p]
            pdh.PdhGetFormattedCounterArrayW.argtypes=[c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.POINTER(w.DWORD),c.c_void_p]
            pdh.PdhCloseQuery.argtypes=[c.c_void_p]
            if pdh.PdhOpenQueryW(None,0,c.byref(query)) or pdh.PdhAddEnglishCounterW(query,r'\GPU Engine(*)\Utilization Percentage',0,c.byref(counter)):
                raise OSError('Windows GPU counters are unavailable')
            pdh.PdhCollectQueryData(query)
            while not self.stop.wait(1):
                if pdh.PdhCollectQueryData(query):raise OSError('GPU counter collection failed')
                rows=[]
                for _ in range(3):
                    size=w.DWORD();count=w.DWORD()
                    pdh.PdhGetFormattedCounterArrayW(counter,0x200,c.byref(size),c.byref(count),None)
                    if not size.value or size.value>32*1024*1024:break
                    buffer=c.create_string_buffer(size.value)
                    result=pdh.PdhGetFormattedCounterArrayW(counter,0x200,c.byref(size),c.byref(count),buffer)
                    if result:continue
                    items=c.cast(buffer,c.POINTER(Item))
                    rows=[(items[i].name,items[i].value.number) for i in range(count.value) if items[i].value.status in (0,1)]
                    break
                self.value=aggregate(rows)
                self.message='Busiest GPU engine across adapters' if self.value is not None else 'No GPU engine samples available from the driver'
        except (OSError,AttributeError):self.value=None;self.message='GPU counters unavailable; open Task Manager to check driver support'
        finally:
            if query.value:pdh.PdhCloseQuery(query)
    def close(self):self.stop.set()
