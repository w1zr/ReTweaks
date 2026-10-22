# C:\pc_optimizer\core\optimizer.py

import os
import subprocess
import shutil
import platform
import json
import time

class WindowsOptimizer:
    @staticmethod
    def get_game_mode():
        if platform.system() != "Windows":
            return "Not Windows"
        try:
            cmd = 'reg query "HKCU\\Software\\Microsoft\\GameBar" /v AllowAutoGameMode'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
            if "0x1" in output:
                return "Enabled"
            return "Disabled"
        except Exception:
            return "Unknown"

    @staticmethod
    def set_game_mode(enable: bool):
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            val = 1 if enable else 0
            cmd = f'reg add "HKCU\\Software\\Microsoft\\GameBar" /v AllowAutoGameMode /t REG_DWORD /d {val} /f'
            subprocess.check_call(cmd, shell=True)
            return True, "Game Mode preference updated."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def set_xbox_captures(disable: bool):
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            val = 0 if disable else 1
            cmd = f'reg add "HKCU\\System\\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d {val} /f'
            subprocess.check_call(cmd, shell=True)
            return True, "Xbox background capture settings updated."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_ultimate_power_plan_status():
        if platform.system() != "Windows":
            return "Not Windows"
        try:
            output = subprocess.check_output('powercfg /getactivescheme', shell=True).decode()
            if "Ultimate Performance" in output or "8c5e7fda-e8bf-496d-815a-8813f8763104" in output:
                return "Active"
            return "Inactive"
        except Exception:
            return "Unknown"

    @staticmethod
    def enable_ultimate_power_plan():
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            subprocess.run('powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 8c5e7fda-e8bf-496d-815a-8813f8763104', shell=True, stderr=subprocess.DEVNULL)
            subprocess.check_call('powercfg /setactive 8c5e7fda-e8bf-496d-815a-8813f8763104', shell=True)
            return True, "Ultimate Performance power plan activated."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_hags_status():
        if platform.system() != "Windows":
            return "Not Windows"
        try:
            cmd = 'reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v HwSchMode'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
            if "0x2" in output:
                return "Enabled"
            return "Disabled"
        except Exception:
            return "Unknown"

    @staticmethod
    def set_hags(enable: bool):
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            val = 2 if enable else 1
            cmd = f'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v HwSchMode /t REG_DWORD /d {val} /f'
            subprocess.check_call(cmd, shell=True)
            return True, "HAGS updated. Restart required to take effect."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_network_adapters():
        adapters = []
        if platform.system() != "Windows":
            return adapters
        try:
            cmd = 'powershell -Command "Get-NetAdapter | Where-Object Status -eq \'Up\' | Select-Object Name, InterfaceIndex"'
            output = subprocess.check_output(cmd, shell=True).decode()
            lines = output.splitlines()
            for line in lines[2:]:  # skip header
                parts = line.split()
                if parts:
                    name = " ".join(parts[:-1])
                    if name:
                        adapters.append(name)
        except Exception:
            pass
        if not adapters:
            adapters.append("Ethernet")
        return adapters

    @staticmethod
    def apply_dns(adapter_name: str, primary_ipv4: str, secondary_ipv4: str):
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            cmd = f'powershell -Command "Set-DnsClientServerAddress -InterfaceAlias \'{adapter_name}\' -ServerAddresses (\'{primary_ipv4}\', \'{secondary_ipv4}\')"'
            subprocess.check_call(cmd, shell=True)
            subprocess.run('ipconfig /flushdns', shell=True, stderr=subprocess.DEVNULL)
            return True, f"Successfully applied DNS {primary_ipv4}, {secondary_ipv4} to adapter '{adapter_name}'."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def restore_dhcp_dns(adapter_name: str):
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            cmd = f'powershell -Command "Set-DnsClientServerAddress -InterfaceAlias \'{adapter_name}\' -ResetServerAddresses"'
            subprocess.check_call(cmd, shell=True)
            subprocess.run('ipconfig /flushdns', shell=True, stderr=subprocess.DEVNULL)
            return True, f"Successfully restored automatic (DHCP) DNS for adapter '{adapter_name}'."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def apply_game_profile(profile_name: str):
        """Game profile hook. Does not change system settings yet (see v1.2 plan)."""
        if platform.system() != "Windows":
            return False, "Non-Windows OS"
        try:
            prof_lower = profile_name.lower()
            if "ultra" in prof_lower or "performance" in prof_lower:
                # NOTE: this used to run Clear-RecycleBin, which permanently deletes the
                # user's files. Profiles must never delete user data. Real profile tuning
                # is planned for v1.2; until then this reports honestly.
                return True, "Ultra Performance profile selected (no system changes are applied yet)."
            elif "high" in prof_lower:
                return True, "High profile selected (no system changes are applied yet)."
            else:
                return True, f"{profile_name} profile selected (no system changes are applied yet)."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def cleanup_temp_files():
        cleaned_size = 0
        temp_dirs = []
        if platform.system() == "Windows":
            temp_dirs = [
                os.path.expandvars(r'%TEMP%'),
                os.path.expandvars(r'%SystemRoot%\\Temp')
            ]
        
        for folder in temp_dirs:
            if os.path.exists(folder):
                try:
                    items = os.listdir(folder)
                except PermissionError:
                    continue
                
                for item in items:
                    item_path = os.path.join(folder, item)
                    try:
                        if os.path.isfile(item_path) or os.path.islink(item_path):
                            file_size = os.path.getsize(item_path)
                            os.unlink(item_path)
                            cleaned_size += file_size
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                    except Exception:
                        continue
        
        return f"Successfully cleaned approx. {cleaned_size / (1024**2):.2f} MB of temporary files."