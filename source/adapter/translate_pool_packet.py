from __future__ import annotations
import argparse,json,re,subprocess,time
from pathlib import Path
CONTROL_RE=re.compile(r'%(?:TS\d{3}|T\d+|X\d{3}|C[0-9A-Fa-f]+|LC|FS|FE|TE|N|K|P|p|O)')
def byte_estimate(text):
 n=0
 for ch in text:
  try:n+=len(ch.encode('cp932'))
  except UnicodeEncodeError:n+=2
 return n
def validate(packet,result):
 errors=[];src=packet['items'];got=result.get('translations') if isinstance(result,dict) else None
 if not isinstance(got,list):return ['translations is not an array']
 if len(got)!=len(src):errors.append(f'count {len(got)} != {len(src)}')
 for i,(a,b) in enumerate(zip(src,got)):
  if b.get('key')!=a['key']:errors.append(f'key[{i}]')
  t=b.get('target_ko')
  if not isinstance(t,str) or not t:errors.append(f'empty[{i}]');continue
  if CONTROL_RE.findall(t)!=a['controls']:errors.append(f'controls[{i}] {CONTROL_RE.findall(t)} != {a["controls"]}')
  if a['storage']=='fixed' and byte_estimate(t)>a['max_source_bytes']:errors.append(f'fixed_overflow[{i}] {byte_estimate(t)}>{a["max_source_bytes"]}')
 return errors
def run(root,packet_path,out,retries=2):
 packet=json.loads(packet_path.read_text(encoding='utf-8'));guide=(root/'localization'/'style-guide.md').read_text(encoding='utf-8');data=json.dumps(packet,ensure_ascii=False,separators=(',',':'))
 base=('너는 Remember11 한국어판의 시나리오·선택지·시스템 문자열 번역자다. 아래 스타일 가이드와 일본어 원문 JSON만 사용하라. 영어판 파일, 영어 번역, 외부 검색은 사용하지 마라.\n'
 'items 각 항목마다 정확히 하나씩 입력과 같은 순서·같은 key로 target_ko를 작성하라. previous_jp와 next_jp는 문맥 참고용이다. source_jp의 모든 % 제어 코드를 철자·대소문자·순서까지 정확히 보존하라. 일본어를 빠뜨리지 말고 자연스러운 한국어로 완역하라.\n'
 'storage가 fixed인 항목은 max_source_bytes를 넘지 않아야 하며 ASCII는 1바이트, 한글/일본어 문자는 2바이트로 계산한다. 짧고 자연스럽게 축약하라. 설명 없이 지정 스키마 JSON만 출력하라.\n\n[스타일 가이드]\n'+guide+'\n[원문 패킷]\n'+data+'\n')
 out.parent.mkdir(parents=True,exist_ok=True);(root/'logs'/'script-pool').mkdir(parents=True,exist_ok=True)
 for a in range(retries+1):
  prompt=base+(f'\n이전 결과는 검증 실패했다. {len(packet["items"])}개 전체를 처음부터 다시 내고 제어 코드와 fixed 길이를 지켜라.\n' if a else '')
  cmd=[str(root/'tools'/'codex.exe'),'exec','--ephemeral','--skip-git-repo-check','-s','read-only','-C',str(root),'-c','model_reasoning_effort="low"','--output-schema',str(root/'adapter'/'translation-output.schema.json'),'-o',str(out),'-']
  st=time.time();p=subprocess.run(cmd,input=prompt.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800);(root/'logs'/'script-pool'/f'{packet_path.stem}.attempt{a}.log').write_bytes(p.stdout)
  try:errors=[f'exit {p.returncode}'] if p.returncode else validate(packet,json.loads(out.read_text(encoding='utf-8')))
  except Exception as e:errors=[str(e)]
  print(json.dumps({'packet':packet_path.name,'attempt':a,'seconds':round(time.time()-st,1),'errors':errors[:20]},ensure_ascii=False),flush=True)
  if not errors:out.with_suffix('.ok.json').write_text(json.dumps({'validated':True,'count':len(packet['items'])},indent=2),encoding='utf-8');return
 raise SystemExit(1)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('packet',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--retries',type=int,default=2);a=ap.parse_args();run(a.root,a.packet,a.output,a.retries)
if __name__=='__main__':main()
