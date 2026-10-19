"""Offline integrity preflight for the extracted NOX QA candidate."""
from __future__ import annotations
import hashlib
import json
import pathlib
import sys

ROOT=pathlib.Path(__file__).resolve().parent
MANIFEST=ROOT/'manifest.json'

def verify():
    if not MANIFEST.is_file() or MANIFEST.is_symlink():
        raise ValueError('MANIFEST_MISSING')
    data=json.loads(MANIFEST.read_text(encoding='utf-8'))
    files=data.get('files')
    if not isinstance(files,dict) or not files:
        raise ValueError('MANIFEST_INVALID')
    for rel,expected in files.items():
        if not isinstance(rel,str) or not isinstance(expected,str) or len(expected)!=64:
            raise ValueError('MANIFEST_ENTRY_INVALID')
        pure=pathlib.PurePosixPath(rel)
        if pure.is_absolute() or '..' in pure.parts or '\\' in rel or rel.startswith('.'):
            raise ValueError('MANIFEST_PATH_INVALID')
        p=ROOT.joinpath(*pure.parts)
        if not p.is_file() or p.is_symlink():
            raise ValueError('FILE_MISSING_OR_UNSAFE:'+rel)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('FILE_HASH_MISMATCH:'+rel)
    # Reject injected Python files in executable source paths.
    for directory in (ROOT,ROOT/'app'/'src',ROOT/'app'/'tests',ROOT/'tests'):
        for path in directory.glob('*.py'):
            rel=path.relative_to(ROOT).as_posix()
            if rel not in files:
                raise ValueError('UNEXPECTED_PYTHON_FILE:'+rel)
    return len(files)

if __name__=='__main__':
    try:
        count=verify()
        print('PACKAGE_INTEGRITY_PASS | verified_files='+str(count))
    except (ValueError,OSError,TypeError,KeyError,json.JSONDecodeError) as exc:
        print('PACKAGE_INTEGRITY_FAIL | '+str(exc))
        sys.exit(2)
