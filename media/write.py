import sqlite3

from media.layout import validate_slot
from media.page import PageImage, pack_page
from media.store import UnknownMediaVolume, load_volume_layout, open_media


class PageWriteError(RuntimeError):
    pass


def _replace(root, volume_id: str, slot: int, image: PageImage | None, write_hook) -> None:
    packed = pack_page(image)
    try:
        with open_media(root, write=True) as db:
            validate_slot(load_volume_layout(db, volume_id), slot)
            if write_hook is not None:
                write_hook(volume_id, slot, 'before', image)
            result = db.execute('''
                UPDATE physical_pages SET image = ? WHERE volume_id = ? AND slot_number = ?
            ''', (packed, volume_id, slot))
            if result.rowcount != 1:
                raise PageWriteError(f'missing preallocated slot {slot} in {volume_id!r}')
        if write_hook is not None:
            write_hook(volume_id, slot, 'after', image)
    except (sqlite3.Error, UnknownMediaVolume) as exc:
        raise PageWriteError(f'page write did not return success for {volume_id!r} slot {slot}') from exc


def write_page(root, volume_id: str, slot: int, image: PageImage, *, write_hook=None) -> None:
    if not isinstance(image, PageImage):
        raise ValueError('write_page requires a complete original')
    _replace(root, volume_id, slot, image, write_hook)


def clear_page(root, volume_id: str, slot: int, *, write_hook=None) -> None:
    _replace(root, volume_id, slot, None, write_hook)
