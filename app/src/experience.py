"""Minimal evidence-gated local experience memory, never stores task text or page bodies."""
from pathlib import Path
from contextlib import closing
import sqlite3
import time
import re

class ExperienceStore:
    def __init__(self, path):
        self.path=Path(path)

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db=sqlite3.connect(self.path, timeout=3)
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS verified_actions(
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                domain TEXT NOT NULL,
                intent TEXT NOT NULL,
                action TEXT NOT NULL,
                control_kind TEXT NOT NULL,
                result_kind TEXT NOT NULL)''')
            return db
        except BaseException:
            db.close()
            raise

    def save_verified(self, domain, action, role, result_kind):
        if result_kind != 'SEARCH_RESULT_LINK_OBSERVED':
            return False
        if action not in ('browser_click','browser_type') or role not in ('textbox','searchbox','button','link','tab','menuitem'):
            return False
        with closing(self._db()) as db, db:
            db.execute('''INSERT INTO verified_actions(ts,domain,intent,action,control_kind,result_kind)
                VALUES(?,?,?,?,?,?)''',(int(time.time()),domain,'search',action,role,result_kind))
        return True

    def import_legacy_readonly(self, source):
        """One-time, whitelisted import; do not copy old raw chats or private text."""
        source=Path(source)
        if not source.is_file():return None
        with closing(self._db()) as current, current:
            current.execute('''CREATE TABLE IF NOT EXISTS migrations(name TEXT PRIMARY KEY,ts INTEGER)''')
            if current.execute("SELECT 1 FROM migrations WHERE name='web07'").fetchone():
                return None
            # Source connection never requests write mode. A corrupt/mismatching source
            # must fail closed rather than silently introducing untrusted records.
            uri=source.resolve().as_uri()+'?mode=ro'
            with closing(sqlite3.connect(uri,uri=True,timeout=2)) as old:
                schema={row[1] for row in old.execute('PRAGMA table_info(verified_actions)')}
                if not {'domain','intent','action','control_kind','result_kind','ts'}.issubset(schema):
                    raise ValueError('LEGACY_EXPERIENCE_SCHEMA_UNSUPPORTED')
                rows=old.execute("SELECT ts,domain,intent,action,control_kind,result_kind FROM verified_actions LIMIT 500").fetchall()
            count=0
            for ts,domain,intent,action,kind,result in rows:
                if (isinstance(ts,int) and isinstance(domain,str) and len(domain)<=253
                    and re.fullmatch(r'[a-z0-9.-]+',domain)
                    and intent=='search' and result=='SEARCH_RESULT_LINK_OBSERVED'
                    and action in ('browser_click','browser_type')
                    and kind in ('textbox','searchbox','button','link','tab','menuitem')):
                    current.execute('''INSERT INTO verified_actions(ts,domain,intent,action,control_kind,result_kind)
                                  VALUES(?,?,?,?,?,?)''',(ts,domain,intent,action,kind,result))
                    count+=1
            current.execute("INSERT INTO migrations(name,ts) VALUES('web07',?)",(int(time.time()),))
        return count

    def hint(self, domain, intent='search'):
        if not self.path.exists():
            return None
        with closing(self._db()) as db:
            row=db.execute('''SELECT action,control_kind,COUNT(*) as n FROM verified_actions
                 WHERE domain=? AND intent=? GROUP BY action,control_kind ORDER BY n DESC LIMIT 1''',(domain,intent)).fetchone()
        return tuple(row) if row else None
