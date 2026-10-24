"""Contextual AI entry points. Only explicit, read-only observations are shared."""
import tkinter as tk


TOPICS = {
    'hardware': ('Hardware and parts', ('Explain my parts', 'Upgrade advice')),
    'monitor': ('Performance diagnostics', ('Explain these readings', 'Investigate slow performance')),
    'health': ('Health Check', ('Explain scan results', 'Prioritize fixes')),
    'tweaks': ('Windows tweaks', ('Explain selected tweaks', 'Recommend a reversible plan')),
    'games': ('Game performance', ('Explain game settings', 'Help with FPS and stutter')),
    'drivers': ('Drivers', ('Explain driver choices', 'Troubleshoot a driver problem')),
    'network': ('Network', ('Explain test results', 'Troubleshoot connection')),
    'storage': ('Storage and cleanup', ('Explain storage tools', 'Plan a careful cleanup')),
    'startup': ('Startup apps', ('Explain startup impact', 'Help choose what to disable')),
    'cooling': ('Temperatures and cooling', ('Explain temperatures', 'Investigate heat or fan noise')),
    'display': ('Display', ('Explain display settings', 'Help choose resolution')),
    'benchmark': ('Benchmarks and snapshots', ('Explain benchmark results', 'Compare performance')),
    'recovery': ('Backups and repairs', ('Explain recovery options', 'Plan a repair')),
    'apps': ('Apps and utilities', ('Help choose apps', 'Explain an installation problem')),
}


def topic_for(title, kicker=''):
    # Branding such as RETWEAKS is not a feature category.
    text = str(title).lower().replace('retweaks', '')
    for words, topic in (
        (('ai assistant', 'windows activation', 'transparent tb'), None),
        (('driver',), 'drivers'),
        (('hardware', 'specification'), 'hardware'),
        (('health',), 'health'),
        (('temperature', 'fan control', 'rgb lighting', 'fan rgb'), 'cooling'),
        (('network',), 'network'),
        (('startup',), 'startup'),
        (('cleanup', 'storage', 'disk tools'), 'storage'),
        (('snapshot', 'benchmark'), 'benchmark'),
        (('display',), 'display'),
        (('game',), 'games'),
        (('preset', 'tweak', 'ctt library', 'customize', 'build your own list'), 'tweaks'),
        (('backup', 'repair', 'fixes'), 'recovery'),
        (('dashboard', 'monitor'), 'monitor'),
        (('app starter', 'daily tools', 'pc value'), 'apps'),
    ):
        if any(word in text for word in words):
            return topic
    return None


def attach_actions(parent, g, topic):
    hub = parent.winfo_toplevel()
    if topic not in TOPICS or not hasattr(hub, 'ask_feature_ai'):
        return
    row = tk.Frame(parent, bg=g['BG'])
    row.pack(fill='x', pady=(0, 10))
    tk.Label(row, text='AI help', bg=g['BG'], fg=g['MUTED'], font=(g['UI'], 9)).pack(side='left', padx=(0, 10))
    for task in TOPICS[topic][1]:
        g['RButton'](row, task, lambda task=task: hub.ask_feature_ai(topic, task),
                     height=30, radius=10).pack(side='left', padx=(0, 6))


def _fields(value, keys):
    return {key: value[key] for key in keys if key in value} if isinstance(value, dict) else {}


def observations(hub, topic):
    """No file paths, device serials, network addresses, or arbitrary widget text."""
    result = {'topic': TOPICS.get(topic, (topic,))[0],
              'limits': 'Only completed readings are observations. Missing results are unknown.'}
    sample = getattr(hub, 'rt_last_sample', None) or {}
    static = getattr(hub, 'rt_static', None) or {}
    if topic in ('hardware', 'monitor', 'games', 'display', 'cooling'):
        result['parts'] = {
            'cpu': _fields(static.get('cpu'), ('name', 'cores', 'threads', 'base_mhz', 'socket')),
            'motherboard': _fields(static.get('motherboard'), ('manufacturer', 'model', 'bios_version')),
            'memory': _fields(static.get('ram'), ('installed_gb', 'type', 'running_mts', 'slots_used', 'slots_total')),
            'graphics': [_fields(gpu, ('name', 'vendor', 'vram_gb', 'integrated', 'driver_version'))
                         for gpu in static.get('gpus', [])[:8]],
        }
    if topic in ('hardware', 'monitor', 'cooling', 'games', 'benchmark'):
        result['cpu'] = _fields(sample.get('cpu'), ('load', 'mhz', 'temp_c'))
        result['ram'] = _fields(sample.get('ram'), ('percent', 'used_gb', 'total_gb'))
        result['gpus'] = [_fields(gpu, ('name', 'vendor', 'load', 'vram_total_gb', 'vram_used_gb',
                                             'temp_c', 'hotspot_c', 'core_mhz', 'power_w', 'fan_pct'))
                          for gpu in sample.get('gpus', [])[:8]]
    pages = getattr(hub, 'rt_pages', {})
    if topic == 'health':
        from core.ai_assistant import scrub, private_terms
        page = pages.get('Health Check')
        result['completed_checks'] = [_fields(item, ('name', 'status', 'detail', 'fix_label'))
                                      for item in getattr(page, 'results', {}).values()][:20]
        for check in result['completed_checks']:
            if 'detail' in check:
                check['detail'] = scrub(check['detail'], private_terms())[:1200]
    if topic == 'network':
        page = pages.get('Network')
        result['ping'] = _fields(getattr(page, 'ai_ping_result', None),
                                ('avg', 'best', 'worst', 'jitter', 'loss_pct', 'count'))
        result['dns_tests'] = getattr(page, 'ai_dns_results', [])
    if topic == 'drivers':
        page = getattr(hub, 'drivers', None)
        result['components'] = [_fields(row, ('kind', 'name', 'vendor', 'installed', 'version',
                                               'date', 'url', 'verified'))
                                for row in getattr(page, 'rows', [])[:32]]
        downloads = getattr(page, 'downloads', None)
        result['official_installer_offers'] = [_fields(offer, ('vendor', 'title', 'version', 'date', 'url', 'note'))
                                               for offer in getattr(downloads, 'offers', {}).values()]
        result['windows_update_offers'] = [_fields(row, ('title', 'maker', 'cls', 'date'))
                                           for row in getattr(downloads, 'wu', [])[:30]]
    if topic == 'games':
        game = getattr(hub, 'game', None)
        if game is not None and callable(getattr(game, 'get', None)):
            result['selected_game'] = str(game.get())[:120]
    return result


def draft(topic, task):
    title = TOPICS[topic][0]
    return (f'{task} in RETWEAKS: {title}.\n\n'
            'Use the current feature observations in the hub context when enabled. Explain what the parts, '
            'readings, options, or task mean, then give specific next steps using the controls in RETWEAKS. '
            'Separate observed facts from possibilities. If a result has not been collected, say which scan '
            'to run. For parts, explain capabilities and compatibility without inventing current prices or '
            'specifications. For changes, explain the tradeoff, how to verify the result, and how to undo. '
            'I will review and apply actions myself. Ask only for information that is still missing.')
