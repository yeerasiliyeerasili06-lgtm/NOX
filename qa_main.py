"""NOX autonomous test runner: independent, bounded, evidence-gated pilot.

Run NOX 0.9 unittests and one real isolated-browser workflow, collect logs and
publish machine-readable + human-readable reports. No code edits or retries.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import re
import time
import urllib.error
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parent
DEFAULT_APP=ROOT/'app'
MAX_SECONDS_TESTS=75
MAX_SECONDS_BROWSER=300
MAX_BYTES_OUTPUT=160000


def file_sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            block=f.read(65536)
            if not block:break
            digest.update(block)
    return digest.hexdigest()


def source_tree_sha(src_dir):
    """Digest of *all* code files, not just agent.py, with stable filenames."""
    digest=hashlib.sha256()
    source_files=sorted(src_dir.rglob('*.py'),key=lambda p:p.relative_to(src_dir).as_posix())
    if not source_files:raise ValueError('SOURCE_FILES_MISSING')
    for path in source_files:
        if path.is_symlink() or not path.is_file():raise ValueError('SOURCE_FILE_UNSAFE')
        rel=path.relative_to(src_dir).as_posix().encode('utf8')
        blob=path.read_bytes()
        digest.update(len(rel).to_bytes(4,'big')+rel)
        digest.update(len(blob).to_bytes(8,'big')+blob)
    return digest.hexdigest()


def safe_log(text):
    return text[-MAX_BYTES_OUTPUT:]


def service_ok():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2) as req:
            return req.status==200
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        return False


def contains_model():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as req:
            response=json.load(req)
        return any(x.get('name')=='qwen3.5:4b-q4_K_M' for x in response.get('models',[]))
    except (urllib.error.URLError,TimeoutError,OSError,ValueError,TypeError):
        return False


def locate_ollama():
    standard=pathlib.Path(os.environ.get('LOCALAPPDATA',''))/'Programs'/'Ollama'/'ollama.exe'
    if standard.exists():return str(standard)
    return shutil.which('ollama')


def start_ollama_if_needed(log):
    """Only start if unreachable, never stop unrelated pre-existing service."""
    if service_ok():return None
    exe=locate_ollama()
    if not exe:
        log.append('Ollama executable not found')
        return None
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    try:
        # Do not capture pipes: Ollama can log more than a pipe holds.
        process=subprocess.Popen([exe,'serve'],stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 creationflags=flags)
    except OSError as exc:
        log.append('Ollama launch failed: '+str(exc)[:120]);return None
    for _ in range(20):
        if service_ok():
            log.append('Ollama started and ready')
            return process
        if process.poll() is not None:break
        time.sleep(1)
    log.append('Ollama not ready after bounded startup')
    return process


def terminate_owned(proc):
    if proc is None or proc.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,check=False)
    else:
        proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill()


def subprocess_with_deadline(command,seconds,cwd=None):
    """Run a child with a real deadline without buffering unbounded output in RAM.

    stdout is redirected to a temporary file; only its bounded tail is returned.
    On Windows a timed-out child process tree is killed, never retried.
    """
    with tempfile.TemporaryFile(mode='w+b') as capture:
        proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=capture,
                              stderr=subprocess.STDOUT,cwd=cwd,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        timedout=False
        try:
            proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timedout=True
            terminate_owned(proc)
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:pass
        capture.flush()
        capture.seek(0,os.SEEK_END)
        size=capture.tell()
        capture.seek(max(0,size-MAX_BYTES_OUTPUT))
        output=capture.read(MAX_BYTES_OUTPUT).decode('utf-8',errors='replace')
        return (None if timedout else proc.returncode),output,timedout


DIAGNOSTIC_CODES=(
    ('DOCUMENT_OPENED_BUT_CONTENT_NOT_VERIFIED','DOCUMENT_METADATA_OR_URL_MISMATCH'),
    ('DOCUMENT_LINK_AMBIGUOUS','DOCUMENT_SELECTION_DECLINED'),
    ('NO_MATCHING_DOCUMENT_LINK','NO_MATCHING_DOCUMENT_LINK'),
    ('DOCUMENT_LINK_CHANGED','DOCUMENT_LINK_CHANGED'),
    ('SEARCH_RESULTS_FOUND_BUT_DOCUMENT_NOT_OPENED','DOCUMENT_STEP_BUDGET'),
    ('QUERY_DISPATCHED_BUT_RESULT_UNVERIFIED','SEARCH_RESULT_NOT_VERIFIED'),
    ('MODEL_CHOSE_NO_ACTION','MODEL_DECLINED_ACTION'),
    ('NO_SAFE_MATCHING_CONTROLS','NO_SAFE_CONTROLS'),
    ('TASK_DEADLINE_REACHED','TASK_DEADLINE_REACHED'),
    ('MCP_DEADLINE_EXCEEDED','MCP_DEADLINE_EXCEEDED'),
    ('DOCUMENT_VERIFIED','INDEPENDENT_QA_REJECTED_DOCUMENT'),
    ('App ended with exception','APP_EXCEPTION'),
)

def diagnostic_code(log_text):
    """Whitelist reason codes only; never copy untrusted webpage or user paths."""
    for needle,code in DIAGNOSTIC_CODES:
        if needle in log_text:
            return code
    return 'UNCLASSIFIED_BROWSER_FAILURE'


def safe_path(path):
    if path.is_symlink():return False
    return path.is_file()


def handoff_projection(record,report_hash):
    """Minimal path-free data for a future, separately authorized chat bridge.

    This function DOES NOT send anything. It deliberately drops target paths,
    raw logs, URLs, page content, and freeform exception text.
    """
    def code(value):
        if not isinstance(value,str):return 'UNKNOWN'
        return value if re.fullmatch(r'[A-Z0-9_]{1,80}',value) else 'OTHER'
    cases=[]
    for item in record.get('case_results',[]):
        if not isinstance(item,dict):continue
        name=item.get('id')
        if name not in ('statistics','pathlib','itertools'):continue
        cases.append({'case':name,'verdict':code(item.get('verdict')),
                      'diagnostic_code':code(item.get('diagnostic_code'))})
    digest=record.get('source_sha256')
    if not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest):
        digest=None
    return {'schema_version':1,'project':'NOX','delivery':'NOT_SENT',
            'verdict':code(record.get('verdict')),
            'unit_tests':code(record.get('unit_tests',{}).get('verdict')),
            'live_browser':code(record.get('live_browser',{}).get('verdict')),
            'cases':cases,'source_sha256':digest,
            'report_sha256':report_hash}


def reports(report_dir,record):
    target=report_dir/'report.json'
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    projection=handoff_projection(record,file_sha(target))
    (report_dir/'handoff_summary.json').write_text(
        json.dumps(projection,ensure_ascii=False,indent=2),encoding='utf-8')
    brief='NOX | '+projection['verdict']+' | '+projection['unit_tests']+' | '+projection['live_browser']
    if projection['cases']:
        brief+=' | '+','.join(x['case']+':'+x['verdict']+'('+x['diagnostic_code']+')' for x in projection['cases'])
    (report_dir/'handoff_summary.txt').write_text(brief+'\n',encoding='utf-8')
    status=record['verdict']
    md=[f'# NOX 自主测试报告 — {status}', '',
        '本报告由独立 QA 工具生成，仅声明实际观察到的结果。', '',
        f"- 运行时间：{record['timestamp']}",
        f"- 目标版本：NOX isolated QA source candidate（SHA256 {record.get('source_sha256','n/a')}）",
        f"- 单元测试：{record['unit_tests']['verdict']}",
        f"- 真实网页任务：{record['live_browser']['verdict']}",
        f"- 真实任务细节：{record['live_browser'].get('reason','')}",
        f"- 失败阶段代码：{record['live_browser'].get('diagnostic_code','')}",
        f"- 自动修复：未启用（不会改动应用源码）",
        '', '## 验收说明',
        '单元测试通过不代表 GUI 实测通过。网页实测须同时满足 NOX 的自身验证与独立 QA 的 URL、标题/章节、实际操作证据。',
        '本阶段没有验证任意 Windows GUI、Root、刷机、经验学习提升或 Stage 1 极速聊天回归。',
        f"- 测试场景：{', '.join(x['id'] for x in record.get('case_results',[]))}",
        '', '## 证据位置',
        '- `unit_tests.log`：原项目的实际单元测试输出',
        '- `browser_task.log`：真实隔离浏览器操作日志',
        '- `browser_evidence.json`：实测网址、标题、章节和工具类型',
        '- `report.json`：机器可读结论',
        '- `handoff_summary.json`：不含用户路径的脱敏交接摘要（未发送）',
        '- `handoff_summary.txt`：简短结果代码（未发送）', '']
    (report_dir/'REPORT_打开我.md').write_text('\n'.join(md),encoding='utf-8')
    return target


def main():
    parser=argparse.ArgumentParser(description='NOX bounded unattended QA')
    parser.add_argument('--app',type=pathlib.Path,default=DEFAULT_APP)
    parser.add_argument('--offline-only',action='store_true')
    parser.add_argument('--cases',default='statistics',choices=['statistics','all'])
    parser.add_argument('--report-dir',type=pathlib.Path)
    args=parser.parse_args()
    app=args.app.resolve()
    stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    report_dir=(args.report_dir or ROOT/'reports'/stamp).resolve()
    report_dir.mkdir(parents=True,exist_ok=False)
    record={'timestamp':dt.datetime.now().astimezone().isoformat(),
            'tested_copy':'isolated_qa_candidate; all existing installations unchanged',
            'target_path':'isolated_candidate','verdict':'NOT_STARTED',
            'unit_tests':{'verdict':'NOT_RUN'},
            'live_browser':{'verdict':'NOT_RUN'},
            'source_sha256':None}
    own_ollama=None
    log=[]
    try:
        source=app/'src'/'agent.py'; tests=app/'tests'
        if not safe_path(source) or not tests.is_dir():
            record['verdict']='BLOCKED_NO_INSTALLED_NOX_09'
            record['unit_tests']['verdict']='BLOCKED'
            record['live_browser']['verdict']='BLOCKED'
            return 2
        record['source_sha256']=source_tree_sha(app/'src')
        print('[NOX-QA] Step 1/2: isolated NOX 0.9.1 fixed-copy unit tests',flush=True)
        cmd=[sys.executable,'-m','unittest','discover','-s',str(tests),'-q']
        code,stdout,timedout=subprocess_with_deadline(cmd,MAX_SECONDS_TESTS,cwd=app)
        (report_dir/'unit_tests.log').write_text(stdout,encoding='utf-8')
        record['unit_tests']={'verdict':'PASS' if code==0 and not timedout else 'FAIL',
                              'returncode':code,'timed_out':timedout}
        if code!=0 or timedout:
            record['verdict']='FAIL_UNIT_TESTS'
            record['live_browser']['verdict']='NOT_RUN';return 3
        if args.offline_only:
            record['verdict']='OFFLINE_ONLY_PASS_NOT_GUI_VERIFIED';
            record['live_browser']['verdict']='NOT_RUN';return 0
        if not shutil.which('node') or not (shutil.which('npx') or shutil.which('npx.cmd')):
            record['verdict']='BLOCKED_NODE_MISSING';record['live_browser']={'verdict':'BLOCKED','reason':'NODE_NPX_NOT_FOUND'};return 2
        own_ollama=start_ollama_if_needed(log)
        if not service_ok():
            record['verdict']='BLOCKED_OLLAMA_NOT_READY';record['live_browser']={'verdict':'BLOCKED','reason':'OLLAMA_UNREACHABLE'};return 2
        if not contains_model():
            record['verdict']='BLOCKED_REQUIRED_MODEL_MISSING';record['live_browser']={'verdict':'BLOCKED','reason':'QWEN35_4B_NOT_INSTALLED'};return 2
        cases=['statistics','pathlib','itertools'] if args.cases=='all' else ['statistics']
        all_ok=True
        case_results=[]
        for i,case in enumerate(cases,1):
            print(f'[NOX-QA] Real browser task {i}/{len(cases)}: {case}',flush=True)
            print('[NOX-QA] Bounded 300 seconds each, no sign-ins or code changes',flush=True)
            case_dir=report_dir/('case_'+case)
            case_dir.mkdir(parents=True,exist_ok=False)
            cmd=[sys.executable,'-u',str(ROOT/'qa_worker.py'),'--installation',str(app),
                 '--work-dir',str(case_dir),'--case',case]
            code,stdout,timedout=subprocess_with_deadline(cmd,MAX_SECONDS_BROWSER,cwd=ROOT)
            (case_dir/'browser_task.log').write_text(stdout,encoding='utf-8')
            ev=case_dir/'browser_evidence.json'
            evidence=json.loads(ev.read_text(encoding='utf-8')) if ev.is_file() else {}
            ok=code==0 and not timedout and evidence.get('qa_pass') is True
            reason='TASK_TIMEOUT' if timedout else evidence.get('reason','EVIDENCE_NOT_WRITTEN')
            diagnosis='PASS' if ok else ('TASK_TIMEOUT' if timedout else diagnostic_code(stdout))
            case_results.append({'id':case,'verdict':'PASS' if ok else 'FAIL',
                                 'reason':reason if isinstance(reason,str) and len(reason)<128 else 'OTHER_OR_UNCLASSIFIED',
                                 'diagnostic_code':diagnosis,
                                 'returncode':code,'timed_out':timedout,
                                 'evidence_sha256':file_sha(ev) if ev.is_file() else None})
            if not ok:
                all_ok=False
                # An observed failure is useful evidence; no silent retries or runaway tests.
                break
        record['case_results']=case_results
        record['live_browser']={'verdict':'PASS' if all_ok else 'FAIL',
                                'reason':'INDEPENDENT_BROWSER_EVIDENCE_CONFIRMED' if all_ok else case_results[-1]['reason'],
                                'diagnostic_code':'PASS' if all_ok else case_results[-1]['diagnostic_code'],
                                'cases_run':len(case_results),'cases_expected':len(cases)}
        if all_ok:record['verdict']='PASS_THREE_BROWSER_CASES' if len(cases)==3 else 'PASS_REAL_BROWSER'
        else:record['verdict']='FAIL_REAL_BROWSER'
        return 0 if all_ok else 3
    except KeyboardInterrupt:
        record['verdict']='CANCELLED';return 130
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        record['verdict']='HARNESS_ERROR:'+type(exc).__name__;return 4
    finally:
        if own_ollama and own_ollama.poll() is None:
            # Only stop the service started by this QA program, NOT unrelated Ollama.
            terminate_owned(own_ollama)
        if log:
            (report_dir/'preflight.log').write_text('\n'.join(log),encoding='utf-8')
        outfile=reports(report_dir,record)
        print('[NOX-QA] '+record['verdict'],flush=True)
        print('[NOX-QA] Report: '+str(outfile),flush=True)

if __name__=='__main__':sys.exit(main())
