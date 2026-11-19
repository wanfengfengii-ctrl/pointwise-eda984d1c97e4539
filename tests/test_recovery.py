from pathlib import Path
from tempfile import TemporaryDirectory

from audit.close import close
from audit.history import readback
from delivery.page import page
from delivery.ticket import ticket
from intake.catalog import open_catalog
from intake.register import accept
from media.read import scan_pages
from reorder.activation import ActivationError, verify_target_layout
from reorder.catalog import load_active_order, load_request
from reorder.request import reorder
from reorder.resume import ReorderInterrupted
from tests.assertions import assert_originals, assert_slots
from tests.fixtures import StopWrite, VolumeCase, deny_commit, initialize


class RecoveryTests(VolumeCase):
    def test_written_without_reply(self):
        self.admit()
        old = ticket(self.root, self.volume_id)
        first = page(self.root, old.number, 0, 1)
        assert_originals(self, first.lines, 'A')
        self.assertEqual(first.next_position, 1)
        stop = StopWrite(1, 'after', 'B')
        with self.assertRaises(ReorderInterrupted):
            reorder(self.root, self.volume_id, 'route', self.goal, write_hook=stop)
        self.assertTrue(stop.hit)
        initialize(self.root)
        assert_slots(self, self.physical(), ('B', 'B', 'C', 'A'))
        with open_catalog(self.root) as db:
            self.assertIsNone(load_request(db, self.volume_id, 'route').receipt)
        paused = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, paused.number, 0, 3).lines, 'ABC')
        tail = page(self.root, old.number, first.next_position, 3)
        assert_originals(self, tail.lines, 'BC')
        self.assertIsNone(tail.next_position)
        receipt = reorder(self.root, self.volume_id, 'route', self.goal)
        self.assertEqual(receipt.target, ('B', 'C', 'A'))
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        assert_originals(self, page(self.root, old.number, 1, 3).lines, 'BC')
        assert_originals(self, page(self.root, paused.number, 0, 3).lines, 'ABC')
        current = ticket(self.root, self.volume_id)
        new_items = page(self.root, current.number, 0, 4).lines
        assert_originals(self, new_items, 'BCA')
        old_audit = close(self.root, old.number, first.lines + tail.lines)
        new_audit = close(self.root, current.number, new_items)
        self.assertEqual((old_audit.record.total, new_audit.record.total), (31, 31))
        initialize(self.root)
        self.assertEqual(readback(self.root, old_audit.record.number), old_audit)
        self.assertEqual(readback(self.root, new_audit.record.number), new_audit)

    def test_last_copy(self):
        self.admit()
        stop = StopWrite(1, 'after', 'B')
        with self.assertRaises(ReorderInterrupted):
            reorder(self.root, self.volume_id, 'route', self.goal, write_hook=stop)
        self.assertTrue(stop.hit)
        images = self.physical()
        self.assertEqual(tuple(index for index, image in enumerate(images, start=1)
                               if image is not None and image.original_id == 'A'), (4,))
        assert_originals(self, (images[3],), 'A')

    def test_write_not_applied(self):
        self.admit()
        stop = StopWrite(1, 'before', 'B')
        with self.assertRaises(ReorderInterrupted):
            reorder(self.root, self.volume_id, 'route', self.goal, write_hook=stop)
        self.assertTrue(stop.hit)
        initialize(self.root)
        assert_slots(self, self.physical(), ('A', 'B', 'C', 'A'))
        paused = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, paused.number, 0, 3).lines, 'ABC')
        steps = []

        def record_write(_volume, slot, phase, image):
            if phase == 'after':
                steps.append((slot, None if image is None else image.original_id))

        receipt = reorder(self.root, self.volume_id, 'route', self.goal, write_hook=record_write)
        self.assertEqual(steps[0], (1, 'B'))
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        self.assertEqual(reorder(self.root, self.volume_id, 'route', self.goal), receipt)
        self.assertEqual(self.count('order_requests'), 1)

    def test_activation_failure(self):
        self.admit()
        old = ticket(self.root, self.volume_id)
        with self.assertRaises(ActivationError):
            reorder(self.root, self.volume_id, 'route', self.goal, before_commit=deny_commit)
        initialize(self.root)
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))
        with open_catalog(self.root) as db:
            request = load_request(db, self.volume_id, 'route')
            self.assertEqual(request.target, ('B', 'C', 'A'))
            self.assertIsNone(request.receipt)
            self.assertEqual(load_active_order(db, self.volume_id), ('A', 'B', 'C'))
        paused = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, paused.number, 0, 3).lines, 'ABC')
        writes = []
        receipt = reorder(self.root, self.volume_id, 'route', self.goal, write_hook=lambda *event: writes.append(event))
        self.assertEqual(writes, [])
        with open_catalog(self.root) as db:
            self.assertEqual(load_request(db, self.volume_id, 'route').receipt, receipt)
            self.assertEqual(load_active_order(db, self.volume_id), ('B', 'C', 'A'))
        self.assertEqual(reorder(self.root, self.volume_id, 'route', self.goal), receipt)
        current = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, current.number, 0, 3).lines, 'BCA')
        assert_originals(self, page(self.root, old.number, 1, 3).lines, 'BC')

    def test_activation_rejects_unready_panels(self):
        self.admit()
        stop = StopWrite(1, 'before', 'B')
        with self.assertRaises(ReorderInterrupted):
            reorder(self.root, self.volume_id, 'route', self.goal, write_hook=stop)
        with open_catalog(self.root) as db:
            request = load_request(db, self.volume_id, 'route')
        with self.assertRaises(ActivationError):
            verify_target_layout(self.root, self.manifest, request)

    def test_every_write_boundary_reopens(self):
        writes = ((4, 'A'), (1, 'B'), (2, 'C'), (3, 'A'), (4, None))
        for slot, identity in writes:
            for phase in ('before', 'after'):
                with self.subTest(slot=slot, identity=identity, phase=phase), TemporaryDirectory() as directory:
                    root = Path(directory)
                    initialize(root)
                    accept(root, self.manifest, self.originals)
                    old = ticket(root, self.volume_id)
                    stop = StopWrite(slot, phase, identity)
                    with self.assertRaises(ReorderInterrupted):
                        reorder(root, self.volume_id, 'route', self.goal, write_hook=stop)
                    self.assertTrue(stop.hit)
                    initialize(root)
                    assert_originals(self, page(root, old.number, 0, 3).lines, 'ABC')
                    receipt = reorder(root, self.volume_id, 'route', self.goal)
                    assert_slots(self, scan_pages(root, self.volume_id), ('B', 'C', 'A', None))
                    self.assertEqual(reorder(root, self.volume_id, 'route', self.goal), receipt)
