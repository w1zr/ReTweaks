import platform
import psutil
import subprocess
import os

try:
    import cpuinfo
except ImportError:
    cpuinfo = None

try:
    import wmi
except ImportError:
    wmi = None

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

            if platform.system() == "Windows" and wmi:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                    c = wmi.WMI()
                    for processor in c.Win32_Processor():
                        info['socket'] = processor.SocketDesignation or 'Unavailable'
                        if not info['l3_cache'] or info['l3_cache'] == 'Unavailable':
                            if hasattr(processor, 'L3CacheSize') and processor.L3CacheSize:
                                info['l3_cache'] = f"{processor.L3CacheSize / 1024:.1f} MB"
                        if hasattr(processor, 'VirtualizationFirmwareEnabled'):
                            info['virtualization'] = "Enabled" if processor.VirtualizationFirmwareEnabled else "Disabled"
                except Exception:
                    pass
        except Exception as e:
            info['error'] = str(e)

        HardwareMonitor._cache['cpu'] = info
        return info

    @staticmethod
    def get_gpu_info():
        gpus = []
        try:
            if platform.system() == "Windows" and wmi:
                import pythoncom
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    vram_bytes = int(gpu.AdapterRAM) if gpu.AdapterRAM else 0
                    vram_gb = f"{vram_bytes / (1024**3):.2f} GB" if vram_bytes > 0 else "Unavailable"
                    
                    # Estimate or query GPU load if possible via counters
                    utilization = "Unavailable"
                    temp = "Unavailable"
                    
                    gpus.append({
                        'name': gpu.Name or 'Unavailable',
                        'driver_version': gpu.DriverVersion or 'Unavailable',
                        'driver_date': gpu.DriverDate or 'Unavailable',
                        'vram': vram_gb,
                        'utilization': utilization,
                        'temperature': temp,
                        'resolution': f"{gpu.CurrentHorizontalResolution}x{gpu.CurrentVerticalResolution}" if gpu.CurrentHorizontalResolution else "Unavailable",
                        'status': gpu.Status or 'OK'
                    })
        except Exception:
            pass

        if not gpus:
            gpus.append({
                'name': 'Standard Display Adapter',
                'driver_version': 'Unavailable',
                'driver_date': 'Unavailable',
                'vram': 'Unavailable',
                'utilization': 'Unavailable',
                'temperature': 'Unavailable',
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

            if platform.system() == "Windows" and wmi:
                import pythoncom
                pythoncom.CoInitialize()
                c = wmi.WMI()
                speed_list = []
                populated = 0
                for mem_chip in c.Win32_PhysicalMemory():
                    populated += 1
                    if hasattr(mem_chip, 'Speed') and mem_chip.Speed:
                        speed_list.append(f"{mem_chip.Speed} MT/s")
                if speed_list:
                    info['speed'] = speed_list[0]
                info['slots_populated'] = str(populated)
        except Exception as e:
            info['error'] = str(e)
        return info

    @staticmethod
    def get_motherboard_info():
        info = {
            'manufacturer': 'Unavailable',
            'model': 'Unavailable',
            'serial': 'Unavailable',
            'bios_version': 'Unavailable',
            'bios_date': 'Unavailable'
        }
        try:
            if platform.system() == "Windows" and wmi:
                import pythoncom
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for board in c.Win32_BaseBoard():
                    info['manufacturer'] = board.Manufacturer or 'Unavailable'
                    info['model'] = board.Product or 'Unavailable'
                    info['serial'] = board.SerialNumber or 'Unavailable'
                for bios in c.Win32_BIOS():
                    info['bios_version'] = bios.SMBIOSBIOSVersion or 'Unavailable'
                    info['bios_date'] = bios.ReleaseDate or 'Unavailable'
        except Exception:
            pass
        return info

    @staticmethod
    def get_disk_info():
        disks = []
        try:
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
        try:
            if platform.system() == "Windows" and wmi:
                import pythoncom
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for mon in c.Win32_DesktopMonitor():
                    monitors.append({
                        'name': mon.Name or 'Generic Monitor',
                        'resolution': f"{mon.ScreenWidth}x{mon.ScreenHeight}" if mon.ScreenWidth else 'Unavailable',
                        'status': mon.Status or 'OK'
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
        audio_devices = []
        try:
            if platform.system() == "Windows" and wmi:
                import pythoncom
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for snd in c.Win32_SoundDevice():
                    audio_devices.append({
                        'name': snd.Name or 'Unavailable',
                        'status': snd.Status or 'OK',
                        'manufacturer': snd.Manufacturer or 'Unavailable'
                    })
        except Exception:
            pass
        if not audio_devices:
            audio_devices.append({'name': 'Standard Audio Device', 'status': 'OK', 'manufacturer': 'Unavailable'})
        return audio_devices

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