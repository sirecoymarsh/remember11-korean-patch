from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 ap=argparse.ArgumentParser();ap.add_argument('catalog',type=Path);ap.add_argument('outdir',type=Path);ap.add_argument('--size',type=int,default=200);a=ap.parse_args();rows=[json.loads(x) for x in a.catalog.read_text(encoding='utf-8').splitlines() if x.strip()];rows=[x for x in rows if x['kind']=='translate'];a.outdir.mkdir(parents=True,exist_ok=True);manifest=[]
 for n,start in enumerate(range(0,len(rows),a.size)):
  subset=[]
  for r in rows[start:start+a.size]:subset.append({k:r[k] for k in ('key','source_jp','previous_jp','next_jp','controls','storage','max_source_bytes')})
  p=a.outdir/f'packet-{n:03d}.json';p.write_text(json.dumps({'packet':n,'count':len(subset),'items':subset},ensure_ascii=False,separators=(',',':')),encoding='utf-8');manifest.append({'packet':n,'count':len(subset),'first_key':subset[0]['key'],'last_key':subset[-1]['key']})
 (a.outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'packets':len(manifest),'translations':len(rows)},ensure_ascii=False))
if __name__=='__main__':main()
