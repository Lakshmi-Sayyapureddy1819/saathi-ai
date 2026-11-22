"""Re-measure Claude Code usage for this project from its local session logs.

Counts each message.id once (its last log record), excludes `<synthetic>` placeholders, and prices the four disjoint
token fields at the claude-sonnet-5-5 list rates used in AI_USAGE.md section 5 (input $2, output $10, cache write
$2.50, cache read $0.10 per 1M tokens). The result is an API-equivalent estimate, not a bill.

Usage:  python scripts/measure_claude_usage.py
"""
import json, glob, os

base = os.path.expanduser('~/.claude/projects')
files = [f for d in glob.glob(base + '/*saathi-ai*') for f in glob.glob(d + '/*.jsonl')]
tot = {'calls': 0, 'i': 0, 'o': 0, 'cw': 0, 'cr': 0}
rows = []
for f in files:
    last = {}
    with open(f, encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('type') != 'assistant':
                continue
            m = r.get('message', {})
            u = m.get('usage')
            if not u or not m.get('id') or m.get('model') == '<synthetic>':
                continue
            last[m['id']] = (r.get('timestamp'), u)
    if not last:
        continue
    ts = sorted(v[0] for v in last.values())
    s = {'calls': len(last), 'i': 0, 'o': 0, 'cw': 0, 'cr': 0}
    for _, u in last.values():
        s['i'] += u.get('input_tokens', 0)
        s['o'] += u.get('output_tokens', 0)
        s['cw'] += u.get('cache_creation_input_tokens', 0)
        s['cr'] += u.get('cache_read_input_tokens', 0)
    cost = (s['i'] * 2 + s['o'] * 10 + s['cw'] * 2.5 + s['cr'] * 0.1) / 1e6
    rows.append((ts[0], os.path.basename(f)[:8], ts[-1], s, round(cost, 2)))
    for k in tot:
        tot[k] += s[k]
for r in sorted(rows):
    print(r[1], r[0][:16], r[2][:16], r[3]['calls'], r[4])
print(tot)
print('input', round(tot['i'] * 2 / 1e6, 2), 'output', round(tot['o'] * 10 / 1e6, 2),
      'cache_write', round(tot['cw'] * 2.5 / 1e6, 2), 'cache_read', round(tot['cr'] * 0.1 / 1e6, 2),
      'TOTAL', round((tot['i'] * 2 + tot['o'] * 10 + tot['cw'] * 2.5 + tot['cr'] * 0.1) / 1e6, 2))
