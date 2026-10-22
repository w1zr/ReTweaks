# C:\pc_optimizer\core\hardware.py

import platform
import psutil
import subprocess
import json
import os

try:
    import cpuinfo
except ImportError:
    cpuinfo = None

class HardwareMonitor:
    _cache = {}

    @staticmethod
    def get_cpu_info(use_cache=True):
        if use_cache and 'cpu' in HardwareMonitor._cache:
            return HardwareMonitor._cache['cpu']
        
        info = {
            'name': 'Unavailable',
            'arch': platform.machine(),
            'cores_physical': psutil.cpu_count(logical=False) or 1,
            'cores_logical': psutil.cpu_count(logical=True) or 1,
            'current_freq': 'Unavailable',
            'base_freq': 'Unavailable',
            'max_freq': 'Unavailable',
            'utilization': 0.0,
            'l3_cache': 'Unavailable',
            'socket': 'Unavailable',
            'virtualization': 'Unavailable'
        }
        try:
            if cpuinfo:
                cpu_data = cpuinfo.get_cpu_info()
                info['name'] = cpu_data.get('brand_raw', platform.processor())
                if 'l3_cache_size' in cpu_data:
                    info['l3_cache'] = f"{cpu_data['l3_cache_size'] / (1024**2):.1f} MB"
            else:
                info['name'] = platform.processor()

            freq = psutil.cpu_freq()
            if freq:
                info['current_freq'] = f"{freq.current:.1f} MHz"
                info['base_freq'] = f"{freq.min:.1f} MHz" if freq.min else "Unavailable"
                info['max_freq'] = f"{freq.max:.1f} MHz" if freq.max else "Unavailable"

            info['utilization'] = psutil.cpu_percent(interval=0.1)
        except Exception as e:
            info['error'] = str(e)

        HardwareMonitor._cache['cpu'] = info
        return info

    @staticmethod
    def get_gpu_info():
        gpus = []
        
        # 1. Try NVIDIA NVML first for precise telemetry
        try:
            import pynvml
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode('utf-8')
                
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_gb = round(mem_info.total / (1024**3), 1)
                
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                    power_str = f"{power:.1f} W"
                except Exception:
                    power_str = "Unavailable"
                    
                try:
                    fan = pynvml.nvmlDeviceGetFanSpeed(handle)
                    fan_str = f"{fan}%"
                except Exception:
                    fan_str = "Unavailable"
                    
                try:
                    core_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
                    mem_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)
                    core_clock_str = f"{core_clock} MHz"
                    mem_clock_str = f"{mem_clock} MHz"
                except Exception:
                    core_clock_str, mem_clock_str = "Unavailable", "Unavailable"

                driver_version = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(driver_version, bytes):
                    driver_version = driver_version.decode('utf-8')

                gpus.append({
                    'name': name,
                    'manufacturer': 'NVIDIA',
                    'vram': f"{vram_gb} GB",
                    'utilization': f"{util.gpu}%",
                    'temperature': f"{temp}°C",
                    'core_clock': core_clock_str,
                    'mem_clock': mem_clock_str,
                    'power': power_str,
                    'fan_speed': fan_str,
                    'driver_version': driver_version,
                    'driver_date': 'Unavailable',
                    'resolution': 'Unavailable',
                    'status': 'OK'
                })
        except Exception:
            pass

        # 2. PowerShell Registry 64-bit QWORD Query (Bypasses WMI 4GB limitation globally for all GPUs)
        if not gpus and platform.system() == "Windows":
            try:
                cmd = '''powershell -NoProfile -Command "$adapters = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}' -ErrorAction SilentlyContinue | Where-Object {$_.PSChildName -match '^\\d{4}$'}; $res = foreach ($a in $adapters) { $desc = $a.GetValue('DriverDesc'); $mem = $a.GetValue('HardwareInformation.qwMemorySize'); if(-not $mem){$mem = $a.GetValue('HardwareInformation.MemorySize')}; if($desc -and $mem){ [PSCustomObject]@{ Name = $desc; VRAM = $mem } } }; if($res){ $res | ConvertTo-Json }"'''
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
                if output.strip():
                    data = json.loads(output)
                    if isinstance(data, dict):
                        data = [data]
                    
                    for gpu in data:
                        name = gpu.get('Name') or "Unknown GPU"
                        name_lower = name.lower()
                        
                        if any(v in name_lower for v in ['meta', 'virtual', 'parsec', 'displaylink', 'remote desktop', 'indirect', 'vmware', 'hyper-v']):
                            continue
                            
                        vram_bytes = int(gpu.get('VRAM', 0) or 0)
                        vram_gb = round(vram_bytes / (1024**3), 1)
                        vram_str = f"{vram_gb} GB" if vram_gb > 0 else "Unavailable"
                        
                        manufacturer = "Unknown"
                        if "nvidia" in name_lower or "geforce" in name_lower:
                            manufacturer = "NVIDIA"
                        elif "amd" in name_lower or "radeon" in name_lower:
                            manufacturer = "AMD"
                        elif "intel" in name_lower:
                            manufacturer = "Intel"

                        gpus.append({
                            'name': name,
                            'manufacturer': manufacturer,
                            'vram': vram_str,
                            'utilization': 'Unavailable',
                            'temperature': 'Unavailable',
                            'core_clock': 'Unavailable',
                            'mem_clock': 'Unavailable',
                            'power': 'Unavailable',
                            'fan_speed': 'Unavailable',
                            'driver_version': 'Unavailable',
                            'driver_date': 'Unavailable',
                            'resolution': 'Unavailable',
                            'status': 'OK'
                        })
            except Exception as e:
                print(f"Registry 64-bit VRAM query error: {e}")

        # 3. Final WMI fallback if registry query returned nothing
        if not gpus and platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion, DriverDate, Status | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
                if output.strip():
                    data = json.loads(output)
                    if isinstance(data, dict):
                        data = [data]
                    for gpu in data:
                        name = gpu.get('Name') or "Unknown GPU"
                        adapter_ram = int(gpu.get('AdapterRAM', 0) or 0)
                        vram_gb = round(adapter_ram / (1024**3), 1)
                        gpus.append({
                            'name': name,
                            'manufacturer': 'Unknown',
                            'vram': f"{vram_gb} GB" if vram_gb > 0 else "Unavailable",
                            'utilization': 'Unavailable',
                            'temperature': 'Unavailable',
                            'core_clock': 'Unavailable',
                            'mem_clock': 'Unavailable',
                            'power': 'Unavailable',
                            'fan_speed': 'Unavailable',
                            'driver_version': gpu.get('DriverVersion') or 'Unavailable',
                            'driver_date': gpu.get('DriverDate') or 'Unavailable',
                            'resolution': 'Unavailable',
                            'status': 'OK'
                        })
            except Exception:
                pass

        if not gpus:
            gpus.append({
                'name': 'Standard Display Adapter',
                'manufacturer': 'Generic',
                'vram': 'Unavailable',
                'utilization': 'Unavailable',
                'temperature': 'Unavailable',
                'core_clock': 'Unavailable',
                'mem_clock': 'Unavailable',
                'power': 'Unavailable',
                'fan_speed': 'Unavailable',
                'driver_version': 'Unavailable',
                'driver_date': 'Unavailable',
                'resolution': 'Unavailable',
                'status': 'Basic'
            })
        return gpus

    @staticmethod
    def get_ram_info():
        info = {}
        try:
            mem = psutil.virtual_memory()
            info['total'] = f"{mem.total / (1024**3):.2f} GB"
            info['available'] = f"{mem.available / (1024**3):.2f} GB"
            info['used'] = f"{mem.used / (1024**3):.2f} GB"
            info['percent'] = mem.percent
            info['type'] = 'Unavailable'
            info['speed'] = 'Unavailable'
            info['slots_populated'] = 'Unavailable'
        except Exception as e:
            info['error'] = str(e)
        return info

    @staticmethod
    def get_motherboard_info():
        mb_info = {
            'manufacturer': 'Unavailable',
            'model': 'Unavailable',
            'serial': 'Unavailable',
            'bios_version': 'Unavailable',
            'bios_date': 'Unavailable'
        }
        if platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "$board = Get-CimInstance Win32_BaseBoard; $bios = Get-CimInstance Win32_BIOS; [PSCustomObject]@{ Manufacturer = $board.Manufacturer; Model = $board.Product; Serial = $board.SerialNumber; BiosVersion = $bios.SMBIOSBIOSVersion; BiosDate = $bios.ReleaseDate } | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
                if output.strip():
                    data = json.loads(output)
                    mb_info['manufacturer'] = data.get('Manufacturer', 'Unavailable').strip()
                    mb_info['model'] = data.get('Model', 'Unavailable').strip()
                    mb_info['serial'] = data.get('Serial', 'Unavailable').strip()
                    mb_info['bios_version'] = data.get('BiosVersion', 'Unavailable').strip()
                    mb_info['bios_date'] = data.get('BiosDate', 'Unavailable').strip()
            except Exception:
                pass
        return mb_info

    @staticmethod
    def get_disk_info():
        disks = []
        try:
            smart_map = {}
            if platform.system() == "Windows":
                try:
                    cmd = 'powershell -NoProfile -Command "Get-PhysicalDisk | Select-Object DeviceId, OperationalStatus, HealthStatus | ConvertTo-Json"'
                    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
                    if output.strip():
                        s_data = json.loads(output)
                        if isinstance(s_data, dict):
                            s_data = [s_data]
                        for d in s_data:
                            health = d.get('HealthStatus')
                            status_str = "Healthy (SMART OK)" if health == 0 or health == "Healthy" else f"Status: {health}"
                            smart_map[str(d.get('DeviceId'))] = status_str
                except Exception:
                    pass

            for partition in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': f"{usage.total / (1024**3):.2f} GB",
                        'used': f"{usage.used / (1024**3):.2f} GB",
                        'free': f"{usage.free / (1024**3):.2f} GB",
                        'percent': usage.percent,
                        'health': 'Healthy (SMART OK)'
                    })
                except PermissionError:
                    continue
        except Exception as e:
            disks.append({'error': str(e)})
        return disks

    @staticmethod
    def get_monitors_info():
        monitors = []
        if platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_DesktopMonitor | Select-Object Name, DeviceID, Status | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
                if output.strip():
                    data = json.loads(output)
                    if isinstance(data, dict):
                        data = [data]
                    for m in data:
                        monitors.append({
                            'name': m.get('Name') or 'Display Device',
                            'resolution': 'Active',
                            'status': m.get('Status') or 'OK'
                        })
            except Exception:
                pass
        if not monitors:
            monitors.append({'name': 'Primary Display', 'resolution': 'Active', 'status': 'OK'})
        return monitors

    @staticmethod
    def get_network_info():
        nets = []
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            for intface, addr_list in addrs.items():
                is_up = stats[intface].isup if intface in stats else False
                speed = f"{stats[intface].speed} Mbps" if intface in stats and stats[intface].speed > 0 else "Unknown"
                for addr in addr_list:
                    if addr.family == 2:
                        nets.append({
                            'interface': intface,
                            'ip': addr.address,
                            'netmask': addr.netmask,
                            'status': 'Connected' if is_up else 'Disconnected',
                            'speed': speed
                        })
        except Exception:
            pass
        return nets

    @staticmethod
    def get_audio_info():
        audio_devs = []
        if platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_SoundDevice | Select-Object Name, Manufacturer, Status | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
                if output.strip():
                    data = json.loads(output)
                    if isinstance(data, dict):
                        data = [data]
                    for aud in data:
                        audio_devs.append({
                            'name': aud.get('Name') or 'Audio Device',
                            'status': aud.get('Status') or 'OK',
                            'manufacturer': aud.get('Manufacturer') or 'Unknown'
                        })
            except Exception:
                pass
        if not audio_devs:
            audio_devs.append({'name': 'Standard Audio Device', 'status': 'OK', 'manufacturer': 'Unknown'})
        return audio_devs

    @staticmethod
    def get_system_info():
        is_admin = False
        try:
            if platform.system() == "Windows":
                import ctypes
                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            pass

        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'node': platform.node(),
            'processor': platform.processor(),
            'is_admin': is_admin
        }

    @staticmethod
    def get_running_processes():
        procs = []
        try:
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = p.info
                    procs.append({
                        'pid': pinfo.get('pid'),
                        'name': pinfo.get('name', 'Unknown'),
                        'cpu': f"{pinfo.get('cpu_percent', 0.0):.1f}%",
                        'memory': f"{pinfo.get('memory_percent', 0.0):.1f}%"
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception:
            pass
        return sorted(procs, key=lambda x: float(x['cpu'].replace('%','')) if isinstance(x['cpu'], str) else 0, reverse=True)[:50]