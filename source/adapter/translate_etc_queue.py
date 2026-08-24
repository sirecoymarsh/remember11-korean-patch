from __future__ import annotations
import json,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];outdir=root/'translations'/'etc-ui';outdir.mkdir(parents=True,exist_ok=True);(root/'logs'/'etc-ui').mkdir(parents=True,exist_ok=True)
for packet_path in sorted((root/'packets'/'etc-ui').glob('packet-*.json')):
 out=outdir/packet_path.name
 if out.exists():print('SKIP',packet_path.name,flush=True);continue
 files=json.loads(packet_path.read_text(encoding='utf-8'))['files'];names=[Path(x).name for x in files]
 prompt=('너는 Remember11 한국어판의 UI 번역자다. 첨부된 이미지는 일본어판 원본 UI 스프라이트다. 일본어판에 원래 영문으로 쓰인 버튼과 항목도 모두 한국어로 번역한다. 영어판 자료나 외부 검색은 사용하지 마라. '
 '각 이미지의 플레이어가 읽는 텍스트를 빠짐없이 식별하고 자연스럽고 짧은 한국어 UI 문구로 옮겨라. 장식용 Remember11 로고와 파일 식별용 숫자는 번역하지 않아도 된다. '
 'bbox는 원본 스프라이트 좌표 [left,top,right,bottom]이며 실제 텍스트 행 또는 상태별 텍스트를 약간 여유 있게 감싼다. 반복 상태는 각각 별도 블록으로 낸다. '
 'filename은 아래 이름을 정확히 사용하고 설명 없이 스키마 JSON만 출력하라.\n- '+'\n- '.join(names))
 cmd=[str(root/'tools'/'codex.exe'),'exec','--ephemeral','--skip-git-repo-check','-s','read-only','-C',str(root),'-c','model_reasoning_effort="medium"','--output-schema',str(root/'adapter'/'image-translation.schema.json'),'-o',str(out),'--image',*files,'-']
 st=time.time();p=subprocess.run(cmd,input=prompt.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800);(root/'logs'/'etc-ui'/f'{packet_path.stem}.log').write_bytes(p.stdout)
 errors=[]
 if p.returncode:errors.append('exit '+str(p.returncode))
 try:
  obj=json.loads(out.read_text(encoding='utf-8'));got=[x['filename'] for x in obj['assets']]
  if got!=names:errors.append(f'names {got} != {names}')
  if any(not x['blocks'] for x in obj['assets']):errors.append('empty blocks')
 except Exception as e:errors.append(str(e))
 print(json.dumps({'packet':packet_path.name,'seconds':round(time.time()-st,1),'errors':errors},ensure_ascii=False),flush=True)
 if errors:raise SystemExit(1)
print('ETC QUEUE COMPLETE',flush=True)
