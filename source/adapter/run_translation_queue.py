from __future__ import annotations
import argparse,subprocess,sys,time
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--start',type=int,default=0);ap.add_argument('--end',type=int);a=ap.parse_args();root=a.root
 packets=sorted((root/'packets'/'scenario-200').glob('packet-*.json')); packets=packets[a.start:a.end]
 done=failed=0
 for i,p in enumerate(packets,1):
  out=root/'translations'/'scenario-packets'/p.name
  ok=out.with_suffix('.ok.json')
  if ok.exists(): print(f'SKIP {p.name}',flush=True);done+=1;continue
  print(f'RUN {p.name} ({i}/{len(packets)})',flush=True)
  r=subprocess.run([sys.executable,str(root/'adapter'/'translate_packet.py'),str(p),str(out),'--retries','2'])
  if r.returncode: failed+=1;print(f'FAIL {p.name}',flush=True)
  else:done+=1
 print(f'QUEUE COMPLETE done={done} failed={failed}',flush=True)
 raise SystemExit(1 if failed else 0)
if __name__=='__main__':main()
