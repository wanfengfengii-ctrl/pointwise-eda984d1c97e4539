from dataclasses import replace

from delivery.page import page
from delivery.ticket import ticket
from intake.catalog import open_catalog
from intake.manifest import ManifestEntry, original_digest
from intake.register import accept
from media.page import PageImage
from reorder.catalog import find_pending_request, load_active_order
from reorder.request import ReorderRequestError, reorder
from reorder.resume import ReorderInterrupted
from tests.assertions import assert_originals, assert_slots
from tests.fixtures import StopWrite, VolumeCase, initialize


class ReorderTests(VolumeCase):
    def test_cycle(self):
        self.admit()
        receipt = reorder(self.root, self.volume_id, 'route', ('B', 'C', 'A'))
        self.assertEqual((receipt.volume_id, receipt.request_id, receipt.target), ('HZ-17', 'route', ('B', 'C', 'A')))
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        self.assertEqual(reorder(self.root, self.volume_id, 'route', self.goal), receipt)
        self.assertEqual(self.count('order_requests'), 1)
        with open_catalog(self.root) as db:
            self.assertIsNone(find_pending_request(db, self.volume_id))

    def test_same_request_conflict(self):
        self.admit()
        receipt = reorder(self.root, self.volume_id, 'route', self.goal)
        with self.assertRaisesRegex(ReorderRequestError, 'bound'):
            reorder(self.root, self.volume_id, 'route', ('C', 'A', 'B'))
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        self.assertEqual(reorder(self.root, self.volume_id, 'route', self.goal), receipt)
        self.assertEqual(self.count('order_requests'), 1)

    def test_invalid_permutation(self):
        self.admit()
        for invalid in (('A', 'B'), ('A', 'A', 'C'), ('A', 'B', 'D'), ('A', 'B', 'C', 'D'), 'BCA'):
            with self.subTest(target=invalid):
                with self.assertRaises(ReorderRequestError):
                    reorder(self.root, self.volume_id, 'route', invalid)
                assert_slots(self, self.physical(), ('A', 'B', 'C', None))
        self.assertEqual(self.count('order_requests'), 0)

    def test_pending_conflict(self):
        self.admit()
        stop = StopWrite(1, 'before', 'B')
        with self.assertRaises(ReorderInterrupted):
            reorder(self.root, self.volume_id, 'route', self.goal, write_hook=stop)
        self.assertTrue(stop.hit)
        before = self.physical()
        with self.assertRaisesRegex(ReorderRequestError, 'pending'):
            reorder(self.root, self.volume_id, 'other', ('C', 'A', 'B'))
        with self.assertRaisesRegex(ReorderRequestError, 'bound'):
            reorder(self.root, self.volume_id, 'route', ('C', 'A', 'B'))
        self.assertEqual(self.physical(), before)
        self.assertEqual(self.count('order_requests'), 1)
        reorder(self.root, self.volume_id, 'route', self.goal)
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))

    def test_reopen_active_order(self):
        self.admit()
        first = reorder(self.root, self.volume_id, 'route', self.goal)
        second = reorder(self.root, self.volume_id, 'reverse', ('C', 'A', 'B'))
        initialize(self.root)
        with open_catalog(self.root) as db:
            self.assertEqual(load_active_order(db, self.volume_id), ('C', 'A', 'B'))
        self.assertEqual(reorder(self.root, self.volume_id, 'route', self.goal), first)
        self.assertEqual(reorder(self.root, self.volume_id, 'reverse', ('C', 'A', 'B')), second)
        assert_slots(self, self.physical(), ('C', 'A', 'B', None))
        current = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, current.number, 0, 3).lines, 'CAB')

    def test_disjoint_cycles_share_one_spare(self):
        d = PageImage('D', '海栈站/栏架/R01', 17, b'D\x00\x11')
        entry = ManifestEntry(d.original_id, d.origin, d.reading, original_digest(d.payload))
        manifest = replace(self.manifest, entries=(*self.manifest.entries, entry))
        a, b, c = self.originals
        accept(self.root, manifest, (a, b, c, d))
        reorder(self.root, self.volume_id, 'two-cycles', ('B', 'A', 'D', 'C'))
        self.assertEqual(self.physical(), (b, a, d, c, None))
