import json
import sqlite3
from dataclasses import dataclass

from intake.catalog import open_catalog
from reorder.catalog import load_active_order


class UnknownTicket(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class TicketOrder:
    number: int
    volume_id: str
    original_ids: tuple[str, ...]


def initialize_tickets(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            number INTEGER PRIMARY KEY,
            volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
            original_ids TEXT NOT NULL
        )
    ''')


def ticket(root, volume_id: str) -> TicketOrder:
    with open_catalog(root, write=True) as db:
        original_ids = load_active_order(db, volume_id)
        result = db.execute('INSERT INTO tickets (volume_id, original_ids) VALUES (?, ?)',
                            (volume_id, json.dumps(original_ids)))
        return TicketOrder(result.lastrowid, volume_id, original_ids)


def load_ticket(db: sqlite3.Connection, ticket_number: int) -> TicketOrder:
    if type(ticket_number) is not int or not 1 <= ticket_number < (1 << 63):
        raise UnknownTicket(ticket_number)
    row = db.execute('SELECT volume_id, original_ids FROM tickets WHERE number = ?', (ticket_number,)).fetchone()
    if row is None:
        raise UnknownTicket(ticket_number)
    return TicketOrder(ticket_number, row['volume_id'], tuple(json.loads(row['original_ids'])))
