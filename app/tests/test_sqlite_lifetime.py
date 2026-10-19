"""Regression: every SQLite connection must close on Windows, including error paths."""
import pathlib
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
import experience
from experience import ExperienceStore


class TrackedConnection(sqlite3.Connection):
    active = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active.append(self)
        self.closed_by_store = False

    def close(self):
        self.closed_by_store = True
        return super().close()


class SQLiteLifetimeTests(unittest.TestCase):
    def setUp(self):
        TrackedConnection.active.clear()
        original_connect = sqlite3.connect

        def tracked(*args, **kwargs):
            kwargs['factory'] = TrackedConnection
            return original_connect(*args, **kwargs)

        self.patcher = patch.object(experience.sqlite3, 'connect', side_effect=tracked)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def assert_all_closed(self):
        self.assertTrue(TrackedConnection.active, 'No database connection was exercised')
        self.assertTrue(all(x.closed_by_store for x in TrackedConnection.active),
                        'SQLite connection leaked; Windows may lock temp files')

    def test_saved_and_read_connections_are_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(pathlib.Path(tmp) / 'memory.db')
            self.assertTrue(store.save_verified('docs.python.org', 'browser_type', 'textbox',
                                                'SEARCH_RESULT_LINK_OBSERVED'))
            self.assertEqual(store.hint('docs.python.org'), ('browser_type', 'textbox', 1))
            self.assert_all_closed()

    def test_successful_import_closes_source_and_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = ExperienceStore(pathlib.Path(tmp) / 'legacy.db')
            old.save_verified('docs.python.org', 'browser_type', 'textbox',
                              'SEARCH_RESULT_LINK_OBSERVED')
            store = ExperienceStore(pathlib.Path(tmp) / 'new.db')
            self.assertEqual(store.import_legacy_readonly(old.path), 1)
            self.assertIsNone(store.import_legacy_readonly(old.path))
            self.assert_all_closed()

    def test_failed_import_closes_source_and_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = pathlib.Path(tmp) / 'bad.db'
            with closing(sqlite3.connect(broken)) as c, c:
                c.execute('CREATE TABLE unrelated (id INT)')
            store = ExperienceStore(pathlib.Path(tmp) / 'new.db')
            with self.assertRaisesRegex(ValueError, 'LEGACY_EXPERIENCE_SCHEMA_UNSUPPORTED'):
                store.import_legacy_readonly(broken)
            self.assert_all_closed()


if __name__ == '__main__':
    unittest.main()
