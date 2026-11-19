from dataclasses import dataclass

from delivery.locate import locate_original
from delivery.provenance import DeliveryLine
from delivery.ticket import load_ticket
from intake.catalog import load_accepted_manifest, open_catalog
from intake.manifest import ManifestEntry
from media.read import scan_pages


class InvalidPageWindow(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PageResult:
    lines: tuple[DeliveryLine, ...]
    next_position: int | None


def validate_page_window(count: int, position: int, page_size: int) -> int:
    if type(position) is not int or not 0 <= position <= count:
        raise InvalidPageWindow(f'invalid ticket position {position!r}')
    if type(page_size) is not int or page_size <= 0:
        raise InvalidPageWindow('page size must be a positive integer')
    return min(position + page_size, count)


def collect_originals(root, volume_id: str, entries: tuple[ManifestEntry, ...], *, read_hook=None) -> tuple[DeliveryLine, ...]:
    if not entries:
        return ()
    snapshot = scan_pages(root, volume_id, read_hook=read_hook)
    return tuple(locate_original(entry, snapshot) for entry in entries)


def page(root, ticket_number: int, position: int, page_size: int, *, read_hook=None) -> PageResult:
    with open_catalog(root) as db:
        fixed_ticket = load_ticket(db, ticket_number)
        length = len(fixed_ticket.original_ids)
        end = validate_page_window(length, position, page_size)
        by_id = load_accepted_manifest(db, fixed_ticket.volume_id).by_id()
    if position == end:
        return PageResult((), None)
    # One read view per paging call.  Tickets freeze identities, not physical slots: during
    # an interrupted reorder a wanted original may sit in the spare or a duplicated slot, so
    # each window entry is located by its ticket identity across the whole panel.  The whole
    # window must verify before anything is returned, keeping the caller's cursor untouched.
    snapshot = scan_pages(root, fixed_ticket.volume_id, read_hook=read_hook)
    window_identities = fixed_ticket.original_ids[position:end]
    lines = tuple(locate_original(by_id[identity], snapshot) for identity in window_identities)
    return PageResult(lines, end if end < length else None)
