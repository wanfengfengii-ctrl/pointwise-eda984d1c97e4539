from delivery.page import InvalidPageWindow, PageResult, page
from delivery.ticket import UnknownTicket, ticket
from intake.catalog import UnknownVolume, open_catalog
from intake.manifest import VolumeManifest
from intake.register import accept
from media.read import PageReadError
from media.write import write_page
from reorder.request import reorder
from tests.assertions import assert_originals, assert_slots
from tests.fixtures import VolumeCase, initialize


class DeliveryTests(VolumeCase):
    def test_old_and_new_ticket(self):
        self.admit()
        old = ticket(self.root, self.volume_id)
        first = page(self.root, old.number, 0, 1)
        assert_originals(self, first.lines, 'A')
        self.assertEqual(first.next_position, 1)
        reorder(self.root, self.volume_id, 'route', self.goal)
        initialize(self.root)
        middle = page(self.root, old.number, first.next_position, 1)
        assert_originals(self, middle.lines, 'B')
        self.assertEqual(middle.next_position, 2)
        last = page(self.root, old.number, middle.next_position, 10)
        assert_originals(self, last.lines, 'C')
        self.assertIsNone(last.next_position)
        new = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, new.number, 0, 10).lines, 'BCA')

    def test_legal_intermediate(self):
        self.admit()
        old = ticket(self.root, self.volume_id)
        first = page(self.root, old.number, 0, 1)
        a, b, _ = self.originals
        # Construct legal media independently of the reorder planner.
        write_page(self.root, self.volume_id, 4, a)
        write_page(self.root, self.volume_id, 1, b)
        initialize(self.root)
        assert_slots(self, self.physical(), ('B', 'B', 'C', 'A'))
        assert_originals(self, page(self.root, old.number, first.next_position, 4).lines, 'BC')
        pause = ticket(self.root, self.volume_id)
        assert_originals(self, page(self.root, pause.number, 0, 4).lines, 'ABC')

    def test_cursor_validation(self):
        self.admit()
        issued = ticket(self.root, self.volume_id)
        for position, size in ((-1, 1), (4, 1), (True, 1), (1.0, 1), (0, False), (0, 0), (0, -2), (0, 1.5)):
            with self.subTest(position=position, size=size), self.assertRaises(InvalidPageWindow):
                page(self.root, issued.number, position, size)
        self.assertEqual(page(self.root, issued.number, 3, 1), PageResult((), None))
        tail = page(self.root, issued.number, 2, 1 << 100)
        assert_originals(self, tail.lines, 'C')
        self.assertIsNone(tail.next_position)

    def test_invalid_ticket_or_volume(self):
        self.admit()
        with self.assertRaises(UnknownVolume):
            ticket(self.root, 'absent')
        self.assertEqual(self.count('tickets'), 0)
        issued = ticket(self.root, self.volume_id)
        for bad_ticket in (issued.number + 1, True, 1 << 70):
            with self.subTest(ticket=bad_ticket), self.assertRaises(UnknownTicket):
                page(self.root, bad_ticket, 0, 1)
        with open_catalog(self.root) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0], 1)

    def test_read_retry(self):
        self.admit()
        issued = ticket(self.root, self.volume_id)
        first = page(self.root, issued.number, 0, 1)
        reads = []

        def fail_c(volume, slot):
            reads.append((volume, slot))
            if slot == 3:
                raise PageReadError('read failed at C')

        with self.assertRaisesRegex(PageReadError, 'at C'):
            page(self.root, issued.number, first.next_position, 2, read_hook=fail_c)
        self.assertEqual(reads, [(self.volume_id, 1), (self.volume_id, 2), (self.volume_id, 3)])
        retry = page(self.root, issued.number, first.next_position, 2)
        assert_originals(self, retry.lines, 'BC')
        self.assertIsNone(retry.next_position)

    def test_empty_ticket(self):
        accept(self.root, VolumeManifest('empty', ()), ())
        old = ticket(self.root, 'empty')
        self.assertEqual(old.original_ids, ())
        self.assertEqual(page(self.root, old.number, 0, 1), PageResult((), None))
        receipt = reorder(self.root, 'empty', 'empty-order', ())
        self.assertEqual(receipt.target, ())
        self.assertEqual(page(self.root, old.number, 0, 4), PageResult((), None))
        with self.assertRaises(InvalidPageWindow):
            page(self.root, old.number, 1, 1)
