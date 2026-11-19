import sqlite3
from dataclasses import dataclass

from intake.manifest import VolumeManifest


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    number: int
    volume_id: str
    original_ids: tuple[str, ...]


def initialize_admission_receipts(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS admission_receipts (
            number INTEGER PRIMARY KEY,
            volume_id TEXT NOT NULL UNIQUE REFERENCES volumes(volume_id)
        )
    ''')


def store_admission_receipt(db: sqlite3.Connection, manifest: VolumeManifest) -> AdmissionReceipt:
    row = db.execute('INSERT INTO admission_receipts (volume_id) VALUES (?)', (manifest.volume_id,))
    return AdmissionReceipt(row.lastrowid, manifest.volume_id, manifest.original_ids)


def load_admission_receipt(db: sqlite3.Connection, volume_id: str) -> AdmissionReceipt | None:
    receipt = db.execute('SELECT number FROM admission_receipts WHERE volume_id = ?', (volume_id,)).fetchone()
    if receipt is None:
        return None
    originals = db.execute('''
        SELECT original_id FROM manifest_entries WHERE volume_id = ? ORDER BY position
    ''', (volume_id,))
    return AdmissionReceipt(receipt[0], volume_id, tuple(row[0] for row in originals))
