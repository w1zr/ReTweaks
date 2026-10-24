import json
from types import SimpleNamespace as NS
from feature_ai import observations, topic_for, draft, TOPICS


def test_contextual_help_covers_distinct_pages():
    titles = ['Hardware', 'Dashboard', 'Health Check', 'Fan Control', 'Network', 'Startup apps',
              'Cleanup', '4D Render benchmark', 'Display', 'Settings that fit your game',
              'Build your own list', 'Backups & Fixes', 'App Starter', 'Drivers']
    assert {topic_for(title) for title in titles} == set(TOPICS)
    assert topic_for('Transparent TB (taskbar)') is None
    assert topic_for('AI assistant') is None


def test_parts_and_live_readings_share_only_allowed_fields():
    hub = NS(rt_static={'cpu': {'name': 'CPU', 'serial': 'PRIVATE'},
                        'motherboard': {'model': 'B760', 'serial': 'PRIVATE'},
                        'ram': {'type': 'DDR5'},
                        'gpus': [{'name': 'GPU', 'vram_gb': 8, 'luid': 'PRIVATE'}]},
             rt_last_sample={'cpu': {'load': 25}, 'gpus': [{'load': 30, 'pnp': 'PRIVATE'}]})
    result = observations(hub, 'hardware')
    assert result['parts']['motherboard']['model'] == 'B760'
    assert result['cpu']['load'] == 25
    assert 'PRIVATE' not in json.dumps(result)


def test_health_detail_scrubs_paths_and_network_addresses():
    hub = NS(rt_pages={'Health Check': NS(results={'disk': {
        'name': 'Disk', 'status': 'warn', 'detail': r'Check C:\Users\someone\file.txt at 192.168.1.3',
        'serial': 'PRIVATE'}})})
    encoded = json.dumps(observations(hub, 'health'))
    assert 'someone' not in encoded and '192.168' not in encoded and 'PRIVATE' not in encoded


def test_driver_context_has_versions_without_hardware_instance_ids():
    hub = NS(drivers=NS(rows=[{'name': 'GPU', 'installed': '1.2', 'hardware': 'PRIVATE'}],
                        downloads=NS(offers={'NVIDIA': {'title': 'Official driver', 'version': '2.0'}}, wu=[])))
    result = observations(hub, 'drivers')
    assert result['components'][0]['installed'] == '1.2'
    assert result['official_installer_offers'][0]['version'] == '2.0'
    assert 'PRIVATE' not in json.dumps(result)


def test_drafts_ask_for_help_without_claiming_actions_completed():
    for topic in TOPICS:
        text = draft(topic, TOPICS[topic][1][0])
        assert 'I will review and apply actions myself' in text
