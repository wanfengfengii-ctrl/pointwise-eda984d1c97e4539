import sqlite3

from media.layout import validate_slot
from media.page import InvalidPageImage, PageImage, unpack_page
from media.store import UnknownMediaVolume, load_volume_layout, open_media


class PageReadError(RuntimeError):
    pass


def _decode(volume_id: str, slot: int, raw: bytes | None, read_hook) -> PageImage | None:
    if read_hook is not None:
        read_hook(volume_id, slot)
    try:
        return unpack_page(raw)
    except InvalidPageImage as exc:
        raise PageReadError(f'invalid image at {volume_id!r} slot {slot}') from exc


def read_page(root, volume_id: str, slot: int, *, read_hook=None) -> PageImage | None:
    try:
        with open_media(root) as db:
            validate_slot(load_volume_layout(db, volume_id), slot)
            row = db.execute('''
                SELECT image FROM physical_pages WHERE volume_id = ? AND slot_number = ?
            ''', (volume_id, slot)).fetchone()
            if row is None:
                raise PageReadError(f'missing preallocated slot {slot} in {volume_id!r}')
            return _decode(volume_id, slot, row[0], read_hook)
    except (sqlite3.Error, UnknownMediaVolume) as exc:
        raise PageReadError(f'cannot read {volume_id!r} slot {slot}') from exc


def scan_pages(root, volume_id: str, *, read_hook=None) -> tuple[PageImage | None, ...]:
    try:
        with open_media(root) as db:
            layout = load_volume_layout(db, volume_id)
            rows = db.execute('''
                SELECT slot_number, image FROM physical_pages WHERE volume_id = ? ORDER BY slot_number
            ''', (volume_id,)).fetchall()
            if tuple(row[0] for row in rows) != tuple(layout.all_slots):
                raise PageReadError(f'preallocated slots are incomplete for {volume_id!r}')
            return tuple(_decode(volume_id, slot, raw, read_hook) for slot, raw in rows)
    except (sqlite3.Error, UnknownMediaVolume) as exc:
        raise PageReadError(f'cannot scan {volume_id!r}') from exc
