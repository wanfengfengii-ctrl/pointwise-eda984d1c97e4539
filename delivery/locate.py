from delivery.provenance import DeliveryLine, ProvenanceMismatch, make_delivery_line
from intake.manifest import ManifestEntry
from media.page import PageImage


class OriginalUnavailable(RuntimeError):
    pass


def locate_original(entry: ManifestEntry, pages: tuple[PageImage | None, ...]) -> DeliveryLine:
    for image in pages:
        if image is None or image.original_id != entry.original_id:
            continue
        try:
            return make_delivery_line(entry, image)
        except ProvenanceMismatch:
            continue
    raise OriginalUnavailable(f'no verifiable copy of original {entry.original_id!r}')
