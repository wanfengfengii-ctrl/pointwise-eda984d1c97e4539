import sqlite3

from intake.catalog import insert_accepted_volume, open_catalog, volume_is_accepted
from intake.manifest import VolumeManifest, require_text
from intake.receipts import AdmissionReceipt, store_admission_receipt
from intake.validate import AdmissionValidationError, validate_original_pages
from media.layout import make_layout
from media.read import scan_pages
from media.store import provision_volume_pages


class VolumeAlreadyAccepted(ValueError):
    pass


class AdmissionStorageError(RuntimeError):
    pass


def accept(root, manifest: VolumeManifest, pages, *, before_commit=None) -> AdmissionReceipt:
    if not isinstance(manifest, VolumeManifest):
        raise AdmissionValidationError('expected a volume manifest')
    try:
        volume_id = require_text(manifest.volume_id, 'volume identifier')
    except ValueError as exc:
        raise AdmissionValidationError(str(exc)) from exc
    try:
        with open_catalog(root, write=True) as db:
            if volume_is_accepted(db, volume_id):
                raise VolumeAlreadyAccepted(volume_id)
            normalized, originals = validate_original_pages(manifest, pages)
            layout = make_layout(volume_id, len(originals))
            provision_volume_pages(root, layout, originals)
            if scan_pages(root, volume_id) != (*originals, None):
                raise AdmissionStorageError(f'admission readback differs for {volume_id!r}')
            insert_accepted_volume(db, normalized)
            receipt = store_admission_receipt(db, normalized)
            if before_commit is not None:
                before_commit(db)
            return receipt
    except sqlite3.Error as exc:
        raise AdmissionStorageError(f'could not commit admission for {volume_id!r}') from exc
