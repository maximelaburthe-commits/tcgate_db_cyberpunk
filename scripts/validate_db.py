#!/usr/bin/env python3
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
errors=[]
cards=load('data/cards.json')['cards']; prints=load('data/printings.json')['printings']; sets=load('sets.json')['sets']
ids=[c['id'] for c in cards]; pids=[p['id'] for p in prints]; setids={s['id'] for s in sets}
if len(ids)!=len(set(ids)): errors.append('duplicate card ids')
if len(pids)!=len(set(pids)): errors.append('duplicate printing ids')
cardids=set(ids)
for p in prints:
    if p['card_id'] not in cardids: errors.append(f"orphan printing {p['id']}")
    if p['set_id'] not in setids: errors.append(f"unknown set {p['set_id']} in {p['id']}")
    if p.get('recognition',{}).get('enabled') and not ((p.get('image') or {}).get('remote_url') or (p.get('image') or {}).get('local_path')):
        errors.append(f"vision enabled without image {p['id']}")
for c in cards:
    if c.get('runtime_ready') and not c.get('name'): errors.append(f"runtime card missing name {c['id']}")
coverage=load('data/coverage.json')
wntc=[c for c in cards if (c.get('catalog_number') or '').startswith('WNTC-')]
if len(wntc)!=coverage['wntc']['records_in_cards_json']: errors.append('coverage WNTC count mismatch')
if len(wntc)!=coverage['wntc']['revealed_slots_tracked']: errors.append('revealed WNTC slot count mismatch')
print(json.dumps({'ok':not errors,'cards':len(cards),'printings':len(prints),'wntc_records':len(wntc),'errors':errors},ensure_ascii=False,indent=2))
sys.exit(1 if errors else 0)
