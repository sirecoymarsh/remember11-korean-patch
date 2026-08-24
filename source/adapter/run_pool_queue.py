from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,default=0);ap.add_argument('--end',type=int);a=ap.parse_args();root=Path(__file__).resolve().parents[1];packets=sorted((root/'packets'/'script-pool-200').glob('packet-*.json'))[a.start:a.end];done=failed=0
for n,p in enumerate(packets,1):
 out=root/'translations'/'script-pool'/p.name
 if out.with_suffix('.ok.json').exists():print('SKIP',p.name,flush=True);done+=1;continue
 print(f'RUN {p.name} {n}/{len(packets)}',flush=True);r=subprocess.run([sys.executable,str(root/'adapter'/'translate_pool_packet.py'),str(p),str(out),'--retries','2'])
 if r.returncode:failed+=1;print('FAIL',p.name,flush=True)
 else:done+=1
print(f'COMPLETE start={a.start} end={a.end} done={done} failed={failed}',flush=True);raise SystemExit(1 if failed else 0)
