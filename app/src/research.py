"""Evidence-based, same-origin navigation from observed search results to a matching document.

Public documentation only. No HTML script execution, external links, downloads, or model-authored selectors.
"""
from __future__ import annotations
import re
from urllib.parse import urlsplit
from pathlib import PurePosixPath
from outcome import core_terms, RE_LINK

OPEN_GOAL = re.compile(r'打开.{0,18}(结果|链接|文档)|阅读.{0,20}(结果|文档|内容)|查看.{0,18}(文档|内容)|\b(open|read|visit|inspect)\b.{0,30}\b(result|documentation|docs|page|article)\b', re.I)
URL_LINE = re.compile(r'(?im)^\s*-?\s*Page URL:\s*(https?://\S+)')
HEADING = re.compile(r'(?im)^\s*-?\s*heading\s+"([^"\n]{1,200})"')
RE_REF_LINK = re.compile(r'^\s*-\s*link\s+"([^"\n]{1,180})"\s+\[ref=(e\d+|f\d+e\d+)\]', re.I | re.M)


def needs_document(goal: str) -> bool:
    return bool(OPEN_GOAL.search(goal))


def unqualified_module_subject(goal: str, query: str = '') -> str | None:
    """For explicit module-level requests, extract an unqualified requested topic.

    The check is generic across documentation sites: it prevents an API method
    such as Snapshot.statistics from masquerading as the statistics module.
    It does not invent selectors, links, navigation targets, or URL paths.
    """
    if not re.search(r'模块|\bmodule\b', goal, re.I):
        return None
    tokens = core_terms(query) or core_terms(goal)
    requested = set(core_terms(goal))
    for token in tokens:
        if token in requested and re.fullmatch(r'[a-z][a-z0-9_]*', token, re.I):
            return token.lower()
    return None


def direct_subject_label(label: str, subject: str) -> bool:
    """Only top-level topic labels, not qualified API names or substrings."""
    return bool(re.match(r'^\s*'+re.escape(subject)+r'(?![\w.])',label,re.I))


def observed_result_links(before: str, after: str, goal: str, query: str = '') -> list[tuple[str,str]]:
    """Return current, new, matching link refs. Must be real observed UI refs."""
    words = core_terms(query) or core_terms(goal)
    requested = core_terms(goal)
    if requested:
        words = [w for w in words if w in requested] or requested
    if not words: return []
    module_subject=unqualified_module_subject(goal,query)
    prior={s.lower() for r,s in RE_LINK.findall(before)}
    matches=[]
    for label,ref in RE_REF_LINK.findall(after):
        if label.lower() in prior: continue
        if any(w in label.lower() for w in words):
            # The module-level target must be the label's *subject*, not an
            # unrelated class or function whose qualified name contains it.
            if module_subject and not direct_subject_label(label,module_subject):
                continue
            matches.append((ref,label))
    return matches[:10]


def document_confirmed(before_search: str, document_snapshot: str, goal: str, query: str) -> bool:
    """Require an actual changed URL plus heading/topic evidence, not a mere query echo."""
    urls_before=URL_LINE.findall(before_search)
    urls_after=URL_LINE.findall(document_snapshot)
    if not urls_before or not urls_after: return False
    b=urlsplit(urls_before[-1]); a=urlsplit(urls_after[-1])
    if (a.scheme,a.netloc)!=(b.scheme,b.netloc):return False
    if (a.path,a.query)==(b.path,b.query):return False
    # A results page is not the opened document.
    if re.search(r'(?:/search(?:/|$)|/find(?:/|$))',a.path,re.I):return False
    if re.search(r'(?:^|[?&])q(?:uery)?=',a.query,re.I):return False
    headings=HEADING.findall(document_snapshot)
    terms=core_terms(query) or core_terms(goal)
    wanted=core_terms(goal)
    if wanted:terms=[t for t in terms if t in wanted] or wanted
    module_subject=unqualified_module_subject(goal,query)
    if module_subject:
        # Confirm a true document landing page, rather than a related method.
        # A post-click URL is *observed evidence*, never a hardcoded navigation.
        last=PurePosixPath(a.path.rstrip('/')).name.lower()
        stem=re.sub(r'\.(?:html?|md|rst|php)$','',last)
        if stem!=module_subject:return False
        title=re.search(r'(?im)^\s*-?\s*Page Title:\s*(.+)$',document_snapshot)
        labels=headings+([title.group(1)] if title else [])
        return any(direct_subject_label(h,module_subject) for h in labels)
    return bool(headings) and bool(terms) and any(any(t in h.lower() for t in terms) for h in headings)
