"""Temperature sources and an explicit-command bridge to supported fan controls."""
import csv,io,math,shutil,subprocess,threading,json,time,re
from pathlib import Path

def format_temperature(value,unit='Both'):
    if value is None:return 'Sensor unavailable'
    if unit=='C':return f'{value:.0f} °C'
    if unit=='F':return f'{value*9/5+32:.0f} °F'
    return f'{value:.0f} °C / {value*9/5+32:.0f} °F'

def category(identifier):
    name=identifier.lower()
    if 'gpu' in name:return 'GPU'
    if 'cpu' in name:return 'CPU'
    if any(x in name for x in ('hdd','ssd','nvme','storage')):return 'Storage'
    if any(x in name for x in ('ram','memory','dimm')):return 'Memory'
    return 'Motherboard'

def valid(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<160

def live_sensor(row):
    name=str(row.get('name','')).lower()
    return valid(row.get('c')) and not any(text in name for text in ('warning temperature','critical temperature','threshold','distance to','tjmax','temperature limit'))

def hardware_name(row):return str(row.get('hardware') or row.get('name','').split(' / ')[0]).strip()

def merge_readings(standard,extended):
    extended=[row for row in extended if live_sensor(row)]
    represented={(row['part'],hardware_name(row).casefold()) for row in extended}
    result=list(extended);seen={(row['part'],row.get('id') or row['name']) for row in extended}
    for row in standard:
        if not live_sensor(row):continue
        if (row['part'],hardware_name(row).casefold()) in represented:continue
        if row.get('source') in ('LibreHardwareMonitor','OpenHardwareMonitor') and any(r['part']==row['part'] for r in extended):continue
        key=(row['part'],row.get('id') or row['name'])
        if key not in seen:result.append(row);seen.add(key)
    return result

def primary_reading(rows,part=None):
    rows=[row for row in rows if live_sensor(row) and (part is None or row['part']==part)]
    if not rows:return None
    def rank(row):
        name=row['name'].lower()
        return 0 if any(tag in name for tag in ('cpu package','tctl/tdie','tdie','gpu core','composite')) else 2 if any(tag in name for tag in ('hot spot','hotspot')) else 1
    return min(rows,key=rank)

def collect():
    rows=[];nvidia=shutil.which('nvidia-smi')
    if nvidia:
        try:
            result=subprocess.run([nvidia,'--query-gpu=name,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4,creationflags=0x08000000)
            if result.returncode==0:
                for name,value in csv.reader(io.StringIO(result.stdout)):
                    try:value=float(value.strip())
                    except ValueError:continue
                    if valid(value):rows.append(dict(part='GPU',name=name.strip(),c=value,source='NVIDIA driver'))
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
    try:
        import comtypes,comtypes.client
        comtypes.CoInitialize()
        try:
            locator=comtypes.client.CreateObject('WbemScripting.SWbemLocator',dynamic=True)
            for namespace in (r'root\LibreHardwareMonitor',r'root\OpenHardwareMonitor'):
                try:
                    service=locator.ConnectServer('.',namespace)
                    for sensor in service.ExecQuery("SELECT Name,Value,Identifier FROM Sensor WHERE SensorType='Temperature'"):
                        value=float(sensor.Value)
                        if valid(value):rows.append(dict(part=category(str(sensor.Identifier)),name=str(sensor.Name),c=value,source=namespace.split('\\')[-1]))
                except Exception:continue
            try:
                service=locator.ConnectServer('.',r'root\Microsoft\Windows\Storage')
                for sensor in service.ExecQuery('SELECT DeviceId,Temperature FROM MSFT_StorageReliabilityCounter'):
                    if sensor.Temperature is not None:
                        value=float(sensor.Temperature)
                        if valid(value) and value>0:rows.append(dict(part='Storage',name='Drive '+str(sensor.DeviceId),c=value,source='Windows storage sensor'))
            except Exception:pass
        finally:comtypes.CoUninitialize()
    except (ImportError,OSError):pass
    return rows

class Temperatures:
    def __init__(self,auto_full=False):
        self.rows=[];self.extended=[];self.extended_process=None;self.extended_starting=False;self.extended_status='Detecting sensors...';self.extended_time=0;self.updated=0;self.stop=threading.Event();self.scanned=False
        self.fans=[];self.fan_controls=[];self.fan_status='Hardware automatic control';self.command_lock=threading.Lock()
        threading.Thread(target=self.run,daemon=True).start()
        if auto_full:self.full_scan()
    def run(self):
        while not self.stop.is_set():
            try:
                standard=collect()
                extended=self.extended if time.monotonic()-self.extended_time<15 else []
                self.rows=merge_readings(standard,extended);self.updated=time.time()
                if self.extended_process and self.extended_process.poll() is None:self.fan_command('heartbeat')
            except Exception:self.rows=[]
            self.scanned=True
            self.stop.wait(5)
    def full_scan(self):
        if self.stop.is_set() or self.extended_starting or (self.extended_process and self.extended_process.poll() is None):return
        self.extended_starting=True
        def read():
            try:
                if self.stop.is_set():return
                executable=Path(__file__).with_name('ai')/'sensors/SensorHost.exe'
                self.extended_process=subprocess.Popen([str(executable)],cwd=str(executable.parent),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=0x08000000)
                self.extended_status='Scanning supported hardware sensors...'
                for line in self.extended_process.stdout:
                    data=json.loads(line)
                    if isinstance(data,dict) and data.get('kind')=='hardware':
                        self.fans=data.get('fans',[]);self.fan_controls=data.get('controls',[]);data=data.get('temperatures',[])
                    elif isinstance(data,dict) and data.get('kind')=='fan_result':
                        self.fan_status=data.get('message','Fan command finished');continue
                    if isinstance(data,list):
                        self.extended=[row for row in data if live_sensor(row)];self.extended_time=time.monotonic();self.extended_status='Automatic hardware monitoring active'
                    else:self.extended_status='Full scan unavailable: '+str(data.get('error','Unknown sensor error'))
                    if self.stop.is_set():break
            except (OSError,ValueError) as exc:self.extended_status='Full scan unavailable: '+str(exc)
            finally:
                self.extended_starting=False
                if self.stop.is_set():self.close()
                if self.extended_process and self.extended_process.poll() is not None:self.extended=[]
        threading.Thread(target=read,daemon=True).start()
    def fan_command(self,op,id=None,value=None):
        if op not in ('heartbeat','manual','default','restore_all'):raise ValueError('Unknown fan operation')
        process=self.extended_process
        if not process or process.poll() is not None:
            self.fan_status='Hardware monitor is not connected. Retry sensor detection.';return False
        if op=='manual':
            control=next((row for row in self.fan_controls if row['id']==id),None)
            if not control or not isinstance(value,(float,int)) or not math.isfinite(value) or not max(30,control['min'])<=value<=min(100,control['max']):
                raise ValueError('Fan duty is outside the supported range')
        try:
            with self.command_lock:
                process.stdin.write(json.dumps(dict(op=op,id=id,value=value))+'\n');process.stdin.flush()
            if op!='heartbeat':self.fan_status='Waiting for hardware controller…'
            return True
        except (OSError,ValueError):self.fan_status='Fan controller disconnected; returning to hardware automatic control.';return False
    def fan_batch(self,op,ids,value=None):
        if op not in ('manual_many','default_many'):raise ValueError('Unknown fan group operation')
        ids=list(dict.fromkeys(ids))
        controls={r['id']:r for r in self.fan_controls}
        if not ids or any(id not in controls for id in ids):raise ValueError('A selected fan controller is no longer available')
        if op=='manual_many':
            if not isinstance(value,(int,float)) or not math.isfinite(value) or any(not max(30,controls[id]['min'])<=value<=min(100,controls[id]['max']) for id in ids):raise ValueError('Duty is outside the common supported fan range')
        process=self.extended_process
        if not process or process.poll() is not None:self.fan_status='Waiting for fan controllers…';return False
        try:
            with self.command_lock:
                process.stdin.write(json.dumps(dict(op=op,ids=ids,value=value))+'\n');process.stdin.flush()
            self.fan_status=f'Applying to {len(ids)} fan controllers…';return True
        except (OSError,ValueError):self.fan_status='Fan controllers disconnected; returning to hardware automatic control.';return False
    def close(self):
        self.stop.set()
        process=self.extended_process
        if process and process.poll() is None:
            try:process.stdin.write('close\n');process.stdin.flush();process.stdin.close()
            except (OSError,ValueError):pass
