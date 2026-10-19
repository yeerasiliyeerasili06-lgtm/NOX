"""NOX: conservative task-outcome verifier for public, read-only web discovery.

This module deliberately does not ask the language model whether it succeeded.
It inspects the observed post-action accessibility snapshot.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

RE_LINK = re.compile(r'^\s*-\s*(link|heading)\s+"([^"\n]{1,180})"', re.I | re.M)
RE_URL = re.compile(r'(?im)^\s*-?\s*Page URL:\s*(https?://\S+)')
RE_TITLE = re.compile(r'(?im)^\s*-?\s*Page Title:\s*(.+)$')
STOP_TERMS = {'this', 'that', 'website', 'search', 'find', 'look', 'docs', 'documentation',
              'document', 'manual', 'tutorial', 'with', 'about', 'the', 'for', 'and',
              'python', 'page', 'using', 'read', 'open', 'here', 'guide', 'latest', 'site'}

@dataclass(frozen=True)
class Result:
    verified: bool
    kind: str
    explanation: str

def core_terms(text):
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9_.+-]{3,}', text.lower())
    words = [w for w in words if w not in STOP_TERMS]
    return sorted(set(words), key=lambda x:(-len(x),x))[:5]

def is_search_goal(goal):
    return bool(re.search(r'\b(search|find|look up|lookup)\b|搜索|查找|检索|поиск',goal,re.I))

def post_action_result(before, after, goal, last_action, query=''):
    """Only declare success when a *newly observed* result supports a search goal.

    Caller may report intermediate success separately. A search text field echo is
    NEVER enough to claim task completion.
    """
    if not isinstance(after,str) or not after.strip():
        return Result(False,'NO_OBSERVATION','post-action snapshot unavailable')
    if not is_search_goal(goal):
        return Result(False,'NOT_EVALUABLE','goal is not a supported search-result task')
    if last_action not in ('browser_click','browser_type'):
        return Result(False,'NO_ACTION','no eligible action was performed')
    requested = core_terms(goal)
    searched = core_terms(query)
    # A model cannot search an unrelated term and claim success from unrelated links.
    if requested and searched and not any(t in requested for t in searched):
        return Result(False,'QUERY_NOT_GROUNDED_IN_GOAL','model query diverges from user goal')
    terms = [t for t in searched if t in requested] if requested and searched else (requested or searched)
    if not terms:
        return Result(False,'NO_DISTINCTIVE_KEYWORD','cannot independently identify target')
    old = {name.lower() for role,name in RE_LINK.findall(before)}
    matches=[]
    for role,name in RE_LINK.findall(after):
        label=name.lower()
        if label in old:
            continue
        if any(t in label for t in terms):
            matches.append((role.lower(),name))
    # A newly observed result *link* is stronger than a heading that may just
    # echo the user's search query; headings do not establish completion.
    links=[name for role,name in matches if role=='link']
    if links:
        return Result(True,'SEARCH_RESULT_LINK_OBSERVED',f'{len(links)} new matching result link(s) observed')
    return Result(False,'RESULT_NOT_PROVEN','no newly observed matching result link')

def page_signature(snapshot):
    """An observation fingerprint; excludes volatile refs and whitespace."""
    normalized=re.sub(r'\[ref=[^\]]+\]','',snapshot or '')
    normalized=' '.join(normalized.split())[:20000]
    import hashlib
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
