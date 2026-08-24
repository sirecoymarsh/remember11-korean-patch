from __future__ import annotations
import json,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];outdir=root/'translations'/'image-ui-retry';outdir.mkdir(parents=True,exist_ok=True);(root/'logs'/'image-ui-retry').mkdir(parents=True,exist_ok=True)
for pp in sorted((root/'packets'/'image-ui-retry').glob('packet-*.json')):
 out=outdir/pp.name;files=json.loads(pp.read_text(encoding='utf-8'))['files'];names=[Path(x).name for x in files]
 prompt=('너는 Remember11 한국어판의 이미지 텍스트 번역자다. 첨부 이미지는 일본어판 원본 자산이다. 영어판 자료나 외부 검색은 사용하지 마라. '
 '일본어뿐 아니라 일본어판 원본 이미지에 원래 들어 있는 영어·독일어 등 로마자 표기도 고유 로고가 아닌 한 전부 한국어로 번역하라. 날짜 아래의 the 4th day 같은 작은 글씨, 지도·그래프·도면의 라벨도 빠뜨리지 마라. '
 '각 텍스트 블록 bbox를 원본 캔버스 픽셀 [left,top,right,bottom]로 기록한다. filename은 아래 이름을 정확히 쓰고 설명 없이 스키마 JSON만 출력하라.\n- '+'\n- '.join(names))
 cmd=[str(root/'tools'/'codex.exe'),'exec','--ephemeral','--skip-git-repo-check','-s','read-only','-C',str(root),'-c','model_reasoning_effort="medium"','--output-schema',str(root/'adapter'/'image-translation.schema.json'),'-o',str(out),'--image',*files,'-'];st=time.time();p=subprocess.run(cmd,input=prompt.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800);(root/'logs'/'image-ui-retry'/f'{pp.stem}.log').write_bytes(p.stdout);print(json.dumps({'packet':pp.name,'seconds':round(time.time()-st,1),'exit':p.returncode},ensure_ascii=False),flush=True)
 if p.returncode:raise SystemExit(1)
print('RETRY COMPLETE',flush=True)
