"""One reversible response-mapping mutant; normal source is restored even on test failure.

Usage from repo root (POSIX): python scripts/vt030_mutation.py -- ./mvnw -B
Windows: python scripts/vt030_mutation.py -- cmd /c mvnw.cmd -B
The runner executes Maven in backend, where sample fixtures use ../samples.
The command is a trusted user-supplied argv, never passed through shell=True.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'backend/src/main/java/vn/vietdoc/document/DocumentService.java'
OLD=b'        j.id,\n        j.documentId,\n'
NEW=b'        j.id,\n        j.id,\n'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'backend/target/vt030-mutation')
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=args.command
    if command and command[0]=='--':command=command[1:]
    if not command:parser.error('provide Maven argv after --')
    evidence=args.evidence_dir.resolve();evidence.mkdir(parents=True,exist_ok=True)
    original=TARGET.read_bytes()
    linebreak=b'\r\n' if b'\r\n' in original else b'\n'
    old=OLD.replace(b'\n',linebreak);new=NEW.replace(b'\n',linebreak)
    if original.count(old)!=1:raise RuntimeError('Unique expected mapper not found; refuse mutation')
    mutated=original.replace(old,new,1)
    result={'mutation':'JobView.document_id <- Job.id instead of Job.documentId',
            'source':str(TARGET.relative_to(ROOT)),'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'before_sha256':hashlib.sha256(original).hexdigest(),'mutant_sha256':hashlib.sha256(mutated).hexdigest()}
    command=command+['-Dtest=Vt030MappingTest,Vt030AsyncContractTest#tc01AcceptedResponseProvidesCorrectMonitorAndIdentity','test']
    result['command']=command
    try:
        TARGET.write_bytes(mutated)
        started = time.time()
        with (evidence/'mutation.txt').open('wb') as log:
            ran=subprocess.run(command,cwd=ROOT/'backend',stdout=log,stderr=subprocess.STDOUT,timeout=240)
        result['exit_code']=ran.returncode
        failures=[];reports=[]
        # Only fresh test reports count; compiler/setup errors cannot kill a mutant.
        for report in (ROOT/'backend/target/surefire-reports').glob('TEST-vn.vietdoc.Vt030*.xml'):
            if report.stat().st_mtime < started:
                continue
            suite=ET.parse(report).getroot()
            reports.append({k:suite.attrib.get(k) for k in ('name','tests','failures','errors','skipped')})
            for case in suite.findall('testcase'):
                for failure in case.findall('failure'):
                    if 'response field must map to owning document' in failure.attrib.get('message',''):
                        failures.append({'class':case.attrib.get('classname'),'test':case.attrib.get('name')})
        result['junit_reports']=reports
        result['mapping_failures']=failures
        result['killed']=ran.returncode!=0 and bool(failures)
    finally:
        TARGET.write_bytes(original)
        result['restored_sha256']=hashlib.sha256(TARGET.read_bytes()).hexdigest()
        result['restored_exact_bytes']=TARGET.read_bytes()==original
        (evidence/'mutation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    return 0 if result.get('killed') and result['restored_exact_bytes'] else 1

if __name__=='__main__':sys.exit(main())
