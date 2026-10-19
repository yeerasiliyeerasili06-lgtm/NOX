import pathlib, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
import outcome
from experience import ExperienceStore
import agent

INITIAL='''- Page URL: https://www.example.org/
- Page Title: Home
- textbox "Search" [ref=e1]
- link "Documentation" [ref=e2]
- button "Delete account" [ref=e3]
'''
RESULTS='''- Page URL: https://www.example.org/search?q=tkinter
- Page Title: Search results
- textbox "Search" [ref=e11]: tkinter
- link "Tkinter Python graphical user interface documentation" [ref=e12]
- link "Support" [ref=e13]
'''
GOAL='在这个网站搜索 tkinter GUI 文档'

class OutcomeTests(unittest.TestCase):
    def test_query_echo_is_not_task_success(self):
        after=INITIAL+'- textbox "Search" [ref=e3]: tkinter GUI\n'
        r=outcome.post_action_result(INITIAL,after,GOAL,'browser_type','tkinter GUI')
        self.assertFalse(r.verified)
    def test_visible_new_result_link_is_evidence(self):
        r=outcome.post_action_result(INITIAL,RESULTS,GOAL,'browser_type','tkinter GUI')
        self.assertTrue(r.verified)
        self.assertEqual(r.kind,'SEARCH_RESULT_LINK_OBSERVED')
    def test_preexisting_link_does_not_count(self):
        old=INITIAL+'- link "Tkinter docs" [ref=e8]\n'
        new=old+'- text: searched tkinter\n'
        self.assertFalse(outcome.post_action_result(old,new,GOAL,'browser_type','tkinter').verified)
    def test_not_success_for_non_search_goal(self):
        self.assertFalse(outcome.post_action_result(INITIAL,RESULTS,'Click the About page','browser_click').verified)
    def test_no_distinctive_terms(self):
        self.assertFalse(outcome.post_action_result(INITIAL,RESULTS,'搜索文档','browser_click').verified)
    def test_no_action(self):
        self.assertFalse(outcome.post_action_result(INITIAL,RESULTS,GOAL,'none').verified)
    def test_signature_stable_across_reassigned_refs(self):
        a=INITIAL.replace('e1','e100')
        self.assertEqual(outcome.page_signature(a),outcome.page_signature(INITIAL))

class ExperienceTests(unittest.TestCase):
    def test_only_verified_records_written(self):
        with tempfile.TemporaryDirectory() as temp:
            p=pathlib.Path(temp)/'memory.db'
            store=ExperienceStore(p)
            self.assertFalse(store.save_verified('example.org','browser_type','textbox','FAILED'))
            self.assertFalse(p.exists())
            self.assertTrue(store.save_verified('example.org','browser_type','textbox','SEARCH_RESULT_LINK_OBSERVED'))
            self.assertEqual(store.hint('example.org'),('browser_type','textbox',1))
            self.assertIsNone(store.hint('other.org'))
    def test_scoped_prior_only_reranks_observed(self):
        snap='''- Page URL: https://example.org/\n- textbox "Search docs" [ref=e1]\n- searchbox "Search docs" [ref=e2]\n'''
        initial=agent.candidates_for(snap,GOAL)
        hinted=agent.candidates_for(snap,GOAL,('browser_type','textbox',2))
        self.assertEqual({c.ref for c in hinted},{c.ref for c in initial})
        self.assertEqual(hinted[0].ref,'e1')

class StructuralDecisionTests(unittest.TestCase):
    def test_unique_search_input_saves_model_call(self):
        cs=agent.candidates_for(INITIAL,GOAL)
        plan=agent.fast_unambiguous_search(GOAL,cs)
        self.assertEqual(plan['text'],'tkinter GUI')
        self.assertEqual(next(c for c in cs if c.index==plan['choice']).role,'textbox')
    def test_ambiguous_inputs_must_use_model(self):
        extra=INITIAL+'- textbox "Search another site" [ref=e5]\n'
        self.assertIsNone(agent.fast_unambiguous_search(GOAL,agent.candidates_for(extra,GOAL)))
    def test_chinese_only_keyword_uses_model(self):
        g='在网站里搜索桌面窗口教程'
        self.assertIsNone(agent.fast_unambiguous_search(g,agent.candidates_for(INITIAL,g)))
    def test_instructions_without_actions_are_read_only(self):
        goal='Observe only: search for tkinter but do not click or modify anything'
        self.assertIsNone(agent.fast_unambiguous_search(goal,agent.candidates_for(INITIAL,goal)))


class FlowTests(unittest.TestCase):
    def test_model_decides_from_dynamic_candidates_with_verified_result(self):
        class Memory:
            def __init__(self):self.writes=[]
            def hint(self,h):return None
            def save_verified(self,*args):self.writes.append(args);return True
        class Fake:
            inst=None
            def __init__(self):
                Fake.inst=self;self.calls=[];self.used=False
                self.tools={'browser_type':{'inputSchema':{'properties':{'target':{},'text':{},'submit':{}},'required':['target','text']}},
                            'browser_click':{'inputSchema':{'properties':{'target':{}},'required':['target']}}}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def tool(self,name,args):
                self.calls.append((name,args))
                if name=='browser_type':self.used=True
                return RESULTS if self.used else INITIAL
        def model(goal,choices,rem):
            candidate=next(x for x in choices if x.action=='browser_type')
            return {'choice':candidate.index,'text':'tkinter GUI','explanation':'search'},0.01,{}
        memory=Memory()
        ret=agent.run('https://www.example.org/',GOAL,Fake,model,memory)
        self.assertEqual(ret,'VERIFIED')
        self.assertEqual(len(memory.writes),1)
        acts=[(n,a) for n,a in Fake.inst.calls if n=='browser_type']
        self.assertEqual(len(acts),1)
        self.assertEqual(acts[0][1]['target'],'e1')
    def test_no_progress_stops_without_replay_or_learning(self):
        class Memory:
            def __init__(self):self.writes=[]
            def hint(self,h):return None
            def save_verified(self,*args):self.writes.append(args);return True
        class Fake:
            inst=None
            def __init__(self):
                Fake.inst=self;self.calls=[]
                self.tools={'browser_type':{'inputSchema':{'properties':{'target':{},'text':{}},'required':['target','text']}}}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def tool(self,name,args):self.calls.append(name);return INITIAL
        def model(goal,choices,rem):
            c=next(x for x in choices if x.action=='browser_type')
            return {'choice':c.index,'text':'tkinter GUI','explanation':'search'},.01,{}
        memory=Memory()
        with self.assertRaisesRegex(agent.NoxStop,'NO_OBSERVABLE_PROGRESS'):
            agent.run('https://www.example.org/',GOAL,Fake,model,memory)
        self.assertEqual(Fake.inst.calls.count('browser_type'),1)
        self.assertEqual(memory.writes,[])

if __name__=='__main__':unittest.main(verbosity=2)
