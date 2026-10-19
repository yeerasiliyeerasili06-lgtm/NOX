"""Run one bounded REAL browser test using existing NOX 0.9, no user input.

The NOX package source is read only. This adapter captures an actual browser's
post-navigation URL/title/headings for an independent QA verdict.
"""
from __future__ import annotations
import argparse
import json
import sys
import traceback
from pathlib import Path
from urllib.parse import urlsplit

CASES = {
    'statistics': {'id':'python_statistics_document','initial_url':'https://docs.python.org/3/',
        'goal':'在这个网站搜索 Python 标准库 statistics 模块文档，并打开对应文档','topic':'statistics'},
    'pathlib': {'id':'python_pathlib_document','initial_url':'https://docs.python.org/3/',
        'goal':'在这个网站搜索 Python 标准库 pathlib 模块文档，并打开对应文档','topic':'pathlib'},
    'itertools': {'id':'python_itertools_document','initial_url':'https://docs.python.org/3/',
        'goal':'在这个网站搜索 Python 标准库 itertools 模块文档，并打开对应文档','topic':'itertools'},
}
CASE=CASES['statistics']


def parse_public_page_metadata(text):
    """Extract only the fixed Playwright metadata, never the page body."""
    if not isinstance(text,str) or len(text)>60000:
        return None
    prefix=text.split('### Ran Playwright code',1)[0]
    brace=prefix.find('{')
    if brace < 0:
        return None
    try:
        item,_=json.JSONDecoder().raw_decode(prefix[brace:])
    except (TypeError, ValueError):
        return None
    if not isinstance(item,dict):
        return None
    url=item.get('url'); title=item.get('title'); headings=item.get('headings')
    if not isinstance(url,str) or not isinstance(title,str) or not isinstance(headings,list):
        return None
    if not all(isinstance(x,str) for x in headings):
        return None
    if len(url)>1000 or len(title)>400 or len(headings)>16 or any(len(x)>300 for x in headings):
        return None
    return {'url':url,'title':title,'headings':headings}


def assess(actual_result,evidence,actions,case=CASE):
    """Additional independent QA gate beyond NOX's internal success message."""
    if actual_result != 'VERIFIED_DOCUMENT':
        return False, 'APP_DID_NOT_VERIFY_DOCUMENT'
    if not isinstance(evidence,dict):
        return False,'BROWSER_METADATA_MISSING'
    if (not isinstance(evidence.get('url'),str) or
        not isinstance(evidence.get('title'),str) or
        not isinstance(evidence.get('headings'),list) or
        any(not isinstance(h,str) for h in evidence['headings'])):
        return False,'BROWSER_METADATA_INVALID'
    if not isinstance(actions,list) or any(not isinstance(a,dict) or not isinstance(a.get('tool'),str) for a in actions):
        return False,'BROWSER_ACTION_EVIDENCE_INVALID'
    observed=urlsplit(evidence['url'])
    initial=urlsplit(case['initial_url'])
    if observed.scheme != 'https' or observed.hostname != initial.hostname:
        return False,'FINAL_URL_OUTSIDE_APPROVED_DOMAIN'
    if evidence['url'].rstrip('/') == case['initial_url'].rstrip('/') or not observed.path:
        return False,'NO_MEANINGFUL_NAVIGATION'
    # This is an independent benchmark for the *specific Python standard
    # library module*, not a generic string-hit search. A tracemalloc method
    # containing 'statistics' is not the statistics module documentation.
    expected_path='/3/library/'+case['topic']+'.html'
    if observed.path != expected_path or observed.query:
        return False,'WRONG_TARGET_DOCUMENT_URL' 
    haystack=' '.join([evidence['title']]+evidence['headings']).lower()
    if case['topic'].lower() not in haystack:
        return False,'REQUESTED_TOPIC_NOT_IN_PAGE_TITLE_OR_HEADINGS'
    if not any(x['tool']=='browser_type' for x in actions):
        return False,'NO_SEARCH_TOOL_OBSERVED'
    if not any(x['tool']=='browser_click' for x in actions):
        return False,'NO_DOCUMENT_CLICK_OBSERVED'
    if len([x for x in actions if x['tool'] in ('browser_click','browser_type')])>3:
        return False,'ACTION_BUDGET_EXCEEDED'
    return True,'INDEPENDENT_BROWSER_EVIDENCE_CONFIRMED'


def run(installation:Path,work_dir:Path,case_id:str="statistics"):
    case=CASES[case_id]
    src=installation/'src'
    sys.path.insert(0,str(src))
    import agent
    from experience import ExperienceStore

    evidence={'metadata':None,'actions':[],'app_result':None,'case_id':case['id']}
    class QAObservedMCP(agent.MCP):
        def tool(self,name,args):
            if name not in ('browser_navigate','browser_snapshot','browser_click','browser_type','browser_evaluate'):
                raise agent.NoxStop('QA_UNEXPECTED_TOOL')
            # Record only tool type and not text/ref/page body/private user content.
            if name in ('browser_type','browser_click'):
                evidence['actions'].append({'tool':name})
            result=super().tool(name,args)
            if name=='browser_evaluate':
                meta=parse_public_page_metadata(result)
                if meta:
                    evidence['metadata']=meta
            return result

    work_dir.mkdir(parents=True,exist_ok=True)
    store=ExperienceStore(work_dir/'qa_only_experience.sqlite3')
    try:
        evidence['app_result']=agent.run(case['initial_url'],case['goal'],
                                         mcp_factory=QAObservedMCP,store=store)
        passed,reason=assess(evidence['app_result'],evidence['metadata'],evidence['actions'],case)
        evidence['qa_pass']=passed
        evidence['reason']=reason
    except Exception as exc:
        evidence['qa_pass']=False
        evidence['reason']='APP_EXCEPTION:'+type(exc).__name__
        # Do not print raw exception text: it can contain private paths,
        # webpage text, or model responses. Full stack traces are not required.
        print('[NOX-QA] App ended with exception: '+type(exc).__name__,flush=True)
    finally:
        destination=work_dir/'browser_evidence.json'
        destination.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[NOX-QA] '+('LIVE_BROWSER_PASS' if evidence['qa_pass'] else 'LIVE_BROWSER_FAIL')+
          ' reason='+evidence['reason'],flush=True)
    return 0 if evidence['qa_pass'] else 3

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--installation',required=True)
    parser.add_argument('--work-dir',required=True)
    parser.add_argument('--case',choices=list(CASES),default='statistics')
    args=parser.parse_args()
    sys.exit(run(Path(args.installation).resolve(),Path(args.work_dir).resolve(),args.case))
