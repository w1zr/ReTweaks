from drivers import components


def test_present_scan_ignores_stale_gpu_and_disconnected_devices():
    info={'gpu':'NVIDIA GeForce RTX 4060','cpu':'Intel Core i5'}
    devices=[{'name':'Intel Iris Xe Graphics','class':'DISPLAY','pnp':'PCI\\','present':True},
             {'name':'AMD Radeon RX 7600','class':'DISPLAY','pnp':'PCI\\','present':False},
             {'name':'Realtek Ethernet','class':'NET','present':False}]
    rows=components(info,devices,present_only=True)
    assert [r['name'] for r in rows if r['kind']=='Graphics']==['Intel Iris Xe Graphics']
    assert not any('AMD' in r['name'] or 'Ethernet' in r['name'] for r in rows)


def test_all_present_driver_categories_and_missing_driver_fallback():
    classes={'NET':'Network','MEDIA':'Audio','BLUETOOTH':'Bluetooth','DISKDRIVE':'Storage',
             'SCSIADAPTER':'Storage controller','USB':'USB controller','HIDCLASS':'Input device',
             'MONITOR':'Monitor','CAMERA':'Camera','SYSTEM':'Chipset / system','PRINTER':'Printer'}
    devices=[{'name':'Test '+cls,'class':cls,'present':True,'version':'1.2'} for cls in classes]
    devices += [{'name':'Unknown device','class':'','hardware':'VEN_1234&DEV_5678','present':True},
                {'name':'VPN virtual adapter','class':'NET','present':True}]
    rows=components({},devices,present_only=True)
    assert set(classes.values()) <= {r['kind'] for r in rows}
    assert any(r['hardware']=='VEN_1234&DEV_5678' and not r['installed'] for r in rows)
    assert not any('VPN' in r['name'] for r in rows)
    assert all(r['installed']=='1.2' for r in rows if r['kind']!='Other hardware')


def test_oem_support_does_not_lose_actual_device_vendor():
    rows=components({'cpu':'AMD Ryzen 7','raw':{'maker':'Dell','model':'Test PC'}},
                    [{'name':'Intel Wi-Fi','class':'NET','provider':'Intel','present':True}],present_only=True)
    nic=next(r for r in rows if r['kind']=='Network')
    cpu=next(r for r in rows if r['kind']=='CPU / chipset')
    assert nic['vendor_key']=='dell' and nic['device_vendor']=='intel'
    assert cpu['device_vendor']=='amd'


def test_component_inventory_is_not_truncated_to_32():
    rows=components({},[{'name':'Device '+str(i),'class':'USB','present':True} for i in range(50)],present_only=True)
    assert len(rows)==50
