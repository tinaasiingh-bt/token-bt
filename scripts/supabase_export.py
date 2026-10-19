#!/usr/bin/env python3
"""
Generate the Tokens Studio export from the Supabase design-token tables.

Input : SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY (env, read-only), rules/supabase-export-rules.json,
        and this repo's tokens/ (for set order, token types, $themes and key order only)
Output: <out>/tokens/**.json in the multi-file layout + <out>/supabase-export-notes.md,
        ready for scripts/clean_supabase_export.py

The generator reads ONLY Supabase plus the rules file for values. tokens/ is consulted so
the output keeps this repo's set layout, token types and key order (small review diffs).
Stdlib only.
"""
import argparse, collections, datetime, io, json, os, re, sys, urllib.request

OD = collections.OrderedDict
PROP = {'font-family': 'fontFamily', 'font-weight': 'fontWeight', 'line-height': 'lineHeight',
        'font-size': 'fontSize', 'text-decoration': 'textDecoration'}
SHADOW_ORDER = ['x offset', 'y offset', 'blur', 'spread', 'color']


def J(v):
    return json.dumps(v, sort_keys=True).lower()


# ---------------- Supabase ----------------
def fetch(url, key, table):
    out, off = [], 0
    while True:
        req = urllib.request.Request('%s/rest/v1/%s?select=*&limit=1000&offset=%d' % (url.rstrip('/'), table, off),
                                     headers={'apikey': key, 'Authorization': 'Bearer ' + key})
        chunk = json.load(urllib.request.urlopen(req))
        out += chunk
        if len(chunk) < 1000:
            return out
        off += 1000


TABLES = ['themes', 'design_token_categories', 'design_tokens_primitive', 'design_tokens_semantic',
          'design_tokens_component', 'design_tokens_semantic_primitives', 'design_token_families',
          'design_token_family_tokens', 'properties']


def load_supabase(url, key, fixture=None):
    if fixture:   # offline: one <table>.json per table, as returned by the REST API
        T = {t: json.load(io.open(os.path.join(fixture, t + '.json'), encoding='utf-8')) for t in TABLES}
    else:
        T = {t: fetch(url, key, t) for t in TABLES}
    idx = lambda t: {r['id']: r for r in T[t]}
    th, cat, prim, fam, prop = idx('themes'), idx('design_token_categories'), idx('design_tokens_primitive'), \
        idx('design_token_families'), idx('properties')
    sem = idx('design_tokens_semantic')
    nm = lambda d, k: (d.get(k) or {}).get('name', '') if k is not None else ''
    pval = {r['name']: (r['value'] or '') for r in T['design_tokens_primitive']}

    rows = []
    for r in sorted(T['design_tokens_primitive'], key=lambda r: r['name']):
        rows.append(dict(table='primitive', name=r['name'], theme='', ref='', cat='', family='', value=r['value'] or ''))
    for r in sorted(T['design_tokens_semantic'], key=lambda r: (r['name'], nm(th, r['theme']))):
        pt = nm(prim, r['primitive_token'])
        rows.append(dict(table='semantic', name=r['name'], theme=nm(th, r['theme']), ref=pt, cat=nm(cat, r['category']),
                         family=nm(fam, r.get('family')), value=pval.get(pt, '')))
    for r in sorted(T['design_tokens_component'], key=lambda r: (r['name'], nm(th, r['theme']))):
        pt = nm(prim, r['primitive_token'])
        rows.append(dict(table='component', name=r['name'], theme=nm(th, r['theme']), ref=pt, cat=nm(cat, r['category']),
                         family='', value=pval.get(pt, '')))

    sparts = collections.defaultdict(dict)
    for d in T['design_tokens_semantic_primitives']:
        s = sem.get(d['semantic_token'])
        if s:
            sparts[(s['name'], nm(th, s['theme']))][d['role']] = nm(prim, d['primitive_token'])
    for r in rows:
        if not r['value'] and (r['name'], r['theme']) in sparts:
            pp = sparts[(r['name'], r['theme'])]
            r['value'] = ' '.join(pval.get(pp.get(k, ''), '?') for k in SHADOW_ORDER)
            r['ref'] = ' '.join(pp.get(k, '?') for k in SHADOW_ORDER)

    fams = collections.defaultdict(dict)
    for t in T['design_token_family_tokens']:
        fams[nm(fam, t['family'])][nm(prop, t['property'])] = nm(sem, t['design_token_semantic'])
    return rows, sparts, fams


# ---------------- this repo (layout only) ----------------
def leaves(d, pre=''):
    for k, v in d.items():
        if not isinstance(v, dict):
            continue
        p = pre + '.' + k if pre else k
        if 'value' in v:
            yield p, v
            yield from leaves(OD((c, cv) for c, cv in v.items() if isinstance(cv, dict) and 'value' in cv), p)
        else:
            yield from leaves(v, p)


def load_repo(tokens_dir):
    meta = json.load(io.open(os.path.join(tokens_dir, '$metadata.json'), encoding='utf-8'))
    order = [s for s in meta['tokenSetOrder'] if not s.lower().startswith('supabase/')]
    sets = OD()
    for rel in order:
        p = os.path.join(tokens_dir, *rel.split('/')) + '.json'
        sets[rel] = json.load(io.open(p, encoding='utf-8'), object_pairs_hook=OD) if os.path.exists(p) else OD()
    her_type = {p: v.get('type') for rel in order for p, v in leaves(sets[rel])}
    themes = json.load(io.open(os.path.join(tokens_dir, '$themes.json'), encoding='utf-8'), object_pairs_hook=OD)
    return order, sets, her_type, themes


# ---------------- value formatting ----------------
def is_line_height(name):
    return ('line-height' in name and not name.endswith('-line-height')) or name.startswith(('line-height-', 'text-line-height-'))


def ratio(v):
    v = str(v or '').strip()
    m = re.fullmatch(r'calc\(\s*([\d.]+)\s*(rem|px)?\s*/\s*([\d.]+)\s*(rem|px)?\s*\)', v)
    if not m:
        return None
    r = float(m.group(1)) / float(m.group(3))
    s = '%.4g' % r
    return s.rstrip('0').rstrip('.') if '.' in s else s


def guess_type(r, her_type, mapped_path=None):
    n = r['name']
    if mapped_path and her_type.get(mapped_path):
        return her_type[mapped_path]
    if 'radius' in n: return 'borderRadius'
    if 'line-height' in n: return 'lineHeights'
    if 'font-size' in n or 'text-size' in n: return 'fontSizes'
    if 'weight' in n: return 'fontWeights'
    if 'family' in n: return 'fontFamilies'
    if 'decoration' in n: return 'textDecoration'
    if n.startswith(('blur-', 'spread-', 'x-', 'y-')): return 'dimension'
    if r['cat'] == 'color' or r['theme'] or str(r['value']).startswith(('#', 'rgb')): return 'color'
    if 'border' in (r['cat'] or '') or n.startswith('border-width'): return 'borderWidth'
    return {'spacing': 'spacing', 'size': 'sizing', 'opacity': 'opacity', 'shadow': 'boxShadow'}.get(r['cat'], 'other')


# ---------------- generator ----------------
def generate(rules, rows, sparts, fams, order, her_type, themes):
    prim_rows = {r['name']: r for r in rows if r['table'] == 'primitive'}
    sem_rows = {(r['name'], r['theme']): r for r in rows if r['table'] == 'semantic'}
    comp_rows = {(r['name'], r['theme']): r for r in rows if r['table'] == 'component'}
    nm = {(e['table'], e['supabase'], e.get('theme', '')): (e['set'], e['path']) for e in rules['name_map']}
    suppress = [re.compile(x) for x in rules.get('suppress', [])]
    prim_path = {n: p for (t, n, th), (s, p) in nm.items() if t == 'primitive'}
    sem_path = {n: p for (t, n, th), (s, p) in nm.items() if t == 'semantic'}

    def prim_ref_path(prim):
        if prim in prim_path: return prim_path[prim]
        return prim if prim in prim_rows else None

    def ref(prim):
        p = prim_ref_path(prim)
        return '{%s}' % p if p else str(prim)

    def fmt_prim(name, v):
        v = str(v).strip()
        if name.startswith('opacity-'):
            try: return '%g%%' % (float(v) * 100)
            except ValueError: return v
        if name.startswith('font-family-'): return v.split(',')[0].strip().strip('\'"')
        if is_line_height(name): return ratio(v) or v
        if v == 'transparent': return 'rgba(0,0,0,0)'
        if v == '0' and name.startswith(('border-', 'size-', 'spacing-', 'blur-', 'spread-', 'x-', 'y-')): return '0px'
        if name.startswith('border-style-'): return OD([('style', v), ('width', '{%s}' % prim_ref_path('border-width-xs'))])
        return v

    def value_for(r):
        n = r['name']
        if r['table'] == 'primitive': return fmt_prim(n, r['value'])
        if r['cat'] == 'shadow' and (n, r['theme']) in sparts:
            pp = sparts[(n, r['theme'])]
            return OD([('x', ref(pp['x offset'])), ('y', ref(pp['y offset'])), ('blur', ref(pp['blur'])),
                       ('spread', ref(pp['spread'])), ('color', ref(pp['color'])), ('type', 'dropShadow')])
        return ref(r['ref']) if r['ref'] else str(r['value'])

    out = OD((rel, OD()) for rel in order)

    def put(st, path, node):
        d = out.setdefault(st, OD()); parts = path.split('.')
        for k in parts[:-1]:
            nxt = d.get(k)
            if nxt is None: nxt = d[k] = OD()
            d = nxt
        if parts[-1] in d and 'value' in d[parts[-1]]: return False
        if isinstance(d.get(parts[-1]), dict):
            for ck, cv in d[parts[-1]].items(): node[ck] = cv
        d[parts[-1]] = node
        return True

    log = collections.defaultdict(list); seen = set(); elev_seen = {}
    elev_themed_vals = collections.defaultdict(dict)
    for r in rows:
        if r['cat'] == 'shadow' and r['theme']: elev_themed_vals[(r['table'], r['name'])][r['theme']] = value_for(r)
    for r in rows:
        key = (r['table'], r['name'], r['theme'])
        if key in seen: continue
        seen.add(key)
        if any(s.match(r['name']) for s in suppress): log['suppressed'].append(r['name']); continue
        val = value_for(r)
        if r['cat'] == 'shadow' and key not in nm:
            ek = (r['table'], r['name'])
            themed_differs = r['theme'] and ek in elev_themed_vals and len({J(v) for v in elev_themed_vals[ek].values()}) > 1
            if not themed_differs:
                if ek in elev_seen: continue
                elev_seen[ek] = val
                key = (r['table'], r['name'], '')
        elif r['cat'] == 'shadow':
            if (r['table'], r['name']) in elev_seen and not r['theme']: continue
            elev_seen[(r['table'], r['name'])] = val
        st, p = nm.get(key) or nm.get((r['table'], r['name'], '')) or (None, None)
        node = OD([('value', val), ('type', guess_type(r, her_type, p))])
        if st is None:
            st, p = 'supabase-only/' + r['table'], (r['name'] + ('.' + r['theme'] if r['theme'] else ''))
            log['supabase-only'].append((st, p, r['name']))
        if not put(st, p, node):
            put('supabase-only/' + r['table'], r['name'] + ('.' + r['theme'] if r['theme'] else ''), node)
            log['collision'].append((st, p, r['name']))
        log['emitted'].append(r['name'])

    fam_map = {e['family']: (e['set'], e['path'], e.get('textCase'), e.get('textDecoration')) for e in rules.get('families', [])}
    for f, props in fams.items():
        comp = OD()
        for prop, tok in props.items():
            if prop in PROP: comp[PROP[prop]] = '{%s}' % sem_path[tok] if tok in sem_path else tok
        st, p, tc, td = fam_map.get(f, (None, None, None, None))
        if tc: comp['textCase'] = tc
        if td and 'textDecoration' not in comp: comp['textDecoration'] = td
        node = OD([('value', comp), ('type', 'typography')])
        if st is None:
            st, p = 'supabase-only/semantic', 'family.' + f.replace('-', '.')
            log['supabase-only'].append((st, p, 'family ' + f))
        put(st, p, node); log['typography'].append(f)

    for a in rules.get('aliases', []):
        src = (prim_rows.get(a['from']) if a['from_table'] == 'primitive' else
               comp_rows.get((a['from'], a.get('from_theme', ''))) if a['from_table'] == 'component' else
               sem_rows.get((a['from'], a.get('from_theme', ''))))
        if src is None: log['alias source missing'].append(a['path']); continue
        v = value_for(src)
        if a.get('mode') == 'ref-semantic': v = '{%s}' % sem_path[a['from']]
        node = OD([('value', v), ('type', a['type'])])
        if not put(a['set'], a['path'], node): log['alias collision'].append(a['path'])
        else: log['alias'].append(a['path'])

    for e in rules.get('figma_only', []):
        node = OD([('value', e['value']), ('type', e['type'])])
        if not put(e['set'], e['path'], node): log['figma-only collision'].append(e['path'])
        else: log['figma-only'].append(e['path'])

    for o in rules.get('value_overrides', []):
        if o['keep'] != 'figma': continue
        d = out.get(o['set'], {})
        for k in o['path'].split('.')[:-1]: d = d.get(k, {})
        leaf = d.get(o['path'].split('.')[-1])
        if leaf is None: log['override target missing'].append(o['path']); continue
        if J(leaf['value']) == J(o['supabase']):
            leaf['value'] = o['figma']; log['override applied'].append(o['path'])
        elif J(leaf['value']) == J(o['figma']): log['override expired (Supabase now matches)'].append(o['path'])
        else: log['override stale (Supabase changed)'].append(o['path'])

    def leaf_at(st, path):
        d = out.get(st)
        for k in path.split('.'):
            if not isinstance(d, dict): return None
            d = d.get(k)
        return d if isinstance(d, dict) and 'value' in d else None

    for e in rules.get('descriptions', []):
        leaf = leaf_at(e['set'], e['path'])
        if leaf is not None: leaf['description'] = e['description']; log['description'].append(e['path'])
        else: log['description target missing'].append(e['path'])
    for e in rules.get('extensions', []):
        leaf = leaf_at(e['set'], e['path'])
        if leaf is not None: leaf['$extensions'] = e['extensions']; log['extensions'].append(e['path'])
        else: log['extensions target missing'].append(e['path'])

    out['$themes'] = themes
    out['$metadata'] = {'tokenSetOrder': order + [s for s in out if s.startswith('supabase-only/') and out[s]]}
    return out, log


# ---------------- output ----------------
def reorder(gen, ref):
    """Keep this repo's key order inside each set so the review diff shows only real changes."""
    if not isinstance(gen, dict) or not isinstance(ref, dict): return gen
    if 'value' in gen:
        if isinstance(gen['value'], dict) and isinstance(ref.get('value'), dict):
            gen['value'] = OD([(k, gen['value'][k]) for k in ref['value'] if k in gen['value']] +
                              [(k, v) for k, v in gen['value'].items() if k not in ref['value']])
        for k in ref:
            if k in gen and isinstance(gen[k], dict) and 'value' in gen[k]: gen[k] = reorder(gen[k], ref[k])
        return gen
    o = OD()
    for k in ref:
        if k in gen: o[k] = reorder(gen[k], ref[k])
    for k in gen:
        if k not in o: o[k] = gen[k]
    return o


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(json.dumps(obj, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rules', default='rules/supabase-export-rules.json')
    ap.add_argument('--tokens', default='tokens')
    ap.add_argument('--out', default='incoming/supabase')
    ap.add_argument('--source', default=os.environ.get('SUPABASE_SOURCE', 'staging'), help='label for the notes file')
    ap.add_argument('--fixture', help='offline: directory of <table>.json dumps instead of Supabase')
    a = ap.parse_args()
    url, key = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_PUBLISHABLE_KEY')
    if not a.fixture and not (url and key):
        sys.exit('SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set (read-only; the token tables grant SELECT to anon)')

    rules = json.load(io.open(a.rules, encoding='utf-8'), object_pairs_hook=OD)
    rows, sparts, fams = load_supabase(url, key, a.fixture)
    order, sets, her_type, themes = load_repo(a.tokens)
    out, log = generate(rules, rows, sparts, fams, order, her_type, themes)

    for s in order:
        out[s] = reorder(out[s], sets[s])
        for p, v in leaves(out[s]):
            head = [k for k in ('value', 'type', 'description', '$extensions') if k in v]
            for k in head + [k for k in list(v) if k not in head]: v[k] = v.pop(k)

    for s in list(out):   # supabase-only sets have no reference layout: sort for a stable diff
        if s.startswith('supabase-only/'): out[s] = OD(sorted(out[s].items()))

    tok = os.path.join(a.out, 'tokens')
    if os.path.isdir(tok):
        for root, _, fs in os.walk(tok):
            for f in fs: os.remove(os.path.join(root, f))
    for s in out['$metadata']['tokenSetOrder']: dump(os.path.join(tok, *s.split('/')) + '.json', out[s])
    dump(os.path.join(tok, '$metadata.json'), out['$metadata'])
    dump(os.path.join(tok, '$themes.json'), out['$themes'])

    sb_only = log.get('supabase-only', [])
    n = io.open(os.path.join(a.out, 'supabase-export-notes.md'), 'w', encoding='utf-8', newline='\n')
    n.write('# Supabase -> Tokens Studio export (%s, %s)\n\n' % (a.source, datetime.date.today()))
    n.write('Generated by `scripts/supabase_export.py` from the Supabase %s token tables and `%s`. '
            '%d tokens emitted into %d sets; %d typography composites.\n\n' % (a.source, a.rules, len(log['emitted']), len(order), len(log['typography'])))
    n.write('## Figma values kept while Supabase differs (%d)\n\n' % len(log.get('override applied', [])))
    for o in rules.get('value_overrides', []):
        if o['keep'] == 'figma' and o['path'] in log.get('override applied', []): n.write('- `%s`: %s\n' % (o['path'], o['reason']))
    for k in ('override expired (Supabase now matches)', 'override stale (Supabase changed)', 'alias source missing',
              'override target missing', 'collision', 'alias collision', 'figma-only collision'):
        if log.get(k):
            n.write('\n## %s (%d)\n\n' % (k, len(log[k])))
            for x in log[k]: n.write('- `%s`\n' % (x if isinstance(x, str) else ' / '.join(map(str, x))))
    n.write('\n## Figma paths served from an existing Supabase token (%d)\n\n' % len(rules.get('aliases', [])))
    for al in rules.get('aliases', []): n.write('- `%s` <- `%s`\n' % (al['path'], al['from']))
    n.write('\n## Figma-only tokens with no Supabase source (%d; emitted verbatim)\n\n' % len(rules.get('figma_only', [])))
    for e in rules.get('figma_only', []): n.write('- `%s` / `%s`\n' % (e['set'], e['path']))
    n.write('\n## Supabase-only tokens (%d) - `supabase-only/*` sets, in no theme\n\n' % len(sb_only))
    for st, p, _ in sb_only: n.write('- `%s` / `%s`\n' % (st, p))
    n.write('\n## Suppressed (%d)\n' % len(log.get('suppressed', [])))
    n.close()
    print({k: len(v) for k, v in log.items()})


if __name__ == '__main__':
    main()
