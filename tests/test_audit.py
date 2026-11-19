from dataclasses import replace
from hashlib import sha256

from audit.close import AuditCloseError, close
from audit.history import UnknownAuditNumber, readback
from delivery.page import page
from delivery.ticket import ticket
from intake.manifest import VolumeManifest
from intake.register import accept
from reorder.request import reorder
from tests.assertions import assert_originals
from tests.fixtures import VolumeCase, initialize


class AuditTests(VolumeCase):
    def issued_lines(self):
        self.admit()
        issued = ticket(self.root, self.volume_id)
        return issued, page(self.root, issued.number, 0, 3).lines

    def assert_no_audit(self):
        self.assertEqual(self.count('audit_records'), 0)
        self.assertEqual(self.count('audit_lines'), 0)
        with self.assertRaises(UnknownAuditNumber):
            readback(self.root, 1)

    def test_fixed_total(self):
        issued, lines = self.issued_lines()
        assert_originals(self, lines, 'ABC')
        sealed = close(self.root, issued.number, lines)
        self.assertEqual((sealed.record.ticket_number, sealed.record.volume_id), (issued.number, 'HZ-17'))
        self.assertEqual(sealed.record.total, 31)
        self.assertEqual(tuple(row.original_id for row in sealed.record.lines), ('A', 'B', 'C'))
        self.assertEqual(tuple(row.digest for row in sealed.record.lines),
                         tuple(sha256(line.payload).hexdigest() for line in lines))
        initialize(self.root)
        history = readback(self.root, sealed.record.number)
        self.assertEqual(history, sealed)
        assert_originals(self, history.originals, 'ABC')

    def test_duplicate_with_omission(self):
        issued, (a, _, c) = self.issued_lines()
        with self.assertRaises(AuditCloseError):
            close(self.root, issued.number, (a, c, a))
        self.assert_no_audit()

    def test_out_of_order(self):
        issued, (a, b, c) = self.issued_lines()
        for incorrect in ((b, a, c), (a, b), (a, b, c, a)):
            with self.subTest(lines=incorrect), self.assertRaises(AuditCloseError):
                close(self.root, issued.number, incorrect)
        self.assert_no_audit()

    def test_wrong_origin(self):
        issued, (a, b, c) = self.issued_lines()
        with self.assertRaises(AuditCloseError):
            close(self.root, issued.number, (replace(a, origin=b.origin), b, c))
        self.assert_no_audit()

    def test_altered_bytes(self):
        issued, (a, b, c) = self.issued_lines()
        with self.assertRaises(AuditCloseError):
            close(self.root, issued.number, (a, replace(b, payload=b.payload + b' '), c))
        self.assert_no_audit()

    def test_wrong_reading(self):
        issued, (a, b, c) = self.issued_lines()
        for incorrect in (None, True, 7.0, 0, 70):
            with self.subTest(reading=incorrect), self.assertRaises(AuditCloseError):
                close(self.root, issued.number, (replace(a, reading=incorrect), b, c))
        self.assert_no_audit()

    def test_empty_volume(self):
        accept(self.root, VolumeManifest('empty', ()), ())
        issued = ticket(self.root, 'empty')
        sealed = close(self.root, issued.number, page(self.root, issued.number, 0, 1).lines)
        self.assertEqual((sealed.record.total, sealed.record.lines, sealed.originals), (0, (), ()))
        self.assertEqual(readback(self.root, sealed.record.number), sealed)

    def test_exact_integer(self):
        for suffix, first_value, expected in (('float-limit', 9007199254740992, 9007199254740993),
                                              ('sqlite-limit', 9223372036854775808, 9223372036854775809)):
            with self.subTest(boundary=suffix):
                readings = (first_value, 1, 0)
                volume = 'exact-' + suffix
                entries = tuple(replace(entry, reading=value) for entry, value in zip(self.manifest.entries, readings))
                originals = tuple(replace(image, reading=value) for image, value in zip(self.originals, readings))
                accept(self.root, VolumeManifest(volume, entries), originals)
                issued = ticket(self.root, volume)
                sealed = close(self.root, issued.number, page(self.root, issued.number, 0, 3).lines)
                self.assertEqual(sealed.record.total, expected)
                initialize(self.root)
                history = readback(self.root, sealed.record.number)
                self.assertIs(type(history.record.total), int)
                self.assertEqual(history.record.total, expected)
                self.assertEqual(tuple(row.reading for row in history.record.lines), readings)
                self.assertEqual(tuple(row.reading for row in history.originals), readings)
                self.assertEqual(history, sealed)

    def test_across_reorder(self):
        old, lines = self.issued_lines()
        sealed = close(self.root, old.number, lines)
        reorder(self.root, self.volume_id, 'route', self.goal)
        initialize(self.root)
        current = ticket(self.root, self.volume_id)
        newer = close(self.root, current.number, page(self.root, current.number, 0, 3).lines)
        self.assertNotEqual(sealed.record.number, newer.record.number)
        history = readback(self.root, sealed.record.number)
        self.assertEqual(history, sealed)
        assert_originals(self, history.originals, 'ABC')
        assert_originals(self, readback(self.root, newer.record.number).originals, 'BCA')

    def test_unknown_number(self):
        issued, lines = self.issued_lines()
        sealed = close(self.root, issued.number, lines)
        for unknown in (sealed.record.number + 1, 0, True, 1 << 70):
            with self.subTest(number=unknown), self.assertRaises(UnknownAuditNumber):
                readback(self.root, unknown)
        self.assertEqual(self.count('audit_records'), 1)
