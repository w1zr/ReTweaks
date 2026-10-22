# core/gpu_dxgi.py
"""List every GPU in the PC using DirectX Graphics Infrastructure (DXGI).

Why DXGI:
- Works for NVIDIA, AMD and Intel (and laptops with two GPUs).
- Reports dedicated VRAM as a 64-bit number, so 8/12/16/24 GB cards show correctly.
  (WMI's Win32_VideoController.AdapterRAM is 32-bit and tops out around 4 GB.)
- Gives each GPU's LUID, the same ID Windows uses in its "GPU Engine" performance
  counters. That's how core/telemetry.py knows which load belongs to which GPU.

Uses only ctypes (built into Python), no extra library.
"""

import ctypes
import uuid

from core.winutil import IS_WINDOWS

VENDORS = {0x10DE: "NVIDIA", 0x1002: "AMD", 0x1022: "AMD", 0x8086: "Intel", 0x1414: "Microsoft",
           0x5143: "Qualcomm", 0x13B5: "ARM"}

DXGI_ADAPTER_FLAG_SOFTWARE = 2
DXGI_ERROR_NOT_FOUND = 0x887A0002 - 0x100000000  # as a signed HRESULT
IID_IDXGIFactory1 = "770aae78-f26f-4dba-a829-253c83d1b387"

# Virtual/remote adapters that are not real GPUs
_VIRTUAL_HINTS = ("basic render", "basic display", "remote display", "parsec", "virtual",
                  "displaylink", "indirect display", "hyper-v", "vmware", "meta virtual")


def vendor_from_name(name):
    n = (name or "").lower()
    if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n:
        return "NVIDIA"
    if "amd" in n or "radeon" in n:
        return "AMD"
    if "intel" in n:
        return "Intel"
    return None


def is_virtual(name):
    n = (name or "").lower()
    return any(h in n for h in _VIRTUAL_HINTS)


def _guess_integrated(vendor, dedicated_bytes):
    """True / False / None (unknown).

    Under 512 MB of dedicated memory is always an integrated GPU. NVIDIA makes no integrated
    GPUs for x86 PCs. But AMD APUs can reserve 1-16 GB as "dedicated" in the BIOS, and Intel
    makes both kinds (Arc), so with a big number we can't tell and say so.
    """
    if dedicated_bytes < 512 * 1024 * 1024:
        return True
    if vendor == "NVIDIA":
        return False
    return None


def luid_key(high, low):
    """Normalized LUID key, matching how PDH names GPU counter instances."""
    return f"0x{high & 0xFFFFFFFF:08X}_0x{low & 0xFFFFFFFF:08X}"


def list_adapters():
    """Return a list of dicts: name, vendor, vram_gb, shared_gb, luid. Empty list if DXGI fails."""
    if not IS_WINDOWS:
        return []
    try:
        return _list_adapters_windows()
    except Exception:
        return []


def _list_adapters_windows():
    from ctypes import wintypes

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class DXGI_ADAPTER_DESC1(ctypes.Structure):
        _fields_ = [
            ("Description", wintypes.WCHAR * 128),
            ("VendorId", wintypes.UINT),
            ("DeviceId", wintypes.UINT),
            ("SubSysId", wintypes.UINT),
            ("Revision", wintypes.UINT),
            ("DedicatedVideoMemory", ctypes.c_size_t),
            ("DedicatedSystemMemory", ctypes.c_size_t),
            ("SharedSystemMemory", ctypes.c_size_t),
            ("AdapterLuid", LUID),
            ("Flags", wintypes.UINT),
        ]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def com_method(obj, index, *argtypes):
        """Get method #index from a COM object's vtable."""
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
        return proto(vtbl[index])

    def release(obj):
        if obj:
            vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(obj)

    iid = GUID.from_buffer_copy(uuid.UUID(IID_IDXGIFactory1).bytes_le)
    factory = ctypes.c_void_p()
    hr = ctypes.WinDLL("dxgi").CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory))
    if hr != 0 or not factory:
        return []

    adapters = []
    try:
        # IDXGIFactory1::EnumAdapters1 is vtable slot 12
        enum_adapters1 = com_method(factory, 12, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        index = 0
        while index < 16:
            adapter = ctypes.c_void_p()
            hr = enum_adapters1(factory, index, ctypes.byref(adapter))
            if hr == DXGI_ERROR_NOT_FOUND or hr != 0:
                break
            try:
                desc = DXGI_ADAPTER_DESC1()
                # IDXGIAdapter1::GetDesc1 is vtable slot 10
                get_desc1 = com_method(adapter, 10, ctypes.POINTER(DXGI_ADAPTER_DESC1))
                if get_desc1(adapter, ctypes.byref(desc)) == 0:
                    name = desc.Description.strip()
                    software = bool(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)
                    if not software and not is_virtual(name):
                        adapters.append({
                            "name": name,
                            "vendor": VENDORS.get(desc.VendorId) or vendor_from_name(name),
                            "vendor_id": desc.VendorId,
                            "vram_gb": round(desc.DedicatedVideoMemory / (1024 ** 3), 1) or None,
                            "shared_gb": round(desc.SharedSystemMemory / (1024 ** 3), 1) or None,
                            "integrated": _guess_integrated(VENDORS.get(desc.VendorId), desc.DedicatedVideoMemory),
                            "luid": luid_key(desc.AdapterLuid.HighPart, desc.AdapterLuid.LowPart),
                        })
            finally:
                release(adapter)
            index += 1
    finally:
        release(factory)

    # The same physical GPU can be listed twice (one per output); keep one per LUID
    seen, unique = set(), []
    for a in adapters:
        if a["luid"] not in seen:
            seen.add(a["luid"])
            unique.append(a)
    # Dedicated GPUs first, so the dashboard shows the gaming GPU as GPU 1
    unique.sort(key=lambda a: (a["integrated"] is True, -(a["vram_gb"] or 0)))
    return unique
