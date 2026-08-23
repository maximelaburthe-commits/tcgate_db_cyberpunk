#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, hashlib, unicodedata
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
CONF=json.loads((ROOT/'source/source.json').read_text(encoding='utf-8'))
UA={'User-Agent':'TCGateCyberpunkDB/0.3 (+manual private-alpha sync)'}

def slugify(s):
    s=unicodedata.normalize('NFKD',s); s=''.join(c for c in s if not unicodedata.combining(c))
    s=s.lower().replace('—','-').replace('–','-').replace('’',"'")
    return re.sub(r'[^a-z0-9]+','-',s).strip('-')
def cid(name): return 'cp-'+slugify(name)
def pid(card_id,set_id,number): return 'cpp-'+hashlib.sha1(f'{card_id}|{set_id}:{number}'.encode()).hexdigest()[:16]
def map_num(source_num):
    prefix,num=source_num.split('-',1)
    return {'WNTC':'wtnc-retail','EP':'embracing-power-retail','HEIST':'the-heist-retail','PRM01':'set-1-promos'}.get(prefix,'unknown'),num

def get(url):
    r=requests.get(url,headers=UA,timeout=35,allow_redirects=True); r.raise_for_status(); return r

def official_health():
    src=CONF['sources'][0]; out={'source':src['id'],'url':src['url'],'ok':False}
    try:
        r=get(src['url']); out['http_status']=r.status_code; out['final_url']=r.url
        if urlparse(r.url).netloc!=urlparse(src['url']).netloc:
            out['status']='CROSS_DOMAIN_REDIRECT'; return out
        body=' '.join(BeautifulSoup(r.text,'html.parser').stripped_strings)
        m=re.search(r'Showing\s+\d+[–-]\d+\s+of\s+(\d+)\s+cards',body,re.I)
        out['reported_gallery_entries']=int(m.group(1)) if m else None
        out['status']='HEALTHY' if 'Card Database' in body else 'STRUCTURE_CHANGED'
        out['ok']=out['status']=='HEALTHY'; return out
    except Exception as e:
        out['status']='UNAVAILABLE'; out['error']=str(e); return out

def secondary_records():
    src=CONF['sources'][1]; data=get(src['url']).json(); rows=[]
    for x in data:
        number=x.get('number') or ''
        if not re.match(r'^(WNTC|EP|HEIST|PRM01)-',number): continue
        # Do not trust community data as authority: preserve its official URL and mark provenance.
        rows.append({k:x.get(k) for k in ['url','name','type','subtype','cost','power','ram','set','number','illustrated_by','eddie','image','color']})
    return rows

def main():
    ap=argparse.ArgumentParser(description='Stage Cyberpunk TCG DB changes; never writes GitHub or production files.')
    ap.add_argument('--output-dir',default=str(ROOT/'staging/latest'))
    args=ap.parse_args(); outdir=Path(args.output_dir); outdir.mkdir(parents=True,exist_ok=True)
    health=official_health()
    try: rows=secondary_records()
    except Exception as e:
        rows=[]; secondary_error=str(e)
    else: secondary_error=None
    current=json.loads((ROOT/'data/cards.json').read_text(encoding='utf-8'))['cards']
    current_nums={c.get('catalog_number') for c in current if c.get('catalog_number')}
    source_nums={x['number'] for x in rows}
    source_wntc={n for n in source_nums if n.startswith('WNTC-')}
    current_source_count=len([c for c in current if c.get('status') in ('source_synced_secondary','verified_official')])
    drop=(current_source_count-len(rows))/max(current_source_count,1)
    blocked=bool(rows and drop>CONF['safety']['block_large_record_drop_ratio'])
    report={
      'mode':'staging_only','official_health':health,'secondary_error':secondary_error,
      'secondary_records':len(rows),'secondary_wntc_records':len(source_wntc),
      'new_source_numbers':sorted(source_nums-current_nums),'source_numbers_missing_from_local':sorted(source_nums-current_nums),
      'local_numbers_not_in_secondary':sorted(current_nums-source_nums),
      'large_drop_ratio':drop,'blocked':blocked,
      'publish_allowed':False,
      'next_action':'Inspect staging; rebuild database package; manually publish to GitHub only after validation.'
    }
    (outdir/'sync_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (outdir/'secondary_snapshot.json').write_text(json.dumps({'records':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(4 if blocked else 0)
if __name__=='__main__': main()
