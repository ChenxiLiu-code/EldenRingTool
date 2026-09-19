"""Compare save snapshots and derive only affected UI domains off the UI thread."""
from .catalog import resolve
from .quest_engine import evaluate_document
from .save_reader import EF_LEN


def public_characters(characters):
    return [{k: v for k, v in c.items() if not k.startswith('_') and k != 'mapPixel'} for c in characters]


def flag_bytes(character):
    flags = character.get('_flags')
    return None if flags is None else flags.pay[flags.offset:flags.offset + EF_LEN]


def prepare_update(parsed, path, context):
    characters = parsed.get('characters', [])
    remembered = context['store'].data['slots'].get(path)
    slots = {c.get('slot') for c in characters}
    slot = remembered if remembered in slots else context['slot']
    if slot not in slots:
        slot = characters[0]['slot'] if characters else None
    c = next((c for c in characters if c.get('slot') == slot), {})
    old = next((c for c in context['characters'] if c.get('slot') == context['slot']), {})
    identity = (path, slot, c.get('name')) != (context['path'], context['slot'], old.get('name'))
    flags_changed = context.get('force', False) or identity or c.get('ok') != old.get('ok') or flag_bytes(c) != flag_bytes(old)
    inventory_changed = flags_changed or c.get('_inventoryRaw') != old.get('_inventoryRaw') or c.get('_gestureIds') != old.get('_gestureIds')
    found = context['found']
    collection = context['collection']
    quests = context['quests']
    if flags_changed:
        flags = c.get('_flags')
        found = {str(m['id']) for m in context['markers']
                 if c.get('ok') and flags and any(flags.get(f) is True for f in (m.get('flags') or ([m['flag']] if m.get('flag') else [])))}
        quests = evaluate_document(context['quest_doc'], c, found,
                                   lambda q, s: context['store'].quest_done(path, c, q, s))
    if inventory_changed:
        collection = resolve(context['index'], c.get('_inventoryRaw'), c.get('_gestureIds', [])) if c.get('ok') else {'owned': {}}
        flags = c.get('_flags')
        if c.get('ok'):
            for row in context['catalog'].get('items', []):
                if row.get('category') != 'world_maps':
                    continue
                acquired = flags and any(flags.get(int(f)) is True for f in row.get('acquisitionFlags', []) if f)
                if acquired or any(str(src.get('marker')) in found for src in row.get('sources', [])):
                    collection['owned'].setdefault(row['key'], {'quantity': 1, 'held': 0, 'storage': 0})
        collection['distinct'] = len(collection['owned'])
    if c.get('position'):
        c['mapPixel'] = context['projector'].project(c['position'])
    return {'characters': characters, 'slot': slot, 'found': found, 'collection': collection, 'quests': quests,
            'generation': context['generation'], 'identity': identity,
            'map_changed': identity or found != context['found'],
            'catalog_changed': identity or collection != context['collection'],
            'quests_changed': identity or quests != context['quests'],
            'character_changed': identity or public_characters(characters) != public_characters(context['characters'])
                                 or found != context['found'] or collection != context['collection'] or quests != context['quests']}
