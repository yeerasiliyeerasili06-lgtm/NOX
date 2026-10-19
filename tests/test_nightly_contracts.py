"""Offline cross-component contract tests for the isolated NOX research/QA candidate."""
from __future__ import annotations
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'app'/'src'))
import agent
import research
import qa_main
import qa_worker

GOAL='在这个网站搜索 Python 标准库 pathlib 模块文档，并打开对应文档'
HOME='''- Page URL: https://docs.python.org/3/
- Page Title: Python docs
- searchbox "Quick search" [ref=e1]
'''
RESULTS='''- Page URL: https://docs.python.org/3/search.html?q=pathlib
- Page Title: Search results
- link "pathlib.Path" [ref=e10]
- link "pathlib — Object-oriented filesystem paths" [ref=e11]
- link "pathlib.PurePath" [ref=e12]
- searchbox "Quick search" [ref=e1]
'''
RIGHT={'url':'https://docs.python.org/3/library/pathlib.html',
       'title':'pathlib — Object-oriented filesystem paths',
       'headings':['pathlib — Object-oriented filesystem paths']}
WRONG={'url':'https://docs.python.org/3/library/tracemalloc.html',
       'title':'tracemalloc.Snapshot.statistics',
       'headings':['tracemalloc.Snapshot.statistics']}

class FakeMemory:
    def __init__(self):self.writes=[]
    def hint(self,*args):return None
    def save_verified(self,*args):self.writes.append(args);return True

class FakeMCP:
    def __init__(self,metadata_sequence):
        self.metadata_sequence=metadata_sequence
        self.calls=[]
        self.pos='home'
        props={'target':{},'element':{},'text':{},'submit':{}}
        self.tools={
            'browser_click':{'inputSchema':{'properties':props,'required':['target']}},
            'browser_type':{'inputSchema':{'properties':props,'required':['target','text']}},
            'browser_evaluate':{'inputSchema':{'properties':{'function':{}},'required':['function']}}}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def tool(self,name,args):
        self.calls.append((name,args))
        if name=='browser_type':
            self.pos='results'
        elif name=='browser_click':
            if args.get('target')!='e11':raise AssertionError('clicked wrong link')
            self.pos='document'
        elif name=='browser_evaluate':
            assert args=={'function':agent.PAGE_META_FN}
            if len(self.metadata_sequence)>1:
                record=self.metadata_sequence.pop(0)
            else:
                record=self.metadata_sequence[0]
            return '### Result\n'+json.dumps(record)
        return {'home':HOME,'results':RESULTS,'document':RESULTS}[self.pos]

class ResearchIntegrationTests(unittest.TestCase):
    def test_unique_module_field_uses_only_exact_topic(self):
        choices=[agent.Candidate(1,'e1','searchbox','Quick search','browser_type')]
        plan=agent.fast_unambiguous_search(GOAL,choices)
        self.assertEqual(plan['text'],'pathlib')
        self.assertEqual(plan['choice'],1)
    def test_multiple_search_fields_still_require_model(self):
        choices=[agent.Candidate(i,'e'+str(i),'searchbox','Search','browser_type') for i in (1,2)]
        self.assertIsNone(agent.fast_unambiguous_search(GOAL,choices))
    def test_exact_module_link_excludes_methods(self):
        self.assertEqual(research.observed_result_links(HOME,RESULTS,GOAL,'pathlib'),
                         [('e11','pathlib — Object-oriented filesystem paths')])
    def test_single_click_waits_for_delayed_metadata(self):
        fake=FakeMCP([{'url':'https://docs.python.org/3/search.html?q=pathlib',
                       'title':'Search results','headings':['Search results']},RIGHT])
        memory=FakeMemory()
        with patch.object(agent.time,'sleep') as sleeper, patch.object(agent,'ask_model',side_effect=AssertionError('doc LLM should not be used')):
            with patch.object(agent,'fast_unambiguous_search',return_value={'choice':1,'text':'pathlib','explanation':'unique'}):
                outcome=agent.run('https://docs.python.org/3/',GOAL,lambda:fake,agent.ask_model,memory)
        self.assertEqual(outcome,'VERIFIED_DOCUMENT')
        self.assertEqual([x[0] for x in fake.calls].count('browser_click'),1)
        self.assertEqual([x[0] for x in fake.calls].count('browser_evaluate'),2)
        self.assertEqual(sleeper.call_count,1)
        self.assertEqual(len(memory.writes),1)
    def test_never_reclicks_when_metadata_never_verifies(self):
        fake=FakeMCP([{'url':'https://docs.python.org/3/library/other.html',
                       'title':'Other module','headings':['Other module']}])
        memory=FakeMemory()
        with patch.object(agent.time,'sleep'), patch.object(agent,'fast_unambiguous_search',return_value={'choice':1,'text':'pathlib','explanation':'unique'}):
            with patch.object(agent,'ask_model',side_effect=AssertionError('doc LLM should not be used')):
                outcome=agent.run('https://docs.python.org/3/',GOAL,lambda:fake,agent.ask_model,memory)
        self.assertEqual(outcome,'UNVERIFIED')
        self.assertEqual([x[0] for x in fake.calls].count('browser_click'),1)
        self.assertEqual([x[0] for x in fake.calls].count('browser_evaluate'),3)
        self.assertEqual(memory.writes,[])
    def test_cross_origin_metadata_fails_closed_without_reclick(self):
        fake=FakeMCP([{'url':'https://untrusted.example/library/pathlib.html',
                       'title':'pathlib','headings':['pathlib']}])
        with patch.object(agent,'fast_unambiguous_search',return_value={'choice':1,'text':'pathlib','explanation':'unique'}):
            with patch.object(agent,'ask_model',side_effect=AssertionError('doc LLM should not be used')):
                with self.assertRaisesRegex(agent.NoxStop,'PAGE_LEFT_INITIAL_ORIGIN'):
                    agent.run('https://docs.python.org/3/',GOAL,lambda:fake,agent.ask_model,FakeMemory())
        self.assertEqual([x[0] for x in fake.calls].count('browser_click'),1)

class HarnessContractTests(unittest.TestCase):
    def test_independent_qa_accepts_three_correct_docs(self):
        actions=[{'tool':'browser_type'},{'tool':'browser_click'}]
        for topic,case in qa_worker.CASES.items():
            evidence={'url':'https://docs.python.org/3/library/'+topic+'.html',
                      'title':topic+' — module','headings':[topic]}
            self.assertEqual(qa_worker.assess('VERIFIED_DOCUMENT',evidence,actions,case),
                             (True,'INDEPENDENT_BROWSER_EVIDENCE_CONFIRMED'))
    def test_qa_rejects_bad_metadata_with_reason_not_exception(self):
        actions=[{'tool':'browser_type'},{'tool':'browser_click'}]
        for value in ({}, {'url':1,'title':'x','headings':[]},
                      {'url':'https://docs.python.org/3/library/pathlib.html','title':'x','headings':'x'}):
            self.assertEqual(qa_worker.assess('VERIFIED_DOCUMENT',value,actions,qa_worker.CASES['pathlib'])[1],
                             'BROWSER_METADATA_INVALID')
    def test_qa_rejects_wrong_module_page(self):
        actions=[{'tool':'browser_type'},{'tool':'browser_click'}]
        self.assertEqual(qa_worker.assess('VERIFIED_DOCUMENT',WRONG,actions,qa_worker.CASES['statistics'])[1],
                         'WRONG_TARGET_DOCUMENT_URL')
    def test_qa_rejects_unverified_even_with_right_page(self):
        self.assertEqual(qa_worker.assess('UNVERIFIED',RIGHT,[{'tool':'browser_type'},{'tool':'browser_click'}],qa_worker.CASES['pathlib'])[1],
                         'APP_DID_NOT_VERIFY_DOCUMENT')
    def test_qa_rejects_invalid_action_evidence(self):
        self.assertEqual(qa_worker.assess('VERIFIED_DOCUMENT',RIGHT,['browser_click'],qa_worker.CASES['pathlib'])[1],
                         'BROWSER_ACTION_EVIDENCE_INVALID')
    def test_qa_rejects_more_than_three_actions(self):
        actions=[{'tool':'browser_type'}]*2+[{'tool':'browser_click'}]*2
        self.assertEqual(qa_worker.assess('VERIFIED_DOCUMENT',RIGHT,actions,qa_worker.CASES['pathlib'])[1],
                         'ACTION_BUDGET_EXCEEDED')
    def test_diagnostics_are_bounded_codes(self):
        for text,expected in (
            ('[NOX] DOCUMENT_OPENED_BUT_CONTENT_NOT_VERIFIED','DOCUMENT_METADATA_OR_URL_MISMATCH'),
            ('[NOX] DOCUMENT_LINK_AMBIGUOUS','DOCUMENT_SELECTION_DECLINED'),
            ('[NOX] NO_MATCHING_DOCUMENT_LINK','NO_MATCHING_DOCUMENT_LINK'),
            ('some path C:\\Users\\private\\sensitive','UNCLASSIFIED_BROWSER_FAILURE')):
            self.assertEqual(qa_main.diagnostic_code(text),expected)
    def test_source_tree_digest_changes_when_research_changes(self):
        with tempfile.TemporaryDirectory() as t:
            d=pathlib.Path(t);(d/'agent.py').write_text('a');(d/'research.py').write_text('x')
            first=qa_main.source_tree_sha(d)
            (d/'research.py').write_text('y')
            self.assertNotEqual(first,qa_main.source_tree_sha(d))
    def test_child_output_is_bounded_in_memory(self):
        code,output,timedout=qa_main.subprocess_with_deadline(
            [sys.executable,'-c','import sys;sys.stdout.write("x"*250000)'],10)
        self.assertEqual(code,0);self.assertFalse(timedout)
        self.assertEqual(len(output),qa_main.MAX_BYTES_OUTPUT)
    def test_child_deadline_does_not_retry(self):
        code,output,timedout=qa_main.subprocess_with_deadline(
            [sys.executable,'-c','import time;time.sleep(2)'],0.1)
        self.assertIsNone(code);self.assertTrue(timedout)

if __name__=='__main__':unittest.main()

class HandoffTests(unittest.TestCase):
    def test_projection_drops_paths_and_untrusted_text(self):
        record={'target_path':r'C:\\Users\\private\\secret',
                'verdict':'FAIL_REAL_BROWSER',
                'unit_tests':{'verdict':'PASS'},
                'live_browser':{'verdict':'FAIL','reason':'PRIVATE_PATH'},
                'case_results':[{'id':'pathlib','verdict':'FAIL',
                                 'diagnostic_code':'DOCUMENT_SELECTION_DECLINED',
                                 'unsafe':'C:\\Users\\private'}],
                'source_sha256':'a'*64}
        p=qa_main.handoff_projection(record,'b'*64)
        text=json.dumps(p)
        self.assertNotIn('Users',text)
        self.assertNotIn('secret',text)
        self.assertEqual(p['delivery'],'NOT_SENT')
        self.assertEqual(p['cases'][0]['diagnostic_code'],'DOCUMENT_SELECTION_DECLINED')
    def test_projection_rejects_arbitrary_diagnostic_text(self):
        record={'verdict':'PASS','unit_tests':{'verdict':'PASS'},
                'live_browser':{'verdict':'FAIL'},
                'case_results':[{'id':'pathlib','verdict':'FAIL','diagnostic_code':'hi: C:\\secret'}]}
        p=qa_main.handoff_projection(record,'a'*64)
        self.assertEqual(p['cases'][0]['diagnostic_code'],'OTHER')

class ProcessCleanupTests(unittest.TestCase):
    def test_windows_cleanup_targets_only_owned_process_tree(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        proc=Mock()
        proc.pid=45678
        proc.poll.side_effect=[None,0]
        proc.wait.return_value=0
        mcp=agent.MCP.__new__(agent.MCP)
        mcp.p=proc
        mcp.reader=None
        with patch.object(agent,'os',SimpleNamespace(name='nt')):
            with patch.object(agent.subprocess,'run') as runner:
                mcp.__exit__(None,None,None)
        self.assertEqual(runner.call_args.args[0],['taskkill','/PID','45678','/T','/F'])
        proc.terminate.assert_not_called()
    def test_linux_cleanup_terminates_only_owned_process(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        proc=Mock()
        proc.poll.side_effect=[None,None]
        mcp=agent.MCP.__new__(agent.MCP)
        mcp.p=proc
        mcp.reader=None
        with patch.object(agent,'os',SimpleNamespace(name='posix')):
            mcp.__exit__(None,None,None)
        proc.terminate.assert_called_once()
