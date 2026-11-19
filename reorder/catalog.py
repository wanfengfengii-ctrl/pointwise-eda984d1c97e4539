import json
import sqlite3
from dataclasses import dataclass

from intake.catalog import load_accepted_manifest


@dataclass(frozen=True, slots=True)
class OrderReceipt:
    number: int
    volume_id: str
    request_id: str
    target: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrderRequest:
    number: int
    volume_id: str
    request_id: str
    target: tuple[str, ...]
    receipt: OrderReceipt | None


def initialize_order_catalog(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS order_requests (
            number INTEGER PRIMARY KEY,
            volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
            request_id TEXT NOT NULL,
            target TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0 CHECK (published IN (0, 1)),
            UNIQUE (volume_id, request_id)
        )
    ''')
    db.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS one_pending_order_per_volume
        ON order_requests(volume_id) WHERE published = 0
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS active_orders (
            volume_id TEXT PRIMARY KEY NOT NULL REFERENCES volumes(volume_id),
            request_id TEXT NOT NULL,
            FOREIGN KEY (volume_id, request_id) REFERENCES order_requests(volume_id, request_id)
        )
    ''')


def _decode_request(row: sqlite3.Row | None) -> OrderRequest | None:
    if row is None:
        return None
    number = row['number']
    volume_id = row['volume_id']
    request_id = row['request_id']
    target = tuple(json.loads(row['target']))
    receipt = OrderReceipt(number, volume_id, request_id, target) if row['published'] else None
    return OrderRequest(number, volume_id, request_id, target, receipt)


def load_request(db: sqlite3.Connection, volume_id: str, request_id: str) -> OrderRequest | None:
    row = db.execute('SELECT * FROM order_requests WHERE volume_id = ? AND request_id = ?',
                     (volume_id, request_id)).fetchone()
    return _decode_request(row)


def find_pending_request(db: sqlite3.Connection, volume_id: str) -> OrderRequest | None:
    row = db.execute('SELECT * FROM order_requests WHERE volume_id = ? AND published = 0',
                     (volume_id,)).fetchone()
    return _decode_request(row)


def insert_pending_request(db: sqlite3.Connection, volume_id: str, request_id: str,
                           target: tuple[str, ...]) -> OrderRequest:
    result = db.execute('INSERT INTO order_requests (volume_id, request_id, target) VALUES (?, ?, ?)',
                        (volume_id, request_id, json.dumps(target)))
    return OrderRequest(result.lastrowid, volume_id, request_id, target, None)


def load_active_order(db: sqlite3.Connection, volume_id: str) -> tuple[str, ...]:
    row = db.execute('''
        SELECT orders.target FROM active_orders AS active
        JOIN order_requests AS orders USING (volume_id, request_id)
        WHERE active.volume_id = ? AND orders.published = 1
    ''', (volume_id,)).fetchone()
    if row is None:
        return load_accepted_manifest(db, volume_id).original_ids
    return tuple(json.loads(row[0]))


def commit_activation(db: sqlite3.Connection, request: OrderRequest) -> OrderReceipt:
    result = db.execute('UPDATE order_requests SET published = 1 WHERE number = ? AND published = 0',
                        (request.number,))
    if result.rowcount != 1:
        raise sqlite3.IntegrityError('activation requires a pending request')
    db.execute('''
        INSERT INTO active_orders (volume_id, request_id) VALUES (?, ?)
        ON CONFLICT (volume_id) DO UPDATE SET request_id = excluded.request_id
    ''', (request.volume_id, request.request_id))
    return OrderReceipt(request.number, request.volume_id, request.request_id, request.target)
