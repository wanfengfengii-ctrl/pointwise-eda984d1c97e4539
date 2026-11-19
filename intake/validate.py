from intake.manifest import VolumeManifest, normalize_manifest, original_digest
from media.layout import make_layout
from media.page import PageImage


class AdmissionValidationError(ValueError):
    pass


def validate_original_pages(manifest: VolumeManifest, pages) -> tuple[VolumeManifest, tuple[PageImage, ...]]:
    try:
        normalized = normalize_manifest(manifest)
        originals = tuple(pages)
    except (TypeError, ValueError) as exc:
        raise AdmissionValidationError(str(exc)) from exc
    layout = make_layout(normalized.volume_id, len(normalized.entries))
    if len(originals) != layout.normal_count:
        raise AdmissionValidationError('manifest and original page counts differ')
    for slot, entry, image in zip(layout.normal_slots, normalized.entries, originals):
        if not isinstance(image, PageImage):
            raise AdmissionValidationError(f'normal slot {slot} requires a complete original')
        if image.original_id != entry.original_id:
            raise AdmissionValidationError(f'identity mismatch at normal slot {slot}')
        if image.origin != entry.origin:
            raise AdmissionValidationError(f'source mismatch for {entry.original_id!r}')
        if type(image.reading) is not int or image.reading != entry.reading:
            raise AdmissionValidationError(f'reading mismatch for {entry.original_id!r}')
        if type(image.payload) is not bytes or original_digest(image.payload) != entry.digest:
            raise AdmissionValidationError(f'original bytes mismatch for {entry.original_id!r}')
    return normalized, originals
