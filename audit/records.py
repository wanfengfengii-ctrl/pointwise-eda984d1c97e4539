import sqlite3
from dataclasses import dataclass

from delivery.provenance import DeliveryLine
from delivery.ticket import TicketOrder
from intake.manifest import ManifestEntry


@dataclass(frozen=True, slots=True)
class AuditLine:
    original_id: str
    origin: str
    reading: int
    digest: str

    def as_manifest_entry(self) -> ManifestEntry:
        return ManifestEntry(self.original_id, self.origin, self.reading, self.digest)


@dataclass(frozen=True, slots=True)
class AuditRecord:
    number: int
    ticket_number: int
    volume_id: str
    lines: tuple[AuditLine, ...]
    total: int


@dataclass(frozen=True, slots=True)
class AuditResult:
    record: AuditRecord
    originals: tuple[DeliveryLine, ...]


def initialize_audit_records(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS audit_records (
            number INTEGER PRIMARY KEY,
            ticket_number INTEGER NOT NULL REFERENCES tickets(number),
            total_hex TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS audit_lines (
            audit_number INTEGER NOT NULL REFERENCES audit_records(number),
            position INTEGER NOT NULL CHECK (position >= 0),
            original_id TEXT NOT NULL,
            origin TEXT NOT NULL,
            reading_hex TEXT NOT NULL,
            digest TEXT NOT NULL,
            PRIMARY KEY (audit_number, position)
        )
    ''')


def store_audit_record(db: sqlite3.Connection, fixed_ticket: TicketOrder,
                       entries: tuple[ManifestEntry, ...], total: int) -> AuditRecord:
    result = db.execute('INSERT INTO audit_records (ticket_number, total_hex) VALUES (?, ?)',
                        (fixed_ticket.number, format(total, 'x')))
    number = result.lastrowid
    lines = tuple(AuditLine(entry.original_id, entry.origin, entry.reading, entry.digest) for entry in entries)
    db.executemany('''
        INSERT INTO audit_lines (audit_number, position, original_id, origin, reading_hex, digest)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        (number, position, line.original_id, line.origin, format(line.reading, 'x'), line.digest)
        for position, line in enumerate(lines)
    ))
    return AuditRecord(number, fixed_ticket.number, fixed_ticket.volume_id, lines, total)


def load_audit_record(db: sqlite3.Connection, audit_number: int) -> AuditRecord | None:
    if type(audit_number) is not int or not 1 <= audit_number < (1 << 63):
        return None
    header = db.execute('''
        SELECT records.ticket_number, tickets.volume_id, records.total_hex
        FROM audit_records AS records JOIN tickets ON tickets.number = records.ticket_number
        WHERE records.number = ?
    ''', (audit_number,)).fetchone()
    if header is None:
        return None
    rows = db.execute('''
        SELECT original_id, origin, reading_hex, digest FROM audit_lines
        WHERE audit_number = ? ORDER BY position
    ''', (audit_number,))
    lines = tuple(AuditLine(row['original_id'], row['origin'], int(row['reading_hex'], 16), row['digest'])
                  for row in rows)
    return AuditRecord(audit_number, header['ticket_number'], header['volume_id'], lines, int(header['total_hex'], 16))
