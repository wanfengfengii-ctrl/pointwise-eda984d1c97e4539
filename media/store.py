import sqlite3
from contextlib import contextmanager
from pathlib import Path

from media.layout import VolumeLayout, make_layout
from media.page import PageImage, pack_page


class UnknownMediaVolume(LookupError):
    pass


@contextmanager
def open_media(root, *, write: bool = False, create: bool = False):
    path = Path(root).resolve() / 'media.sqlite3'
    mode = 'rwc' if create else ('rw' if write else 'ro')
    connection = sqlite3.connect(f'{path.as_uri()}?mode={mode}', uri=True, isolation_level=None)
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


def initialize_media(root) -> None:
    Path(root).mkdir(parents=True, exist_ok=True)
    with open_media(root, write=True, create=True) as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS media_volumes (
                volume_id TEXT PRIMARY KEY NOT NULL,
                normal_count INTEGER NOT NULL CHECK (normal_count >= 0)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS physical_pages (
                volume_id TEXT NOT NULL REFERENCES media_volumes(volume_id),
                slot_number INTEGER NOT NULL CHECK (slot_number >= 1),
                image BLOB,
                PRIMARY KEY (volume_id, slot_number)
            )
        ''')


def provision_volume_pages(root, layout: VolumeLayout, originals: tuple[PageImage, ...]) -> None:
    if len(originals) != layout.normal_count or any(not isinstance(image, PageImage) for image in originals):
        raise ValueError('provisioning requires exactly the complete normal pages')
    # The caller holds the admission transaction and has verified that the volume is unregistered.
    with open_media(root, write=True) as db:
        db.execute('DELETE FROM physical_pages WHERE volume_id = ?', (layout.volume_id,))
        db.execute('''
            INSERT INTO media_volumes (volume_id, normal_count) VALUES (?, ?)
            ON CONFLICT (volume_id) DO UPDATE SET normal_count = excluded.normal_count
        ''', (layout.volume_id, layout.normal_count))
        db.executemany('INSERT INTO physical_pages (volume_id, slot_number, image) VALUES (?, ?, ?)', (
            (layout.volume_id, slot, pack_page(image))
            for slot, image in zip(layout.all_slots, (*originals, None))
        ))


def load_volume_layout(db: sqlite3.Connection, volume_id: str) -> VolumeLayout:
    row = db.execute('SELECT normal_count FROM media_volumes WHERE volume_id = ?', (volume_id,)).fetchone()
    if row is None:
        raise UnknownMediaVolume(volume_id)
    return make_layout(volume_id, row[0])
