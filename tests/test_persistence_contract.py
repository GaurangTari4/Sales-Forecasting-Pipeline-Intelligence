import os,unittest
from src.persistence.database import Database
class PersistenceContractTests(unittest.TestCase):
 def test_credentials_are_environment_only(self):
  old=os.environ.pop('DATABASE_URL',None)
  try:
   with self.assertRaises(RuntimeError): Database().connect()
  finally:
   if old: os.environ['DATABASE_URL']=old
 def test_migration_declares_immutable_triggers_and_idempotency(self):
  from pathlib import Path
  text=Path('migrations/002_persistence_audit.sql').read_text(encoding='utf8'); self.assertIn('no_stage_history_mutation',text); self.assertIn('no_booking_mutation',text); self.assertIn('no_snapshot_mutation',text); self.assertIn('ON CONFLICT',Path('src/persistence/database.py').read_text(encoding='utf8'))
