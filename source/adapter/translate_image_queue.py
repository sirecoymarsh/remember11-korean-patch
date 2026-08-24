from __future__ import annotations
import json,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];outdir=root/'translations'/'image-ui';outdir.mkdir(parents=True,exist_ok=True);(root/'logs'/'image-ui').mkdir(parents=True,exist_ok=True)
for packet_path in sorted((root/'packets'/'image-ui').glob('packet-*.json')):
 out=outdir/packet_path.name
 if out.exists():print('SKIP',packet_path.name,flush=True);continue
 files=json.loads(packet_path.read_text(encoding='utf-8'))['files'];names=[Path(x).name for x in files]
 prompt=('너는 Remember11 한국어판의 이미지 UI 번역자다. 첨부된 이미지는 입력 목록과 같은 순서의 일본어 원본 캔버스다. 영어판이나 외부 자료는 사용하지 마라. '
 '각 이미지에서 플레이어가 읽는 모든 일본어 텍스트를 빠짐없이 식별하고 자연스러운 한국어로 번역하라. 장식용 로마자 로고와 숫자는 번역하지 않아도 된다. '
 '텍스트 블록별 bbox는 원본 캔버스 픽셀 좌표 [left,top,right,bottom]로, 실제 글자 영역을 약간 여유 있게 감싸라. '
 '표/달력/문서는 의미 단위별 여러 블록으로 나누고 원본의 줄 순서를 보존하라. filename은 아래 이름을 정확히 사용하라. 설명 없이 스키마 JSON만 출력하라.\n\n입력 이름:\n- '+'\n- '.join(names))
 cmd=[str(root/'tools'/'codex.exe'),'exec','--ephemeral','--skip-git-repo-check','-s','read-only','-C',str(root),'-c','model_reasoning_effort="medium"','--output-schema',str(root/'adapter'/'image-translation.schema.json'),'-o',str(out),'--image',*files,'-']
 started=time.time();p=subprocess.run(cmd,input=prompt.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800)
 (root/'logs'/'image-ui'/f'{packet_path.stem}.log').write_bytes(p.stdout)
 errors=[]
 if p.returncode:errors.append('exit '+str(p.returncode))
 try:
  obj=json.loads(out.read_text(encoding='utf-8'));got=[x['filename'] for x in obj['assets']]
  if got!=names:errors.append(f'names {got} != {names}')
 except Exception as e:errors.append(str(e))
 print(json.dumps({'packet':packet_path.name,'seconds':round(time.time()-started,1),'errors':errors},ensure_ascii=False),flush=True)
 if errors:raise SystemExit(1)
print('IMAGE QUEUE COMPLETE',flush=True)

