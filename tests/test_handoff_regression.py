from media.read import scan_pages
from media.write import clear_page, write_page
from reorder.request import reorder
from tests.assertions import assert_originals, assert_slots
from tests.fixtures import VolumeCase


class SparePanelResumeTests(VolumeCase):
    """Regression coverage for the HZ-17 handoff failures.

    The panel may be reopened in any state left by a single all-or-nothing page write,
    including a normal slot that was already emptied while the spare holds the displaced
    original.  Rerunning the same volume/request/target must converge without ever losing a
    byte, while frozen tickets keep delivering their ordered identities.
    """

    def test_resumes_from_empty_normal_slot_with_parked_spare(self):
        self.admit()
        a, b, _c = self.originals
        # Reachable intermediate: slot 1 was emptied after A was parked in the spare.
        write_page(self.root, self.volume_id, 4, a)
        clear_page(self.root, self.volume_id, 1)
        assert_slots(self, scan_pages(self.root, self.volume_id), (None, 'B', 'C', 'A'))
        receipt = reorder(self.root, self.volume_id, 'route', self.goal)
        self.assertEqual(receipt.target, ('B', 'C', 'A'))
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))

    def test_repeated_retries_are_idempotent_and_byte_preserving(self):
        self.admit()
        # Drive the same request three times from progressively interrupted panels.
        first = reorder(self.root, self.volume_id, 'route', self.goal)
        second = reorder(self.root, self.volume_id, 'route', self.goal)
        third = reorder(self.root, self.volume_id, 'route', self.goal)
        self.assertEqual((first, second), (second, third))
        assert_slots(self, self.physical(), ('B', 'C', 'A', None))

    def test_ticket_window_verifies_identities_across_spare_and_duplicates(self):
        from delivery.locate import OriginalUnavailable
        from delivery.page import page
        from delivery.ticket import ticket

        self.admit()
        old = ticket(self.root, self.volume_id)
        first = page(self.root, old.number, 0, 1)
        a, b, _c = self.originals
        # A legal mid-cycle panel: spare holds A, slot 1 already carries B.
        write_page(self.root, self.volume_id, 4, a)
        write_page(self.root, self.volume_id, 1, b)
        tail = page(self.root, old.number, first.next_position, 4)
        # The frozen ticket must return its own B and C by identity, never slot contents.
        assert_originals(self, tail.lines, 'BC')
        self.assertIsNone(tail.next_position)
        assert_originals(self, page(self.root, old.number, 0, 4).lines, 'ABC')
        # Whole-window verification is all-or-nothing: with no copy of B on the panel the
        # call raises and the caller keeps its recorded position for a later retry.
        # Panel here is (B, B, C, A); remove both copies of B while preserving A and C.
        clear_page(self.root, self.volume_id, 1)
        clear_page(self.root, self.volume_id, 2)
        with self.assertRaises(OriginalUnavailable):
            page(self.root, old.number, first.next_position, 4)
        assert_originals(self, page(self.root, old.number, 0, 1).lines, 'A')

    def test_resume_converges_after_every_interrupted_write(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from intake.register import accept
        from tests.fixtures import StopWrite, initialize
        from reorder.resume import ReorderInterrupted

        writes = ((4, 'A'), (1, 'B'), (2, 'C'), (3, 'A'), (4, None))
        for slot, identity in writes:
            with self.subTest(interrupted=(slot, identity)), TemporaryDirectory() as directory:
                root = Path(directory)
                initialize(root)
                accept(root, self.manifest, self.originals)
                stop = StopWrite(slot, 'after', identity)
                with self.assertRaises(ReorderInterrupted):
                    reorder(root, self.volume_id, 'route', self.goal, write_hook=stop)
                self.assertTrue(stop.hit)
                # No original byte may disappear across any single-page interruption.
                on_disk = {image.original_id for image in scan_pages(root, self.volume_id)
                           if image is not None}
                self.assertEqual(on_disk, {'A', 'B', 'C'})
                # Same volume/request/target resume from the intermediate panel and finish.
                receipt = reorder(root, self.volume_id, 'route', self.goal)
                self.assertEqual(receipt.target, ('B', 'C', 'A'))
                assert_slots(self, scan_pages(root, self.volume_id), ('B', 'C', 'A', None))
