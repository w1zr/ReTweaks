"""Shared capacity and quantity rules for all PC value-checker users."""
import math
import re

def kind_of(key):
    return 'Storage' if re.fullmatch(r'Storage(?: \d+)?', key) else key

def quantity(name):
    match = re.search(r'(?i)\b(?:quantity|qty)\s*[:=]?\s*(\d+)', name)
    return max(1, int(match.group(1))) if match else 1

def capacity_gb(name):
    # A kit's advertised total precedes its per-module breakdown: 32GB (2x16GB).
    kit = re.search(r'(?i)(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(GB|TB)', name)
    first = re.search(r'(?i)\b(\d+(?:\.\d+)?)\s*(TiB|GiB|TB|GB)\b', name)
    if not first:
        return int(kit.group(1)) * float(kit.group(2)) * (1000 if kit.group(3).upper() == 'TB' else 1) if kit else None
    if kit and kit.start() < first.start():
        return int(kit.group(1)) * float(kit.group(2)) * (1000 if kit.group(3).upper() == 'TB' else 1)
    trailing = re.search(r'(?i)(\d+(?:\.\d+)?)\s*(GB|TB)\s*[x×]\s*(\d+)\b', name)
    if trailing and trailing.start() == first.start():
        return float(trailing.group(1)) * int(trailing.group(3)) * (1000 if trailing.group(2).upper() == 'TB' else 1)
    value = float(first.group(1));unit = first.group(2).lower()
    if unit == 'tb':
        value *= 1000
    elif unit in ('gib', 'tib'):
        value *= (1024 ** (3 if unit == 'gib' else 4)) / 1e9
        sizes = (120,128,240,250,256,480,500,512,960,1000,1024,1920,2000,2048,3840,4000,4096,7680,8000)
        nearest = min(sizes, key=lambda size: abs(size - value))
        if abs(nearest - value) / nearest <= .03:
            value = nearest
    return value if math.isfinite(value) and value > 0 else None

def ram_spec(name):
    canonical = re.match(r'(?i)^([\d.]+) GB total\s*\((\d+) [x×] ([\d.]+) GB', name)
    if canonical:
        return {'kind':'RAM','total_gb':float(canonical.group(1)), 'modules':int(canonical.group(2)), 'module_gb':float(canonical.group(3))}
    total = 0;modules = 0;unit_sizes = set();layout_known = True
    for group in name.split(';'):
        gb = capacity_gb(group)
        if not gb:
            return {'kind':'RAM'}
        kit = re.search(r'(?i)(\d+)\s*[x×]\s*([\d.]+)\s*GB', group)
        count = quantity(group)
        if 'total ram' in group.lower() or 'gb total' in group.lower():
            total += gb
            layout_known = False
        elif kit:
            total += gb * count;modules += int(kit.group(1)) * count;unit_sizes.add(float(kit.group(2)))
        else:
            total += gb * count
            if re.search(r'(?i)\b(?:quantity|qty)\s*[:=]?\s*\d+', group):
                modules += count;unit_sizes.add(gb)
            else:
                layout_known = False
    result = {'kind':'RAM', 'total_gb':total}
    if modules and layout_known:
        result['modules'] = modules
    if len(unit_sizes) == 1 and layout_known:
        result['module_gb'] = next(iter(unit_sizes))
    return result

def normalize_ram(name):
    spec = ram_spec(name)
    if not spec.get('total_gb') or re.match(r'(?i)^[\d.]+ GB total', name):
        return name
    heading = f'{spec["total_gb"]:g} GB total'
    if spec.get('modules') and spec.get('module_gb'):
        heading += f' ({spec["modules"]} × {spec["module_gb"]:g} GB modules)'
    details = re.sub(r'(?i)\b(?:quantity|qty)\s*[:=]?\s*\d+|\b\d+\s*[x×]\s*\d+(?:\.\d+)?\s*GB|\b\d+(?:\.\d+)?\s*GB', '', name)
    details = re.sub(r'[\s,;()]+', ' ', details).strip()
    return heading + (' — ' + details if details else '')

def normalize_components(components):
    result = {};drive = 0
    for key, name in components.items():
        if key == 'RAM':
            result[key] = normalize_ram(name)
        elif kind_of(key) == 'Storage':
            for group in name.split(';'):
                if not group.strip():
                    continue
                count = quantity(group)
                label = re.sub(r'(?i),?\s*\b(?:quantity|qty)\s*[:=]?\s*\d+', '', group).strip()
                gb = capacity_gb(label)
                if gb:
                    size = f'{gb / 1000:g} TB' if gb >= 1000 else f'{gb:g} GB'
                    label = re.sub(r'(?i)\b\d+(?:\.\d+)?\s*(?:GiB|TiB)\s*detected', size, label)
                for _ in range(count if count <= 32 else 1):
                    drive += 1
                    result[f'Storage {drive}'] = label + f', quantity {1 if count <= 32 else count}'
        else:
            result[key] = name
    return result

def specifications(components):
    result = {}
    for key, name in components.items():
        kind = kind_of(key)
        if kind == 'RAM':
            result[key] = ram_spec(name)
        elif kind == 'Storage':
            result[key] = {'kind':kind, 'unit_gb':capacity_gb(name), 'quantity':quantity(name)}
        else:
            result[key] = {'kind':kind, 'quantity':quantity(name)}
    return result

def matches_capacity(key, requested, source):
    kind = kind_of(key)
    if kind not in ('RAM','Storage'):
        return True
    target = ram_spec(requested).get('total_gb') if kind == 'RAM' else capacity_gb(requested)
    if not target:
        return False
    # Only a particular listing with an explicit capacity can substantiate these parts.
    if not source.get('listing'):
        return False
    title = str(source.get('title', ''))
    offered = capacity_gb(title)
    if offered is None or abs(target - offered) / target > .035:
        return False
    if kind == 'RAM':
        wanted_type = re.search(r'(?i)\b(?:LP)?DDR[345]\b', requested)
        offered_type = re.search(r'(?i)\b(?:LP)?DDR[345]\b', title)
        if wanted_type and (not offered_type or offered_type.group().lower() != wanted_type.group().lower()):
            return False
    return True

def exact_model_match(requested, offered):
    """Conservative: same capacity alone does not establish the same model."""
    clean = re.sub(r'(?i)\b\d+(?:\.\d+)?\s*(?:GB|GiB|TB|MT/s|MHz)\b|\b(?:quantity|qty)\s*\d+|DDR[345]', ' ', requested)
    tokens = re.findall(r'(?i)\b[a-z0-9]+(?:-[a-z0-9]+)*\b', clean)
    identifiers = [t for t in tokens if (any(c.isdigit() for c in t) and any(c.isalpha() for c in t)) or (t.isdigit() and len(t) >= 3)]
    if not identifiers:
        return False
    offered_tokens = set(re.findall(r'(?i)\b[a-z0-9]+(?:-[a-z0-9]+)*\b', offered.lower()))
    if not all(token.lower() in offered_tokens for token in identifiers):
        return False
    for suffix in ('pro','evo','plus','max','xt','super','ti'):
        if (suffix in [t.lower() for t in tokens]) != (suffix in offered_tokens):
            return False
    return True
