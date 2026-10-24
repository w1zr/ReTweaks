from feature_ai import topic_for


def test_brand_header_does_not_make_every_page_a_tweaks_page():
    for title in ('Settings', 'Backgrounds', 'Browser', 'File Transfers', 'About', 'Crosshair'):
        assert topic_for(title, 'RETWEAKS') is None
    for title in ('Individual tweaks', 'Presets', 'Windows tweaks'):
        assert topic_for(title, 'RETWEAKS') == 'tweaks'
    assert topic_for('Dashboard', 'RETWEAKS') == 'monitor'
    assert topic_for('Drivers', 'RETWEAKS') == 'drivers'
    assert topic_for('Network', 'RETWEAKS') == 'network'
