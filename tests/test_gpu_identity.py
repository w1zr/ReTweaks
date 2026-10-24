from core.gpu_dxgi import unique_adapters
from core.hardware import merge_gpus


def test_virtual_adapter_copying_real_gpu_name_is_not_an_extra_gpu():
    physical = {'name': 'Intel Iris Xe', 'luid': 'a',
                'device_path': r'\\?\PCI#VEN_8086&DEV_46A8#physical'}
    virtual = {'name': 'Intel Iris Xe', 'luid': 'b',
               'device_path': r'\\?\ROOT#DISPLAY#0000#interface'}
    assert unique_adapters([physical, virtual]) == [physical]


def test_duplicate_device_path_with_different_luids_is_one_gpu():
    first = {'name': 'GPU', 'luid': 'a', 'device_path': r'PCI#DEVICE#1'}
    duplicate = {**first, 'luid': 'b', 'device_path': r'pci#device#1'}
    assert unique_adapters([first, duplicate]) == [first]


def test_two_identical_physical_cards_are_preserved():
    cards = [{'name': 'NVIDIA RTX', 'luid': str(i),
              'device_path': rf'PCI#DEVICE#{i}'} for i in range(2)]
    assert unique_adapters(cards) == cards


def test_unknown_identity_does_not_hide_real_cards():
    cards = [{'name': 'GPU', 'luid': 'a'}, {'name': 'GPU', 'luid': 'b'}]
    assert unique_adapters(cards) == cards


def test_wmi_fallback_filters_virtual_and_duplicate_devices():
    real = {'name': 'Intel Iris Xe', 'pnp_id': r'PCI\VEN_8086\1'}
    virtual = {'name': 'Intel Iris Xe', 'pnp_id': r'ROOT\DISPLAY\0000'}
    gpus = merge_gpus([], [real, dict(real), virtual,
                           {'name': 'Microsoft Remote Display Adapter'}])
    assert len(gpus) == 1
    assert gpus[0]['name'] == real['name']
    assert gpus[0]['vram_gb'] is None


def test_integrated_and_dedicated_gpus_both_remain_visible():
    cards = [{'name': 'Intel UHD', 'luid': 'i'},
             {'name': 'NVIDIA RTX', 'luid': 'd'}]
    assert len(merge_gpus(cards, [])) == 2
