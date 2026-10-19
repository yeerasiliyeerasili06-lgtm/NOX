"""Regression: avoid method names that contain a requested module topic."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
import research

GOAL='在这个网站搜索 Python 标准库 statistics 模块文档，并打开对应文档'
BEFORE='- Page URL: https://docs.python.org/3/\n- Page Title: Python docs\n'
AFTER='''- Page URL: https://docs.python.org/3/search.html?q=statistics
- Page Title: Search results
- link "tracemalloc.Snapshot.statistics" [ref=e1]
- link "statistics — Mathematical statistics functions" [ref=e2]
- link "statistics.mean" [ref=e3]
'''
RIGHT='''- Page URL: https://docs.python.org/3/library/statistics.html
- Page Title: statistics — Mathematical statistics functions
- heading "statistics — Mathematical statistics functions" [level=1]
'''
WRONG='''- Page URL: https://docs.python.org/3/library/tracemalloc.html
- Page Title: tracemalloc.Snapshot.statistics
- heading "tracemalloc.Snapshot.statistics" [level=1]
'''
class ModuleDisambiguationTests(unittest.TestCase):
    def test_module_only_observed_landing_page_link(self):
        self.assertEqual(research.observed_result_links(BEFORE,AFTER,GOAL,'statistics'),
                         [('e2','statistics — Mathematical statistics functions')])
    def test_missing_module_landing_link_fails_closed(self):
        self.assertEqual(research.observed_result_links(BEFORE,AFTER.replace('statistics — Mathematical statistics functions','unrelated'),GOAL,'statistics'),[])
    def test_both_url_and_heading_must_be_exact_module_subject(self):
        self.assertTrue(research.document_confirmed(AFTER,RIGHT,GOAL,'statistics'))
        self.assertFalse(research.document_confirmed(AFTER,WRONG,GOAL,'statistics'))
        self.assertFalse(research.document_confirmed(AFTER,RIGHT.replace('/statistics.html','/tracemalloc.html'),GOAL,'statistics'))
    def test_generic_non_module_intent_keeps_existing_behavior(self):
        self.assertEqual(len(research.observed_result_links(BEFORE,AFTER,'查找 statistics 文档','statistics')),3)

if __name__=='__main__':unittest.main()
