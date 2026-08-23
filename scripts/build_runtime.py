#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def dump(p,o): (ROOT/p).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
cards=load('data/cards.json')['cards']; prints=load('data/printings.json')['printings']
runtime=[{k:c.get(k) for k in ['id','name','type','color','tags','cost','power','ram','catalog_number','primary_printing_key','source_url']} for c in cards if c.get('runtime_ready') and c.get('name')]
names={c['id']:c.get('name') for c in cards}
vision=[]
for p in prints:
    if not p.get('recognition',{}).get('enabled') or not names.get(p['card_id']): continue
    vision.append({'printing_id':p['id'],'card_id':p['card_id'],'name':names[p['card_id']],'set_id':p['set_id'],'number':p['number'],'variant_kind':p.get('variant_kind'),'printing_uuid':p.get('printing_uuid'),'image_url':(p.get('image') or {}).get('remote_url'),'local_path':(p.get('image') or {}).get('local_path'),'image_source':(p.get('image') or {}).get('source')})
dump('runtime/cards.min.json',runtime); dump('runtime/vision-index.json',vision)
print(json.dumps({'runtime_cards':len(runtime),'vision_entries':len(vision)},indent=2))
