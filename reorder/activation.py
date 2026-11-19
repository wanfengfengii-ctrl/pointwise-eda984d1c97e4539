import sqlite3

from intake.manifest import VolumeManifest, matches_entry
from media.read import PageReadError, scan_pages
from reorder.catalog import OrderReceipt, OrderRequest, commit_activation


class ActivationError(RuntimeError):
    pass


def verify_target_layout(root, manifest: VolumeManifest, request: OrderRequest) -> None:
    if manifest.volume_id != request.volume_id:
        raise ActivationError('request and manifest volumes differ')
    try:
        pages = scan_pages(root, request.volume_id)
    except PageReadError as exc:
        raise ActivationError('cannot verify the target disk layout') from exc
    if len(pages) != len(manifest.entries) + 1 or pages[-1] is not None:
        raise ActivationError('activation requires the fixed layout with an empty spare')
    expected = manifest.by_id()
    if (len(request.target) != len(expected) or set(request.target) != set(expected)):
        raise ActivationError('activation target differs from the accepted identities')
    for slot, (identity, image) in enumerate(zip(request.target, pages[:-1]), start=1):
        if image is None or not matches_entry(expected[identity], image.original_id, image.origin,
                                              image.reading, image.payload):
            raise ActivationError(f'normal slot {slot} is not ready for original {identity!r}')


def activate_order(root, db: sqlite3.Connection, manifest: VolumeManifest, request: OrderRequest,
                   *, before_commit=None) -> OrderReceipt:
    verify_target_layout(root, manifest, request)
    receipt = commit_activation(db, request)
    if before_commit is not None:
        before_commit(db)
    return receipt
