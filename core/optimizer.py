# core/optimizer.py
"""Windows tweaks. Every get_* reads the real current state; every set_* returns (ok, message).

Commands run without a console window (core.winutil.run), so nothing flashes on screen.
"""

import os
import shutil

from core.winutil import IS_WINDOWS, run, run_powershell, run_powershell_json, as_list

ULTIMATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"   # built-in Ultimate Performance template
ULTIMATE_COPY_GUID = "8c5e7fda-e8bf-496d-815a-8813f8763104"
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"     # Windows default plan

NOT_WINDOWS = (False, "This only works on Windows.")

# Xbox Game Bar capture: the old global switch plus the two toggles in
# Settings > Gaming > Captures ("Record what happened" = HistoricalCaptureEnabled)
_CAPTURE_VALUES = [
    (r"HKCU\System\GameConfigStore", "GameDVR_Enabled"),
    (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled"),
    (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "HistoricalCaptureEnabled"),
]


def _ps_quote(text):
    """Quote a value for PowerShell single-quoted strings (adapter names can contain ')."""
    return "'" + str(text).replace("'", "''") + "'"


def _reg_query_dword(key, value):
    """Return the DWORD as int, or None if the value doesn't exist."""
    try:
        r = run(["reg", "query", key, "/v", value], timeout=10)
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0].lower() == value.lower() and parts[1] == "REG_DWORD":
                return int(parts[2], 16)
    except Exception:
        return None
    return None


def _reg_set_dword(key, value, data):
    r = run(["reg", "add", key, "/v", value, "/t", "REG_DWORD", "/d", str(data), "/f"], timeout=10)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "reg.exe failed (try running as administrator)."
    return True, ""


class WindowsOptimizer:
    # ------------------------------------------------------------ Game Mode
    @staticmethod
    def get_game_mode():
        if not IS_WINDOWS:
            return "Not Windows"
        v = _reg_query_dword(r"HKCU\Software\Microsoft\GameBar", "AutoGameModeEnabled")
        if v is None:
            # Value missing = Windows default, which is ON in Windows 10 1703+ and Windows 11
            return "Enabled (Windows default)"
        return "Enabled" if v == 1 else "Disabled"

    @staticmethod
    def set_game_mode(enable: bool):
        if not IS_WINDOWS:
            return NOT_WINDOWS
        ok, err = _reg_set_dword(r"HKCU\Software\Microsoft\GameBar", "AutoGameModeEnabled", 1 if enable else 0)
        # Older RyTweaks versions wrote AllowAutoGameMode; keep it in sync
        _reg_set_dword(r"HKCU\Software\Microsoft\GameBar", "AllowAutoGameMode", 1 if enable else 0)
        return (True, f"Game Mode {'enabled' if enable else 'disabled'}.") if ok else (False, err)

    # ------------------------------------------------------------ Xbox Game Bar background capture
    @staticmethod
    def get_xbox_captures():
        if not IS_WINDOWS:
            return "Not Windows"
        values = [_reg_query_dword(k, v) for k, v in _CAPTURE_VALUES]
        if any(v == 0 for v in values):
            return "Disabled"
        if all(v is None for v in values):
            return "Enabled (Windows default)"
        return "Enabled"

    @staticmethod
    def set_xbox_captures(disable: bool):
        if not IS_WINDOWS:
            return NOT_WINDOWS
        ok, err = True, ""
        for key, value in _CAPTURE_VALUES:
            k_ok, k_err = _reg_set_dword(key, value, 0 if disable else 1)
            if not k_ok:
                ok, err = False, k_err
        return (True, f"Background capture {'disabled' if disable else 'enabled'}.") if ok else (False, err)

    # ------------------------------------------------------------ Power plans
    @staticmethod
    def get_active_power_plan():
        if not IS_WINDOWS:
            return "Not Windows"
        try:
            out = run(["powercfg", "/getactivescheme"], timeout=10).stdout
            # "Power Scheme GUID: <guid>  (Name)"
            if "(" in out and ")" in out:
                return out[out.index("(") + 1:out.rindex(")")]
            return out.strip() or "Unknown"
        except Exception:
            return "Unknown"

    @staticmethod
    def get_ultimate_power_plan_status():
        if not IS_WINDOWS:
            return "Not Windows"
        try:
            out = run(["powercfg", "/getactivescheme"], timeout=10).stdout.lower()
            return "Active" if ULTIMATE_COPY_GUID in out or "ultimate performance" in out else "Inactive"
        except Exception:
            return "Unknown"

    @staticmethod
    def enable_ultimate_power_plan():
        if not IS_WINDOWS:
            return NOT_WINDOWS
        # Creates the plan if it doesn't exist yet (fails harmlessly if it already does)
        run(["powercfg", "-duplicatescheme", ULTIMATE_GUID, ULTIMATE_COPY_GUID], timeout=15)
        r = run(["powercfg", "/setactive", ULTIMATE_COPY_GUID], timeout=15)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout).strip() or "powercfg failed."
        return True, "Ultimate Performance power plan is now active. Laptops will use more battery and run warmer."

    @staticmethod
    def set_balanced_power_plan():
        if not IS_WINDOWS:
            return NOT_WINDOWS
        r = run(["powercfg", "/setactive", BALANCED_GUID], timeout=15)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout).strip() or "powercfg failed."
        return True, "Balanced power plan (Windows default) is now active."

    # ------------------------------------------------------------ HAGS
    @staticmethod
    def get_hags_status():
        if not IS_WINDOWS:
            return "Not Windows"
        v = _reg_query_dword(r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode")
        if v is None:
            return "Not set (driver default)"
        return "Enabled" if v == 2 else "Disabled"

    @staticmethod
    def set_hags(enable: bool):
        if not IS_WINDOWS:
            return NOT_WINDOWS
        ok, err = _reg_set_dword(r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2 if enable else 1)
        if not ok:
            return False, err + " (HAGS needs administrator rights.)"
        return True, f"HAGS {'enabled' if enable else 'disabled'}. Restart your PC for it to take effect."

    # ------------------------------------------------------------ Network / DNS
    @staticmethod
    def get_network_adapters():
        """Names of connected network adapters."""
        if not IS_WINDOWS:
            return []
        data = run_powershell_json(
            "Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name | ConvertTo-Json -Compress",
            timeout=20)
        return [a.get("Name") for a in as_list(data) if a.get("Name")]

    @staticmethod
    def get_dns_servers(adapter_name):
        """IPv4 DNS servers set on an adapter (empty list = automatic/DHCP or unknown)."""
        if not IS_WINDOWS or not adapter_name:
            return []
        data = run_powershell_json(
            f"(Get-DnsClientServerAddress -InterfaceAlias {_ps_quote(adapter_name)} -AddressFamily IPv4)"
            ".ServerAddresses | ConvertTo-Json -Compress", timeout=20)
        return [str(x) for x in as_list(data)]

    @staticmethod
    def apply_dns(adapter_name: str, primary_ipv4: str, secondary_ipv4: str):
        if not IS_WINDOWS:
            return NOT_WINDOWS
        out = run_powershell(
            f"try {{ Set-DnsClientServerAddress -InterfaceAlias {_ps_quote(adapter_name)} "
            f"-ServerAddresses ({_ps_quote(primary_ipv4)}, {_ps_quote(secondary_ipv4)}) -ErrorAction Stop; "
            "Clear-DnsClientCache; 'OK' } catch { $_.Exception.Message }", timeout=30).strip()
        if out != "OK":
            return False, out or "Could not change DNS (needs administrator rights)."
        return True, f"DNS for '{adapter_name}' set to {primary_ipv4} / {secondary_ipv4}."

    @staticmethod
    def restore_dhcp_dns(adapter_name: str):
        if not IS_WINDOWS:
            return NOT_WINDOWS
        out = run_powershell(
            f"try {{ Set-DnsClientServerAddress -InterfaceAlias {_ps_quote(adapter_name)} -ResetServerAddresses "
            "-ErrorAction Stop; Clear-DnsClientCache; 'OK' } catch { $_.Exception.Message }", timeout=30).strip()
        if out != "OK":
            return False, out or "Could not reset DNS (needs administrator rights)."
        return True, f"DNS for '{adapter_name}' set back to automatic."

    # ------------------------------------------------------------ Temp files
    @staticmethod
    def cleanup_temp_files():
        """Delete files in the user and Windows temp folders. Files in use are skipped."""
        cleaned_size = 0
        temp_dirs = []
        if IS_WINDOWS:
            temp_dirs = [os.path.expandvars(r'%TEMP%'), os.path.expandvars(r'%SystemRoot%\Temp')]
        for folder in temp_dirs:
            if not os.path.isdir(folder):
                continue
            try:
                items = os.listdir(folder)
            except PermissionError:
                continue
            for item in items:
                item_path = os.path.join(folder, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        size = os.path.getsize(item_path)
                        os.unlink(item_path)
                        cleaned_size += size
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                except Exception:
                    continue
        return f"Freed about {cleaned_size / (1024 ** 2):.2f} MB of temporary files."
