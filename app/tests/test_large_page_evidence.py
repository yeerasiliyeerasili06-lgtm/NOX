"""No external I/O: test huge Playwright payloads and generic evidence gating."""
import io, json, pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'src'))
import agent, research

class LargePageTests(unittest.TestCase):
    def test_capped_message_drains_without_losing_next_rpc(self):
        large=b'{"jsonrpc":"2.0","id":8,"result":{"content":"'+b'X'*25000+b'"}}\n'
        after=b'{"jsonrpc":"2.0","id":9,"result":{"ok":true}}\n'
        stream=io.BytesIO(large+after)
        oversized=agent.capped_jsonrpc_line(stream,limit=1500)
        self.assertEqual(oversized,{'id':8,'_nox_oversize':True})
        self.assertEqual(agent.capped_jsonrpc_line(stream)['id'],9)
    def test_capped_message_recovers_rpc_id_at_tail(self):
        big=b'{"jsonrpc":"2.0","result":{"body":"'+b'X'*30000+b'"},"id":12}\n'
        self.assertEqual(agent.capped_jsonrpc_line(io.BytesIO(big),limit=1200),
                         {'id':12,'_nox_oversize':True})
    def test_bad_large_response_is_not_success(self):
        big=b'{"body":"'+b'X'*10000+b'"}\n'
        self.assertEqual(agent.capped_jsonrpc_line(io.BytesIO(big),limit=1000),
                         {'_nox_unidentified_oversize':True})
    def test_metadata_only_returns_small_public_signals(self):
        raw='### Result\n'+json.dumps({'url':'https://docs.python.org/3/library/pathlib.html',
            'title':'pathlib — Object-oriented filesystem paths',
            'headings':['pathlib — Object-oriented filesystem paths','Concrete paths']})+'\n### Ran Playwright code\n() => ...'
        compact=agent.compact_document_evidence(raw)
        self.assertTrue(research.document_confirmed('- Page URL: https://docs.python.org/3/search.html?q=pathlib',
             compact,'在这个网站搜索 pathlib 文档，并打开对应文档','pathlib'))
        self.assertLess(len(compact),500)
    def test_page_topic_absent_is_not_verified(self):
        raw='### Result\n'+json.dumps({'url':'https://docs.python.org/3/library/other.html',
            'title':'other', 'headings':['This is not the requested topic']})
        compact=agent.compact_document_evidence(raw)
        self.assertFalse(research.document_confirmed('- Page URL: https://docs.python.org/3/search.html?q=pathlib',
             compact,'在这个网站搜索 pathlib 文档，并打开对应文档','pathlib'))
    def test_cross_site_url_never_verified(self):
        raw='### Result\n'+json.dumps({'url':'https://evil.example.org/3/library/pathlib.html',
            'title':'pathlib', 'headings':['pathlib']})
        compact=agent.compact_document_evidence(raw)
        with self.assertRaises(agent.NoxStop):
            agent.require_origin(compact,'https://docs.python.org')
    def test_invalid_or_secret_metadata_not_treated_as_success(self):
        for text in ('No Result','### Result\n{}', '### Result\n{"url":100,"title":"x","headings":[]}'):
            with self.subTest(text=text):
                with self.assertRaises(agent.NoxStop):agent.compact_document_evidence(text)
    def test_no_dynamic_eval_scripts_or_other_privilege(self):
        obj=agent.MCP(command=['fake'])
        obj.tools={'browser_evaluate':{'inputSchema':{'properties':{'function':{}}}}}
        with self.assertRaisesRegex(agent.NoxStop,'DYNAMIC_SCRIPT_NOT_ALLOWED'):
            obj.tool('browser_evaluate',{'function':'() => fetch("https://evil.example")'})
        with self.assertRaisesRegex(agent.NoxStop,'TOOL_NOT_ALLOWED'):
            obj.tool('browser_run_code_unsafe',{'code':'hi'})
    def test_never_log_success_for_large_click_ack(self):
        obj=agent.MCP(command=['fake'])
        obj.tools={'browser_click':{}}
        obj.call=lambda *args,**kwargs:{'_nox_oversize':True}
        text=obj.tool('browser_click',{'target':'e5'})
        self.assertIn('outcome unknown',text)
        self.assertNotIn('DOCUMENT_VERIFIED',text)

if __name__=='__main__': unittest.main()
