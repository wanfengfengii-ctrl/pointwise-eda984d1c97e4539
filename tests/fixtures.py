import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import load_sample
from intake.catalog import initialize_catalog, open_catalog
from intake.register import accept
from media.read import scan_pages
from media.store import initialize_media
from media.write import PageWriteError


def initialize(root):
    initialize_catalog(root)
    initialize_media(root)


def deny_commit(db):
    def authorizer(action, operation, _name, _database, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and operation == 'COMMIT':
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    db.set_authorizer(authorizer)


class StopWrite:
    def __init__(self, slot, phase, identity):
        self.slot = slot
        self.phase = phase
        self.identity = identity
        self.hit = False

    def __call__(self, volume_id, slot, phase, image):
        identity = None if image is None else image.original_id
        if (slot, phase, identity) == (self.slot, self.phase, self.identity):
            self.hit = True
            raise PageWriteError(f'injected {phase} write failure for {volume_id} slot {slot}')


class VolumeCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix='haizhan-test-')))
        initialize(self.root)
        self.manifest, self.originals, self.goal = load_sample()
        self.volume_id = self.manifest.volume_id

    def admit(self):
        return accept(self.root, self.manifest, self.originals)

    def physical(self):
        return scan_pages(self.root, self.volume_id)

    def count(self, table):
        allowed = {'admission_receipts', 'volumes', 'order_requests', 'tickets', 'audit_records', 'audit_lines'}
        if table not in allowed:
            raise ValueError(f'unexpected table {table!r}')
        with open_catalog(self.root) as db:
            return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
