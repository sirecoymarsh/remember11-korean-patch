from __future__ import annotations
import argparse,json,re,subprocess,time
from pathlib import Path
CONTROL_RE=re.compile(r"%(?:TS\d{3}|T\d+|X\d{3}|C[0-9A-Fa-f]+|LC|FS|FE|TE|N|K|P)")

def validate(packet:dict,result:dict)->list[str]:
    errors=[]; src=packet['items']; got=result.get('translations') if isinstance(result,dict) else None
    if not isinstance(got,list): return ['translations is not an array']
    if len(got)!=len(src): errors.append(f'count {len(got)} != {len(src)}')
    for i,(a,b) in enumerate(zip(src,got)):
        if b.get('key')!=a['key']: errors.append(f"key[{i}] {b.get('key')} != {a['key']}")
        t=b.get('target_ko')
        if not isinstance(t,str) or not t: errors.append(f'empty target[{i}]'); continue
        if CONTROL_RE.findall(t)!=a['controls']: errors.append(f"controls[{i}] {CONTROL_RE.findall(t)} != {a['controls']}")
        if '원문이 물음표로 손상' in t: errors.append(f'damaged-source placeholder[{i}]')
    return errors

def translate(root:Path,packet_path:Path,out_path:Path,retries:int=2)->None:
    packet=json.loads(packet_path.read_text(encoding='utf-8'))
    guide=(root/'localization'/'style-guide.md').read_text(encoding='utf-8')
    data=json.dumps(packet,ensure_ascii=False,separators=(',',':'))
    instruction=(
        '너는 Remember11 한국어판의 시나리오 번역자다. 아래 스타일 가이드와 일본어 원문 JSON만 사용하라. '
        '영어 번역, 영어판 파일, 외부 검색은 사용하지 마라.\n'
        'items의 각 항목마다 정확히 하나씩, 입력과 같은 순서·같은 key로 target_ko를 작성하라. '
        'previous_jp와 next_jp는 문맥 참고용이며 출력 대상이 아니다. source_jp의 모든 % 제어 코드는 철자와 순서를 정확히 보존하라. '
        '일본어를 빠뜨리지 말고 자연스러운 한국어로 완역하라. 설명 없이 지정된 JSON 스키마로만 응답하라.\n\n'
    )
    base=instruction+'[스타일 가이드]\n'+guide+'\n[번역 패킷]\n'+data+'\n'
    out_path.parent.mkdir(parents=True,exist_ok=True); (root/'logs'/'scenario-translation').mkdir(parents=True,exist_ok=True)
    for attempt in range(retries+1):
        prompt=base
        if attempt: prompt += f'\n이전 결과는 검증에 실패했다. 입력 {len(packet["items"])}개를 하나도 생략하지 말고 제어 코드를 보존하여 전체를 처음부터 다시 출력하라.\n'
        cmd=[str(root/'tools'/'codex.exe'),'exec','--ephemeral','--skip-git-repo-check','-s','read-only','-C',str(root),'-c','model_reasoning_effort="low"','--output-schema',str(root/'adapter'/'translation-output.schema.json'),'-o',str(out_path),'-']
        started=time.time(); p=subprocess.run(cmd,input=prompt.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800)
        (root/'logs'/'scenario-translation'/f'{packet_path.stem}.attempt{attempt}.log').write_bytes(p.stdout)
        if p.returncode!=0: errors=[f'codex exit {p.returncode}']
        else:
            try: errors=validate(packet,json.loads(out_path.read_text(encoding='utf-8')))
            except Exception as e: errors=[f'parse: {e}']
        status={'packet':packet_path.name,'attempt':attempt,'seconds':round(time.time()-started,1),'errors':errors[:20]}
        print(json.dumps(status,ensure_ascii=False),flush=True)
        if not errors:
            out_path.with_suffix('.ok.json').write_text(json.dumps({'validated':True,'count':len(packet['items']),'seconds':status['seconds']},ensure_ascii=False,indent=2),encoding='utf-8')
            return
    raise SystemExit('translation failed: '+packet_path.name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('packet',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--retries',type=int,default=2);a=ap.parse_args();translate(a.root,a.packet,a.output,a.retries)
if __name__=='__main__': main()
