from dataclasses import replace

from audit.close import close
from audit.history import readback
from delivery.page import page
from delivery.ticket import ticket
from intake.catalog import UnknownVolume, load_accepted_manifest, open_catalog
from intake.manifest import VolumeManifest
from intake.receipts import load_admission_receipt
from intake.register import AdmissionStorageError, VolumeAlreadyAccepted, accept
from intake.validate import AdmissionValidationError
from media.read import read_page, scan_pages
from reorder.request import reorder
from tests.assertions import assert_originals, assert_slots
from tests.fixtures import VolumeCase, deny_commit, initialize


class AcceptTests(VolumeCase):
    def assert_unaccepted(self):
        self.assertEqual(self.count('admission_receipts'), 0)
        self.assertEqual(self.count('volumes'), 0)
        with open_catalog(self.root) as db:
            self.assertIsNone(load_admission_receipt(db, self.volume_id))
        with self.assertRaises(UnknownVolume):
            ticket(self.root, self.volume_id)

    def test_initial_manifest(self):
        receipt = self.admit()
        self.assertEqual(receipt.volume_id, 'HZ-17')
        self.assertEqual(receipt.original_ids, ('A', 'B', 'C'))
        with open_catalog(self.root) as db:
            self.assertEqual(load_admission_receipt(db, self.volume_id), receipt)
            self.assertEqual(load_accepted_manifest(db, self.volume_id), self.manifest)
        issued = ticket(self.root, self.volume_id)
        result = page(self.root, issued.number, 0, 8)
        assert_originals(self, result.lines, 'ABC')
        self.assertIsNone(result.next_position)
        assert_slots(self, self.physical(), ('A', 'B', 'C', None))
        self.assertEqual(read_page(self.root, self.volume_id, 3), self.originals[2])

    def test_empty_volume(self):
        receipt = accept(self.root, VolumeManifest('empty', ()), ())
        self.assertEqual(receipt.original_ids, ())
        self.assertEqual(scan_pages(self.root, 'empty'), (None,))
        self.assertIsNone(read_page(self.root, 'empty', 1))
        with self.assertRaises(ValueError):
            read_page(self.root, 'empty', 2)

    def test_duplicate_origin(self):
        a, _, c = self.manifest.entries
        other_a = replace(a, origin='冲突来源')
        manifest = replace(self.manifest, entries=(a, other_a, c))
        pages = (self.originals[0], replace(self.originals[0], origin=other_a.origin), self.originals[2])
        with self.assertRaisesRegex(AdmissionValidationError, 'duplicate'):
            accept(self.root, manifest, pages)
        self.assert_unaccepted()

    def test_missing_page(self):
        with self.assertRaises(AdmissionValidationError):
            accept(self.root, self.manifest, self.originals[:-1])
        self.assert_unaccepted()

    def test_page_origin_mismatch(self):
        altered = (replace(self.originals[0], origin='另一合法测点'), *self.originals[1:])
        with self.assertRaisesRegex(AdmissionValidationError, 'source mismatch'):
            accept(self.root, self.manifest, altered)
        self.assert_unaccepted()

    def test_page_bytes_mismatch(self):
        altered = (replace(self.originals[0], payload=b'changed'), *self.originals[1:])
        with self.assertRaisesRegex(AdmissionValidationError, 'bytes mismatch'):
            accept(self.root, self.manifest, altered)
        self.assert_unaccepted()

    def test_invalid_reading(self):
        for value in (-1, True, 7.0, None):
            with self.subTest(reading=value):
                first = replace(self.manifest.entries[0], reading=value)
                manifest = replace(self.manifest, entries=(first, *self.manifest.entries[1:]))
                with self.assertRaises(AdmissionValidationError):
                    accept(self.root, manifest, self.originals)
                self.assert_unaccepted()

    def test_repeat_volume(self):
        receipt = self.admit()
        issued = ticket(self.root, self.volume_id)
        reorder(self.root, self.volume_id, 'route', self.goal)
        changed = replace(self.manifest.entries[0], reading=70)
        manifest = replace(self.manifest, entries=(changed, *self.manifest.entries[1:]))
        pages = (replace(self.originals[0], reading=70), *self.originals[1:])
        with self.assertRaises(VolumeAlreadyAccepted):
            accept(self.root, manifest, pages)
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        assert_originals(self, page(self.root, issued.number, 0, 3).lines, 'ABC')
        with open_catalog(self.root) as db:
            self.assertEqual(load_admission_receipt(db, self.volume_id), receipt)
            self.assertEqual(load_accepted_manifest(db, self.volume_id), self.manifest)
        self.assertEqual(self.count('admission_receipts'), 1)

    def test_initialize_twice(self):
        receipt = self.admit()
        old = ticket(self.root, self.volume_id)
        archived = close(self.root, old.number, page(self.root, old.number, 0, 3).lines)
        ordered = reorder(self.root, self.volume_id, 'evening', self.goal)
        initialize(self.root)
        initialize(self.root)
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        with open_catalog(self.root) as db:
            self.assertEqual(load_admission_receipt(db, self.volume_id), receipt)
        self.assertEqual(reorder(self.root, self.volume_id, 'evening', self.goal), ordered)
        self.assertEqual(ticket(self.root, self.volume_id).original_ids, ('B', 'C', 'A'))
        assert_originals(self, page(self.root, old.number, 0, 3).lines, 'ABC')
        self.assertEqual(readback(self.root, archived.record.number), archived)

    def test_catalog_rollback(self):
        with self.assertRaises(AdmissionStorageError):
            accept(self.root, self.manifest, self.originals, before_commit=deny_commit)
        assert_slots(self, self.physical(), ('A', 'B', 'C', None))
        self.assert_unaccepted()
        with self.assertRaises(AdmissionValidationError):
            accept(self.root, self.manifest, self.originals[:-1])
        self.assert_unaccepted()
        new_entry = replace(self.manifest.entries[0], reading=70)
        new_manifest = replace(self.manifest, entries=(new_entry, *self.manifest.entries[1:]))
        new_pages = (replace(self.originals[0], reading=70), *self.originals[1:])
        accept(self.root, new_manifest, new_pages)
        issued = ticket(self.root, self.volume_id)
        self.assertEqual(page(self.root, issued.number, 0, 1).lines[0].reading, 70)
        self.assertEqual(self.count('admission_receipts'), 1)
