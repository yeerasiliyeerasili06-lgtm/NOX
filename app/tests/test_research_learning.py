"""Offline tests, no browser/LLM or user files touched."""
import pathlib, sys, tempfile, sqlite3, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
import agent, research, outcome
from experience import ExperienceStore

GOAL='在这个网站搜索 pathlib 文档并打开对应文档'
HOME='''- Page URL: https://www.example.org/
- Page Title: Example docs
- textbox "Search docs" [ref=e1]
- link "Install tools" [ref=e6]
'''
RESULTS='''- Page URL: https://www.example.org/search?q=pathlib
- Page Title: Search results
- textbox "Search docs" [ref=e2]
- link "pathlib documentation and path management" [ref=e4]
- link "Contact" [ref=e5]
'''
DOC='''- Page URL: https://www.example.org/library/pathlib.html
- Page Title: pathlib — Object-oriented filesystem paths
- heading "pathlib — Object-oriented filesystem paths" [level=1]
- paragraph: This module offers classes representing filesystem paths
'''
class ResearchTests(unittest.TestCase):
    def test_detect_open_doc(self):
        self.assertTrue(research.needs_document(GOAL))
        self.assertFalse(research.needs_document('在这个网站搜索 pathlib 文档'))
    def test_select_only_new_matching_links(self):
        self.assertEqual(research.observed_result_links(HOME,RESULTS,GOAL,'pathlib'),
                         [('e4','pathlib documentation and path management')])
        self.assertEqual(research.observed_result_links(HOME,RESULTS,GOAL,'unrelated'),
                         [('e4','pathlib documentation and path management')])
    def test_read_doc_requires_heading_and_same_origin_new_url(self):
        self.assertTrue(research.document_confirmed(RESULTS,DOC,GOAL,'pathlib'))
        self.assertFalse(research.document_confirmed(RESULTS,RESULTS,GOAL,'pathlib'))
        self.assertFalse(research.document_confirmed(RESULTS,DOC.replace('heading "pathlib','heading "Random'),GOAL,'pathlib'))
        self.assertFalse(research.document_confirmed(RESULTS,DOC.replace('www.example.org','evil.example.org'),GOAL,'pathlib'))
    def test_unrelated_results_not_evidence_of_goal(self):
        junk=RESULTS.replace('pathlib documentation and path management','free images collection')
        r=outcome.post_action_result(HOME,junk,GOAL,'browser_type','images')
        self.assertFalse(r.verified)
        self.assertEqual(r.kind,'QUERY_NOT_GROUNDED_IN_GOAL')
    def test_end_to_end_search_then_open_verified_document(self):
        class Memory:
            def __init__(self):self.writes=[]
            def hint(self,domain):return None
            def save_verified(self,*args):self.writes.append(args);return True
        class Fake:
            def __init__(self):
                self.position='home';self.calls=[]
                props={'target':{},'element':{},'text':{},'submit':{}}
                self.tools={'browser_click':{'inputSchema':{'properties':props,'required':['target']}},
                            'browser_evaluate':{'inputSchema':{'properties':{'function':{}},'required':['function']}},
                            'browser_type':{'inputSchema':{'properties':props,'required':['target','text']}}}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def tool(self,name,args):
                self.calls.append((name,args))
                if name=='browser_type':self.position='results'
                if name=='browser_click':
                    assert args['target']=='e4'
                    self.position='document'
                if name=='browser_evaluate':
                    assert args=={'function':agent.PAGE_META_FN}
                    return '### Result\n'+agent.json.dumps({'url':'https://www.example.org/library/pathlib.html','title':'pathlib — Object-oriented filesystem paths','headings':['pathlib — Object-oriented filesystem paths']})
                return {'home':HOME,'results':RESULTS,'document':DOC}[self.position]
        mock=Fake();memory=Memory()
        def model(goal,cs,budget):
            first=next(x for x in cs if x.action=='browser_type')
            return {'choice':first.index,'text':'pathlib','explanation':'search'},.01,{}
        result=agent.run('https://www.example.org/',GOAL,lambda:mock,model,memory)
        self.assertEqual(result,'VERIFIED_DOCUMENT')
        self.assertEqual([n for n,_ in mock.calls].count('browser_type'),1)
        self.assertEqual([n for n,_ in mock.calls].count('browser_click'),1)
        self.assertEqual(len(memory.writes),1)
    def test_import_verified_legacy_once_no_destructive_copy(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)
            old=ExperienceStore(root/'old.sqlite3')
            old.save_verified('docs.python.org','browser_type','textbox','SEARCH_RESULT_LINK_OBSERVED')
            store=ExperienceStore(root/'shared.sqlite3')
            self.assertEqual(store.import_legacy_readonly(root/'old.sqlite3'),1)
            self.assertEqual(store.hint('docs.python.org'),('browser_type','textbox',1))
            self.assertIsNone(store.import_legacy_readonly(root/'old.sqlite3'))
            self.assertEqual(store.hint('docs.python.org'),('browser_type','textbox',1))
            self.assertEqual(old.hint('docs.python.org'),('browser_type','textbox',1))
    def test_on_empty_migration_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t); store=ExperienceStore(root/'shared.sqlite3')
            self.assertIsNone(store.import_legacy_readonly(root/'not_there.sqlite3'))
            self.assertFalse((root/'shared.sqlite3').exists())

if __name__=='__main__':unittest.main(verbosity=2)

class AmbiguousSelectionTests(unittest.TestCase):
    def test_two_results_require_real_model_selection(self):
        from unittest.mock import patch
        many=RESULTS.replace('  - link "Contact"','  - link "Contact"')+'- link "pathlib file access examples" [ref=e9]\n'
        class Fake:
            def __init__(self):
                self.pos=0;self.calls=[]
                self.tools={'browser_type':{'inputSchema':{'properties':{'target':{},'text':{},'submit':{}},'required':['target','text']}},
                            'browser_click':{'inputSchema':{'properties':{'target':{},'element':{}},'required':['target']}},
                            'browser_evaluate':{'inputSchema':{'properties':{'function':{}},'required':['function']}}}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def tool(self,n,args):
                self.calls.append((n,args))
                if n=='browser_type':self.pos=1
                elif n=='browser_click':self.pos=2
                elif n=='browser_evaluate':
                    return '### Result\n'+agent.json.dumps({'url':'https://www.example.org/library/pathlib.html','title':'pathlib — Object-oriented filesystem paths','headings':['pathlib — Object-oriented filesystem paths']})
                return (HOME,many,DOC)[self.pos]
        def search_model(goal,cs,remaining):
            c=next(c for c in cs if c.action=='browser_type')
            return {'choice':c.index,'text':'pathlib','explanation':'search'},.01,{}
        class Memory:
            def hint(self,d):return None
            def save_verified(self,*a):return True
        def doc_model(goal,cs,budget):
            c=next(c for c in cs if c.name=='pathlib documentation and path management')
            return {'choice':c.index,'text':'','explanation':'best matching docs'},.02,{}
        fake=Fake()
        with patch.object(agent,'ask_model',doc_model):
            result=agent.run('https://www.example.org/',GOAL,lambda:fake,search_model,Memory())
        self.assertEqual(result,'VERIFIED_DOCUMENT')
        self.assertEqual([n for n,_ in fake.calls].count('browser_click'),1)
    def test_model_can_decline_ambiguous_links(self):
        # No model must be forced into clicking an uncertain result.
        from unittest.mock import patch
        many=RESULTS+'- link "pathlib quick guide" [ref=e9]\n'
        class Fake:
            def __init__(self):
                self.pos=0;self.calls=[]
                self.tools={'browser_type':{'inputSchema':{'properties':{'target':{},'text':{},'submit':{}},'required':['target','text']}},
                            'browser_click':{'inputSchema':{'properties':{'target':{}},'required':['target']}}}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def tool(self,n,args):
                self.calls.append(n)
                if n=='browser_type':self.pos=1
                return (HOME,many)[self.pos]
        def model(goal,cs,remaining):
            c=next(c for c in cs if c.action=='browser_type')
            return {'choice':c.index,'text':'pathlib','explanation':'search'},.01,{}
        class Memory:
            def hint(self,d):return None
            def save_verified(self,*a):raise AssertionError('Unverified run must not be learned')
        fake=Fake()
        with patch.object(agent,'ask_model',return_value=({'choice':0,'text':'','explanation':'uncertain'},.01,{})):
            result=agent.run('https://www.example.org/',GOAL,lambda:fake,model,Memory())
        self.assertEqual(result,'UNVERIFIED')
        self.assertNotIn('browser_click',fake.calls)
