import sqlite3
from contextlib import contextmanager
from pathlib import Path

from intake.manifest import ManifestEntry, VolumeManifest, require_text


class UnknownVolume(LookupError):
    pass


@contextmanager
def _catalog_transaction(root, mode: str, write: bool):
    path = Path(root).resolve() / 'catalog.sqlite3'
    connection = sqlite3.connect(f'{path.as_uri()}?mode={mode}', uri=True, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield connection
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def open_catalog(root, *, write: bool = False):
    return _catalog_transaction(root, 'rw' if write else 'ro', write)


def initialize_catalog(root) -> None:
    from audit.records import initialize_audit_records
    from delivery.ticket import initialize_tickets
    from intake.receipts import initialize_admission_receipts
    from reorder.catalog import initialize_order_catalog

    Path(root).mkdir(parents=True, exist_ok=True)
    with _catalog_transaction(root, 'rwc', True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS volumes (volume_id TEXT PRIMARY KEY NOT NULL)')
        db.execute('''
            CREATE TABLE IF NOT EXISTS manifest_entries (
                volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
                position INTEGER NOT NULL CHECK (position >= 0),
                original_id TEXT NOT NULL,
                origin TEXT NOT NULL,
                reading_hex TEXT NOT NULL,
                digest TEXT NOT NULL,
                PRIMARY KEY (volume_id, position),
                UNIQUE (volume_id, original_id)
            )
        ''')
        initialize_admission_receipts(db)
        initialize_order_catalog(db)
        initialize_tickets(db)
        initialize_audit_records(db)


def volume_is_accepted(db: sqlite3.Connection, volume_id: str) -> bool:
    return db.execute('SELECT 1 FROM volumes WHERE volume_id = ?', (volume_id,)).fetchone() is not None


def insert_accepted_volume(db: sqlite3.Connection, manifest: VolumeManifest) -> None:
    db.execute('INSERT INTO volumes (volume_id) VALUES (?)', (manifest.volume_id,))
    db.executemany('''
        INSERT INTO manifest_entries (volume_id, position, original_id, origin, reading_hex, digest)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        (manifest.volume_id, position, entry.original_id, entry.origin, format(entry.reading, 'x'), entry.digest)
        for position, entry in enumerate(manifest.entries)
    ))


def load_accepted_manifest(db: sqlite3.Connection, volume_id: str) -> VolumeManifest:
    require_text(volume_id, 'volume identifier')
    if not volume_is_accepted(db, volume_id):
        raise UnknownVolume(volume_id)
    rows = db.execute('''
        SELECT original_id, origin, reading_hex, digest FROM manifest_entries
        WHERE volume_id = ? ORDER BY position
    ''', (volume_id,))
    entries = tuple(ManifestEntry(row['original_id'], row['origin'], int(row['reading_hex'], 16), row['digest'])
                    for row in rows)
    return VolumeManifest(volume_id, entries)
