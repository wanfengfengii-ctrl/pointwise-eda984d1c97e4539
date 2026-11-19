from dataclasses import dataclass

from intake.manifest import ManifestEntry, matches_entry
from media.page import PageImage


class ProvenanceMismatch(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DeliveryLine:
    original_id: str
    origin: str
    reading: int
    payload: bytes


def verify_provenance(entry: ManifestEntry, original: PageImage | DeliveryLine) -> None:
    if not matches_entry(entry, original.original_id, original.origin, original.reading, original.payload):
        raise ProvenanceMismatch(f'original {entry.original_id!r} differs from the verified record')


def make_delivery_line(entry: ManifestEntry, image: PageImage) -> DeliveryLine:
    verify_provenance(entry, image)
    return DeliveryLine(image.original_id, image.origin, image.reading, image.payload)
