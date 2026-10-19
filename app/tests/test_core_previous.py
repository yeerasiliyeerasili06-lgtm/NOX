"""No network/model/GUI calls: fail-closed tests for Web Task Core."""
import importlib.util, pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"src"))
P=pathlib.Path(__file__).resolve().parents[1]/'src'/'agent.py'
S=importlib.util.spec_from_file_location('nox6',P)
M=importlib.util.module_from_spec(S);sys.modules['nox6']=M;S.loader.exec_module(M)
SNAP='''- Page URL: https://www.example.org/
- Page Title: Example Docs
- banner:
  - link "Donate" [ref=e1]
  - button "Search" [ref=e2]
  - textbox "Search site" [ref=e3]
  - link "Documentation" [ref=e4]
  - link "Install tools" [ref=e5]
  - link "Tkinter GUI" [ref=e6]
  - button "Delete account" [ref=e7]
'''
GOAL='在这个网站搜索 tkinter GUI 文档'
class CoreTests(unittest.TestCase):
    def test_url(self):
        self.assertEqual(M.checked_url('https://www.example.org/path'),'https://www.example.org/path')
        for u in ['http://example.org/','file:///x','https://localhost','https://10.1.1.1',
                  'https://name:secret@example.org','https://example.org:9899']:
            with self.subTest(url=u),self.assertRaises(M.NoxStop):M.checked_url(u)
    def test_origin(self):
        M.require_origin(SNAP,'https://www.example.org')
        with self.assertRaises(M.NoxStop):M.require_origin(SNAP,'https://other.example.org')
    def test_dynamic_extract(self):
        self.assertEqual(M.extract_controls(SNAP)['e3'],('textbox','Search site'))
        self.assertNotIn('e99',M.extract_controls(SNAP))
    def test_search_candidates_filter_risky(self):
        cs=M.candidates_for(SNAP,GOAL)
        self.assertTrue(any(c.ref=='e3' and c.action=='browser_type' for c in cs))
        self.assertFalse(any(c.ref in ('e1','e5','e7') for c in cs))
        self.assertEqual([c.index for c in cs],list(range(1,len(cs)+1)))
    def test_model_cannot_pick_raw_ref(self):
        cs=M.candidates_for(SNAP,GOAL)
        with self.assertRaises(M.NoxStop):M.validate_choice({'choice':'e3','text':'abc','explanation':'x'},cs,GOAL)
        with self.assertRaises(M.NoxStop):M.validate_choice({'choice':99,'text':'abc','explanation':'x'},cs,GOAL)
        with self.assertRaises(M.NoxStop):M.validate_choice({'choice':1,'text':'abc','explanation':'x','ref':'e3'},cs,GOAL)
    def test_none(self):
        cs=M.candidates_for(SNAP,GOAL)
        self.assertIsNone(M.validate_choice({'choice':0,'text':'','explanation':'cannot decide'},cs,GOAL))
        with self.assertRaises(M.NoxStop):M.validate_choice({'choice':0,'text':'random','explanation':''},cs,GOAL)
    def test_click_cannot_have_text(self):
        cs=M.candidates_for(SNAP,GOAL)
        c=next(c for c in cs if c.action=='browser_click')
        with self.assertRaises(M.NoxStop):M.validate_choice({'choice':c.index,'text':'unwanted','explanation':''},cs,GOAL)
    def test_type_has_safe_query(self):
        cs=M.candidates_for(SNAP,GOAL)
        c=next(c for c in cs if c.action=='browser_type')
        got=M.validate_choice({'choice':c.index,'text':'tkinter GUI','explanation':'search'},cs,GOAL)
        self.assertEqual(got.ref,'e3')
        for val in ['', 'buy now', '\n', 'x'*101]:
            with self.subTest(val=val),self.assertRaises(M.NoxStop):
                M.validate_choice({'choice':c.index,'text':val,'explanation':'x'},cs,GOAL)
    def test_type_disallowed_without_search_goal(self):
        cs=M.candidates_for(SNAP,'Read documentation')
        c=next(c for c in cs if c.action=='browser_type')
        with self.assertRaises(M.NoxStop):M.validate_choice({'choice':c.index,'text':'abc','explanation':''},cs,'Read documentation')
    def test_schema_restricts_to_current_candidates(self):
        cs=M.candidates_for(SNAP,GOAL)
        schema=M.choice_schema(cs)
        self.assertEqual(schema['properties']['choice']['enum'],[0]+[c.index for c in cs])
    def test_build_arg_target(self):
        c=next(c for c in M.candidates_for(SNAP,GOAL) if c.action=='browser_type')
        m={'inputSchema':{'properties':{'target':{},'text':{},'submit':{}},'required':['target','text']}}
        self.assertEqual(M.tool_arguments(m,c,'tkinter',True),{'target':c.ref,'text':'tkinter','submit':True})
    def test_build_arg_ref_and_element(self):
        c=next(c for c in M.candidates_for(SNAP,GOAL) if c.action=='browser_type')
        m={'inputSchema':{'properties':{'ref':{},'element':{},'text':{}},'required':['ref','element','text']}}
        self.assertEqual(M.tool_arguments(m,c,'tkinter')['ref'],c.ref)
    def test_reject_unsupported_upstream_schema(self):
        c=M.candidates_for(SNAP,GOAL)[0]
        with self.assertRaises(M.NoxStop):M.tool_arguments({'inputSchema':{'properties':{'selector':{}},'required':['selector']}},c,'')
    def test_readonly_intent(self):
        for g in ['不要点击，只观察这个网站','Observe only; do not click or modify anything']:
            self.assertTrue(M.read_only_goal(g))
        self.assertFalse(M.read_only_goal(GOAL))
    def test_no_side_effect_if_no_choice(self):
        class Fake:
            inst=None
            def __init__(self):self.calls=[];Fake.inst=self;self.tools={}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def tool(self,n,a):self.calls.append(n);return SNAP
        def model(g,choices,remaining):return {'choice':0,'text':'','explanation':'no safe action'},0.01,{}
        M.run('https://www.example.org/',GOAL,Fake,model)
        self.assertNotIn('browser_click',Fake.inst.calls)
        self.assertNotIn('browser_type',Fake.inst.calls)
    def test_dynamic_search_action_and_readback(self):
        after=SNAP+'- text: tkinter GUI\n'
        class Fake:
            inst=None
            def __init__(self):
                Fake.inst=self;self.calls=[];self.changed=False
                self.tools={'browser_type':{'inputSchema':{'properties':{'target':{},'text':{},'submit':{}},'required':['target','text']}},
                  'browser_click':{'inputSchema':{'properties':{'target':{}},'required':['target']}}}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def tool(self,n,a):
                self.calls.append((n,a))
                if n=='browser_type':self.changed=True;return after
                return after if self.changed else SNAP
        def model(g,choices,remaining):
            c=next(c for c in choices if c.action=='browser_type')
            return {'choice':c.index,'text':'tkinter GUI','explanation':'search field'},.01,{}
        M.run('https://www.example.org/',GOAL,Fake,model)
        executed=[x for x in Fake.inst.calls if x[0]=='browser_type']
        self.assertEqual(len(executed),1)
        self.assertEqual(executed[0][1]['target'],'e3')
    def test_fresh_control_identity_check(self):
        changed=SNAP.replace('textbox "Search site" [ref=e3]','textbox "Password" [ref=e3]')
        class Fake:
            inst=None
            def __init__(self):Fake.inst=self;self.n=0;self.calls=[];self.tools={}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def tool(self,n,a):
                self.calls.append(n)
                if n=='browser_snapshot':
                    self.n+=1
                    return SNAP if self.n==1 else changed
                return SNAP
        def model(g,choices,remaining):
            c=next(c for c in choices if c.action=='browser_type')
            return {'choice':c.index,'text':'tkinter','explanation':'search'},.01,{}
        with self.assertRaisesRegex(M.NoxStop,'TARGET_CHANGED'):
            M.run('https://www.example.org/',GOAL,Fake,model)
        self.assertNotIn('browser_type',Fake.inst.calls)

if __name__=='__main__':unittest.main(verbosity=2)
