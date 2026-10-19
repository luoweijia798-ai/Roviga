"""Synthetic SQLite backup CLI regression; no actual market records."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stock_picker.phase4_acceptance import main, verify_snapshot
from stock_picker.real_market import SQLiteMarketCache


class BackupEntryTests(unittest.TestCase):
    def test_verified_online_backup_does_not_audit_or_mutate_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'test.sqlite'; SQLiteMarketCache(source)
            before=source.read_bytes()
            with patch('sys.argv',['backup','--cache',str(source),'--output',str(root/'backup'),'--backup-only']), \
                 patch('stock_picker.phase4_acceptance.RealMarketDataAuditor.run',side_effect=AssertionError('must not audit')), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                main()
            identities=list((root/'backup').glob('*/snapshot_identity.json'))
            self.assertEqual(len(identities),1)
            identity=json.loads(identities[0].read_text(encoding='utf-8'))
            verify_snapshot(Path(identity['path']),identity)
            self.assertEqual(source.read_bytes(),before)
            self.assertIn('"backup_verified": true',output.getvalue())
            self.assertFalse(list((root/'backup').rglob('audit_report.json')))

    def test_backup_cannot_reuse_or_relabel_old_snapshot(self):
        with patch('sys.argv',['backup','--backup-only','--snapshot','unused.sqlite']), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code,2)


if __name__=='__main__':unittest.main()
