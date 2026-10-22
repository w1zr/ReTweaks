"""Tests for the parts that turn raw Windows output into what the UI shows.

They run on any OS (no Windows needed). Sample data mirrors real output formats from
PowerShell ConvertTo-Json, the GPU Engine performance counters and LibreHardwareMonitor.
"""
from core.hardware import parse_static, merge_gpus
from core.telemetry import aggregate_gpu_engines, aggregate_gpu_memory, cpu_mhz_from_counters, _match_nvml
from core.sensors_lhm import parse_lhm
from core.gpu_dxgi import luid_key


def test_gpu_engine_aggregation_matches_task_manager_rules():
    inst = {
        # two processes on the 3D engine of the dGPU: they add up
        "pid_100_luid_0x00000000_0x0000D1A3_phys_0_eng_0_engtype_3D": 30.0,
        "pid_200_luid_0x00000000_0x0000D1A3_phys_0_eng_0_engtype_3D": 25.5,
        # video decode engine on the same GPU: separate engine, lower
        "pid_300_luid_0x00000000_0x0000D1A3_phys_0_eng_3_engtype_VideoDecode": 10.0,
        # iGPU (different LUID, lower-case hex like some drivers) mostly idle
        "pid_100_luid_0x00000000_0x0000abcd_phys_0_eng_0_engtype_3D": 2.0,
    }
    out = aggregate_gpu_engines(inst)
    assert out[luid_key(0, 0xD1A3)] == {"load": 55.5, "engine": "3D"}
    assert out[luid_key(0, 0xABCD)]["load"] == 2.0


def test_gpu_engine_load_is_capped_at_100():
    inst = {f"pid_{i}_luid_0x00000000_0x00000001_phys_0_eng_0_engtype_3D": 60.0 for i in range(3)}
    assert aggregate_gpu_engines(inst)[luid_key(0, 1)]["load"] == 100.0


def test_gpu_memory():
    gib = 1024 ** 3
    out = aggregate_gpu_memory({"luid_0x00000000_0x0000D1A3_phys_0": 3 * gib})
    assert out[luid_key(0, 0xD1A3)] == 3 * gib


def test_negative_luid_high_part_normalizes():
    # LUID.HighPart is signed; PDH prints it as unsigned hex
    assert luid_key(-1, 5) == "0xFFFFFFFF_0x00000005"


def test_cpu_clock():
    assert cpu_mhz_from_counters(3000, 150.0) == 4500
    assert cpu_mhz_from_counters(None, 150.0) is None


def test_parse_static_single_items_and_ram():
    raw = {
        "cpu": {"Name": "AMD Ryzen 7 7800X3D 8-Core Processor ", "NumberOfCores": 8,
                "NumberOfLogicalProcessors": 16, "MaxClockSpeed": 4201, "L3CacheSize": 98304},
        "board": {"Manufacturer": "ASUSTeK COMPUTER INC.", "Product": "ROG STRIX B650-A GAMING WIFI"},
        "bios": {"SMBIOSBIOSVersion": "1813", "ReleaseDate": "2024-01-10"},
        "ram_sticks": [
            {"Capacity": 17179869184, "Speed": 6000, "ConfiguredClockSpeed": 6000, "SMBIOSMemoryType": 34, "DeviceLocator": "DIMM_A2"},
            {"Capacity": 17179869184, "Speed": 6000, "ConfiguredClockSpeed": 6000, "SMBIOSMemoryType": 34, "DeviceLocator": "DIMM_B2"},
        ],
        "ram_slots": 4,
        "disks": {"DeviceId": "0", "FriendlyName": "Samsung SSD 990 PRO 2TB", "Size": 2000398934016,
                  "MediaType": "SSD", "BusType": "NVMe", "Health": "Healthy"},
        "partitions": [{"DiskNumber": 0, "DriveLetter": "C"}, {"DiskNumber": 0, "DriveLetter": "D"}],
    }
    s = parse_static(raw)
    assert s["cpu"]["name"] == "AMD Ryzen 7 7800X3D 8-Core Processor"
    assert s["cpu"]["l3_mb"] == 96.0
    assert s["ram"]["type"] == "DDR5" and s["ram"]["running_mts"] == 6000
    assert s["ram"]["slots_used"] == 2 and s["ram"]["slots_total"] == 4
    assert s["disks"][0]["letters"] == ["C:", "D:"] and s["disks"][0]["health"] == "Healthy"
    assert s["motherboard"]["model"] == "ROG STRIX B650-A GAMING WIFI"


def test_parse_static_hides_oem_placeholders_and_missing_data():
    s = parse_static({"board": {"Manufacturer": "To be filled by O.E.M.", "Product": "Default string"}})
    assert s["motherboard"]["manufacturer"] is None and s["motherboard"]["model"] is None
    assert s["ram"]["type"] is None and s["disks"] == []


def test_bad_slot_count_is_ignored():
    raw = {"ram_sticks": [{"Capacity": 8 * 1024 ** 3}] * 2, "ram_slots": 0}
    assert parse_static(raw)["ram"]["slots_total"] is None


def test_merge_gpus_keeps_dxgi_vram_and_adds_driver():
    dxgi = [{"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "vendor": "NVIDIA", "vram_gb": 8.0, "luid": "x"}]
    wmi = [{"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "driver_version": "32.0.15.6094"},
           {"name": "Intel(R) UHD Graphics", "driver_version": "31.0"}]
    g = merge_gpus(dxgi, wmi)
    assert g[0]["vram_gb"] == 8.0 and g[0]["driver_version"] == "32.0.15.6094"


def test_merge_gpus_fallback_never_reports_capped_wmi_vram():
    g = merge_gpus([], [{"name": "AMD Radeon RX 7800 XT", "driver_version": "1"}])
    assert g[0]["vram_gb"] is None and g[0]["vendor"] == "AMD"


def test_nvml_matching():
    adapters = [{"name": "NVIDIA GeForce RTX 3080", "vendor": "NVIDIA", "luid": "a"},
                {"name": "Intel(R) UHD Graphics 770", "vendor": "Intel", "luid": "b"}]
    assert _match_nvml(adapters, [("NVIDIA GeForce RTX 3080", "H")]) == {"a": "H"}


def test_lhm_parsing():
    hw = [{"Identifier": "/amdcpu/0", "Name": "AMD Ryzen 7 5800X", "HardwareType": "Cpu"},
          {"Identifier": "/gpu-nvidia/0", "Name": "NVIDIA GeForce RTX 3070", "HardwareType": "GpuNvidia"},
          {"Identifier": "/lpc/nct6798d", "Name": "Nuvoton NCT6798D", "HardwareType": "SuperIO"}]
    sensors = [
        {"Name": "Core (Tctl/Tdie)", "SensorType": "Temperature", "Value": 61.5, "Parent": "/amdcpu/0"},
        {"Name": "CCD1 (Tdie)", "SensorType": "Temperature", "Value": 58.0, "Parent": "/amdcpu/0"},
        {"Name": "GPU Memory Junction", "SensorType": "Temperature", "Value": 70.0, "Parent": "/gpu-nvidia/0"},
        {"Name": "GPU Core", "SensorType": "Temperature", "Value": 55.0, "Parent": "/gpu-nvidia/0"},
        {"Name": "GPU Hot Spot", "SensorType": "Temperature", "Value": 66.0, "Parent": "/gpu-nvidia/0"},
        {"Name": "Fan #1", "SensorType": "Fan", "Value": 1150.0, "Parent": "/lpc/nct6798d"},
        {"Name": "Fan #3", "SensorType": "Fan", "Value": 0.0, "Parent": "/lpc/nct6798d"},
        {"Name": "Temperature #2", "SensorType": "Temperature", "Value": -55.0, "Parent": "/lpc/nct6798d"},
        {"Name": "System", "SensorType": "Temperature", "Value": 34.0, "Parent": "/lpc/nct6798d"},
    ]
    r = parse_lhm(hw, sensors)
    assert r["cpu_temp"] == 61.5
    assert r["gpu_temps"]["NVIDIA GeForce RTX 3070"] == {"memory": 70.0, "core": 55.0, "hotspot": 66.0}
    assert [f["rpm"] for f in r["fans"]] == [1150.0]      # stopped/unused headers hidden
    assert r["board_temps"] == [{"name": "System", "celsius": 34.0}]  # impossible -55 C dropped
