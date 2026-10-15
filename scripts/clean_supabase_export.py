#!/usr/bin/env python3
"""
Clean a Supabase -> Tokens Studio export before it touches tokens/.

Input : one single-file Tokens Studio JSON (sets as top-level keys, plus $themes/$metadata)
Base  : the current tokens/ folder (source of truth for names, descriptions, set layout)
Output: tokens/** rewritten in the multi-file layout, plus a Markdown report

Rules
  1. tokens/ owns everything on a token except value and type: descriptions, $extensions
     (Figma scopes, Tokens Studio modifiers) and any other key. Exporter notes never land in a
     token description; they go to the report instead.
  2. A token that exists in tokens/ keeps its place. Its value may change; that is logged.
     Hex-case-only changes are ignored (base casing kept).
  3. A token that does NOT exist in tokens/ is quarantined into tokens/Supabase/<set>.json.
     Those sets are listed in $metadata (so they load) but added to no theme (so they never push).
  4. $themes is never changed by an import.
  5. Fail (exit 2) on: broken {references}, light/dark name mismatch in a color-mode set,
     or a value that is not a string/number/object.
"""
import argparse, glob, json, os, re, sys, datetime, collections

HEX = re.compile(r'^#[0-9a-fA-F]{3,8}$')
REF = re.compile(r'\{([^}]+)\}')

def load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def dump(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)  # no trailing newline, matches Tokens Studio output

def leaves(node, path=''):
    """Flatten a Tokens Studio set into {dotted.path: leaf}."""
    out = {}
    if isinstance(node, dict):
        if 'value' in node or '$value' in node:
            return {path: node}
        for k, v in node.items():
            out.update(leaves(v, f'{path}.{k}' if path else k))
    return out

def set_leaf(tree, path, leaf):
    parts = path.split('.'); cur = tree
    for p in parts[:-1]: cur = cur.setdefault(p, {})
    cur[parts[-1]] = leaf

def strings(v):
    if isinstance(v, str): yield v
    elif isinstance(v, dict):
        for x in v.values(): yield from strings(x)
    elif isinstance(v, list):
        for x in v: yield from strings(x)

def same_value(a, b):
    if isinstance(a, str) and isinstance(b, str) and HEX.match(a) and HEX.match(b):
        return a.lower() == b.lower()
    return a == b

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('export'); ap.add_argument('--tokens', default='tokens')
    ap.add_argument('--report', default=None); ap.add_argument('--quarantine', default='supabase')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    export = load(a.export)
    base = {}
    for f in glob.glob(os.path.join(a.tokens, '**', '*.json'), recursive=True):
        rel = os.path.relpath(f, a.tokens)[:-5].replace(os.sep, '/')
        if rel.startswith('$'): continue
        base[rel] = load(f)
    base_by_lower = {k.lower(): k for k in base}
    quarantine_prefix = a.quarantine + '/'

    rep = collections.defaultdict(list)
    out_sets = {}          # set name (base casing) -> tree
    quarantine = {}        # Supabase/<set> -> tree
    all_names = set()

    for set_name, tree in export.items():
        if set_name.startswith('$'): continue
        if set_name.lower().startswith(quarantine_prefix.lower()):
            rep['error'].append(f'export already contains a `{a.quarantine}/` set: {set_name}'); continue
        base_name = base_by_lower.get(set_name.lower())
        if not base_name:
            rep['new_sets'].append(set_name)
            quarantine[f'{a.quarantine}/{set_name}'] = tree
            all_names |= set(leaves(tree)); continue
        B = leaves(base[base_name]); E = leaves(tree)
        out = {}
        for path, b in B.items():
            if path not in E:
                rep['missing'].append((base_name, path, json.dumps(b.get('value', b.get('$value')))))
                set_leaf(out, path, b); continue
            e = E[path]
            # rule 1: tokens/ owns everything except value and type (description, $extensions,
            # Figma scopes, legacy nested keys). The export only ever contributes value + type.
            leaf = dict(b)
            if 'type' in e: leaf['type'] = e['type']
            note = e.get('description')
            if note and note != b.get('description'):
                rep['notes'].append((base_name, path, note))
            # rule 2: value changes logged; hex-case-only ignored
            bv, ev = b.get('value', b.get('$value')), e.get('value', e.get('$value'))
            if not same_value(bv, ev):
                leaf['value'] = ev
                rep['value_changes'].append((base_name, path, json.dumps(bv), json.dumps(ev)))
            dropped = sorted(k for k in b if k not in e and k not in ('value', '$value', 'description'))
            if dropped: rep['kept_meta'].append((base_name, path, ', '.join(dropped)))
            if b.get('type') != e.get('type'):
                rep['type_changes'].append((base_name, path, b.get('type'), e.get('type')))
            set_leaf(out, path, leaf)
        for path, e in E.items():
            if path in B: continue
            q = dict(e); note = q.pop('description', None)
            rep['quarantined'].append((base_name, path, json.dumps(e.get('value')), note or ''))
            set_leaf(quarantine.setdefault(f'{a.quarantine}/{base_name}', {}), path, q)
        out_sets[base_name] = out
        all_names |= set(B) | set(E)

    for base_name in base:
        if base_name not in out_sets and not base_name.lower().startswith(quarantine_prefix.lower()):
            rep['untouched_sets'].append(base_name); out_sets[base_name] = base[base_name]

    # rule 5: validation
    for name, tree in list(out_sets.items()) + list(quarantine.items()):
        for path, leaf in leaves(tree).items():
            v = leaf.get('value', leaf.get('$value'))
            if not isinstance(v, (str, int, float, dict, list)):
                rep['error'].append(f'{name}:{path} value is {type(v).__name__}')
            for s in strings(v):
                for r in REF.findall(s):
                    if r not in all_names: rep['error'].append(f'{name}:{path} references missing token {{{r}}}')
    for light in [s for s in out_sets if s.lower().endswith('color-mode/light')]:
        dark = light[:-5] + 'dark'
        if dark in out_sets:
            L, D = set(leaves(out_sets[light])), set(leaves(out_sets[dark]))
            BL, BD = set(leaves(base[light])), set(leaves(base[dark]))
            pre = BL ^ BD
            for p in sorted(L - D): rep['parity_pre' if p in pre else 'parity'].append((light, p, 'light only'))
            for p in sorted(D - L): rep['parity_pre' if p in pre else 'parity'].append((dark, p, 'dark only'))
    for light in [s for s in quarantine if s.lower().endswith('color-mode/light')]:
        dark = light[:-5] + 'dark'
        L = set(leaves(quarantine[light])); D = set(leaves(quarantine.get(dark, {})))
        for p in sorted(L ^ D): rep['parity_q'].append((light if p in L else dark, p, 'quarantine, one mode only'))

    # $metadata: base order + quarantine sets; $themes untouched
    meta_path = os.path.join(a.tokens, '$metadata.json')
    meta = load(meta_path) if os.path.exists(meta_path) else {'tokenSetOrder': []}
    order = [s for s in meta.get('tokenSetOrder', []) if not s.lower().startswith(quarantine_prefix.lower())]
    order += sorted(quarantine)
    themes_path = os.path.join(a.tokens, '$themes.json')
    if 'themes' in export and export.get('$themes') != (load(themes_path) if os.path.exists(themes_path) else None):
        rep['notes'].append(('$themes', '', 'export $themes differs from tokens/$themes.json; repo version kept'))

    # report
    today = datetime.date.today().isoformat()
    lines = [f'# Supabase import report · {today}', '',
             f'Source: `{os.path.basename(a.export)}`', '']
    def section(title, rows, header):
        lines.append(f'## {title} ({len(rows)})'); lines.append('')
        if not rows: lines.append('None.'); lines.append(''); return
        lines.append('| ' + ' | '.join(header) + ' |'); lines.append('|' + '---|' * len(header))
        for r in rows: lines.append('| ' + ' | '.join(str(x).replace('|', '\\|') for x in r) + ' |')
        lines.append('')
    section('Blocking errors', [(e,) for e in rep['error']], ['error'])
    section('Value changes to existing tokens', rep['value_changes'], ['set', 'token', 'before', 'after'])
    section('Type changes to existing tokens', rep['type_changes'], ['set', 'token', 'before', 'after'])
    section('Light/dark parity problems introduced by this import', rep['parity'], ['set', 'token', 'issue'])
    section('Light/dark parity problems already in tokens/ (not blocking)', rep['parity_pre'], ['set', 'token', 'issue'])
    section('Quarantined tokens present in one mode only (not blocking, never pushed)', rep['parity_q'], ['set', 'token', 'issue'])
    section(f'Quarantined to `{a.quarantine}/` (not in tokens/, not in any theme)', rep['quarantined'], ['set', 'token', 'value', 'exporter note'])
    section('Tokens in tokens/ missing from export (kept as-is)', rep['missing'], ['set', 'token', 'value'])
    section('Exporter notes stripped from descriptions', rep['notes'], ['set', 'token', 'note'])
    section('Metadata the export dropped but tokens/ kept', rep['kept_meta'], ['set', 'token', 'keys kept'])
    section('Export sets with no counterpart in tokens/ (quarantined whole)', [(s,) for s in rep['new_sets']], ['set'])
    section('Sets not present in export (unchanged)', [(s,) for s in rep['untouched_sets']], ['set'])
    report = '\n'.join(lines)
    report_path = a.report or os.path.join('reports', f'supabase-import-{today}.md')

    if a.dry_run:
        print(report); sys.exit(2 if rep['error'] or rep['parity'] else 0)

    for name, tree in out_sets.items(): dump(os.path.join(a.tokens, name + '.json'), tree)
    # drop stale quarantine files, write fresh ones
    for f in glob.glob(os.path.join(a.tokens, a.quarantine, '**', '*.json'), recursive=True): os.remove(f)
    for name, tree in quarantine.items(): dump(os.path.join(a.tokens, name + '.json'), tree)
    meta['tokenSetOrder'] = order; dump(meta_path, meta)
    dump_text = report_path
    os.makedirs(os.path.dirname(dump_text) or '.', exist_ok=True)
    with open(dump_text, 'w', encoding='utf-8') as f: f.write(report + '\n')
    print(report)
    print(f'\nwrote {len(out_sets)} sets, {len(quarantine)} quarantine sets, report {report_path}')
    sys.exit(2 if rep['error'] or rep['parity'] else 0)

if __name__ == '__main__':
    main()
