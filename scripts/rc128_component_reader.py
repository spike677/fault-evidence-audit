"""Emit exact saved evidence ranges for the Agent; never infer a review verdict."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import difflib

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'reports/archive/rc128-actual-rework-20261113'
EVIDENCE=ROOT/'reports/evidence'


def resources():
    return [json.loads(s) for s in (SOURCE/'resource_audit.jsonl').read_text(encoding='utf-8').splitlines() if s]


def text_of(r):
    p=SOURCE/r['text_file']
    return p.read_bytes().decode('utf-8') if r['platform']=='GITHUB' else p.read_text(encoding='utf-8')


def hunk_signatures(text):
    """Hash exact returned per-file hunks, excluding email envelopes/trailers."""
    lines=text.splitlines();file=None;out=[];i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('diff --git '):file=line
        match=re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',line)
        if not match:i+=1;continue
        old=int(match[2]) if match[2] is not None else 1
        new=int(match[4]) if match[4] is not None else 1
        body=[line];i+=1
        while i<len(lines) and (old or new):
            value=lines[i]
            if value.startswith(' '):old-=1;new-=1
            elif value.startswith('-'):old-=1
            elif value.startswith('+'):new-=1
            elif value.startswith('\\'):body.append(value);i+=1;continue
            else:raise ValueError('Incomplete returned hunk')
            if old<0 or new<0:raise ValueError('Invalid returned hunk counts')
            body.append(value);i+=1
        if old or new:raise ValueError('Truncated returned hunk')
        out.append((file,sha256('\n'.join(body).encode()).hexdigest()))
    return out


def emit(r,start,end):
    text=text_of(r)
    start=max(0,start);end=min(len(text),end)
    event={'resource_id':r['resource_id'],'task_ids':r['task_ids'],'kind':r['kind'],
           'url':r['url'],'source_path':(SOURCE/r['text_file']).relative_to(ROOT).as_posix(),
           'start':start,'end':end,'total_chars':len(text),'sha256':sha256(text[start:end].encode()).hexdigest(),
           'first_line':text[:start].count('\n')+1,'last_line':text[:end].count('\n')+1}
    print(json.dumps(event,ensure_ascii=False))
    print(text[start:end])
    EVIDENCE.mkdir(exist_ok=True)
    with (EVIDENCE/'supplemental_read_sessions.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(event,ensure_ascii=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['inventory','read','changes','compact'])
    p.add_argument('ids',nargs='*')
    p.add_argument('--start',type=int,default=0)
    p.add_argument('--chars',type=int,default=14000)
    p.add_argument('--needle')
    a=p.parse_args(); rs=resources()
    if a.action=='inventory':
        for r in rs:
            if r['outcome']=='READABLE' and not r['review_selections']:
                t=text_of(r)
                print(json.dumps({'id':r['resource_id'],'case':r['task_ids'],'kind':r['kind'],'chars':len(t),
                                  'url':r['url'],'files':re.findall(r'^diff --git a/(.*?) b/',t,re.M)},ensure_ascii=False))
        return
    for key in a.ids:
        r=next(x for x in rs if x['resource_id']==key)
        t=text_of(r)
        if a.action=='read':
            start=a.start
            if a.needle:
                at=t.find(a.needle)
                if at<0:raise ValueError('Needle absent: '+a.needle)
                start=max(0,at-500)
            emit(r,start,start+a.chars)
        elif a.action=='compact':
            print(json.dumps({'resource_id':key,'url':r['url'],'cases':r['task_ids'],'kind':r['kind'],'total_chars':len(t)},ensure_ascii=False))
            lines=t.splitlines(keepends=True); offsets=[];at=0
            for line in lines:offsets.append(at);at+=len(line)
            breaks=[i for i,line in enumerate(lines) if line.startswith('diff --git')]+[len(lines)]
            chosen=set()
            for n in range(len(breaks)-1):
                lo,hi=breaks[n:n+2];chosen.add(lo)
                if re.search(r'\.(csv|tsv) b/',lines[lo]):
                    print('EXCLUDED_NUMERIC_TEST_DATA_FILE',lines[lo].strip());continue
                old=[];new=[]
                for i in range(lo+1,hi):
                    if lines[i].startswith(('+++','---')):continue
                    if lines[i].startswith('-'):old.append((lines[i][1:].strip(),i))
                    if lines[i].startswith('+'):new.append((lines[i][1:].strip(),i))
                # Selection aid only: report exact source lines, not a proof of equivalence.
                matcher=difflib.SequenceMatcher(None,[x[0] for x in old],[x[0] for x in new],autojunk=False)
                for op,i,j,k,l in matcher.get_opcodes():
                    if op!='equal':chosen.update(x[1] for x in old[i:j]+new[k:l])
            events=[];used=0
            for i in sorted(chosen):
                line=lines[i];start=offsets[i]
                if start<a.start:continue
                if used+len(line)>a.chars:print('NEXT_OFFSET',start);break
                print(str(i+1)+': '+line.rstrip());used+=len(line)
                events.append({'resource_id':key,'source_path':(SOURCE/r['text_file']).relative_to(ROOT).as_posix(),
                               'start':start,'end':start+len(line),'total_chars':len(t),
                               'sha256':sha256(line.encode()).hexdigest(),'first_line':i+1,'last_line':i+1})
            EVIDENCE.mkdir(exist_ok=True)
            with (EVIDENCE/'supplemental_read_sessions.jsonl').open('a',encoding='utf-8') as f:
                for e in events:f.write(json.dumps(e,ensure_ascii=False)+'\n')
        else:
            # Every displayed line has its exact source range. Omitted lines remain unread.
            lines=t.splitlines(keepends=True);offset=0;used=0
            print(json.dumps({'resource_id':key,'url':r['url'],'cases':r['task_ids'],'kind':r['kind'],'total_chars':len(t)},ensure_ascii=False))
            events=[]
            for line_no,line in enumerate(lines,1):
                take=line.startswith(('diff --git','@@','Subject:','From ')) or (
                    line.startswith(('+','-')) and not line.startswith(('+++','---')))
                if take and len(line)<900 and offset>=a.start:
                    if used+len(line)>a.chars:
                        print('NEXT_OFFSET',offset);break
                    print(str(line_no)+': '+line.rstrip())
                    events.append({'resource_id':key,'source_path':(SOURCE/r['text_file']).relative_to(ROOT).as_posix(),
                                   'start':offset,'end':offset+len(line),'total_chars':len(t),
                                   'sha256':sha256(line.encode()).hexdigest(),'first_line':line_no,'last_line':line_no})
                    used+=len(line)
                offset+=len(line)
            EVIDENCE.mkdir(exist_ok=True)
            with (EVIDENCE/'supplemental_read_sessions.jsonl').open('a',encoding='utf-8') as f:
                for e in events:f.write(json.dumps(e,ensure_ascii=False)+'\n')


if __name__=='__main__':main()
