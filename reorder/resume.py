from intake.manifest import VolumeManifest, matches_entry
from media.layout import make_layout
from media.page import PageImage
from media.read import PageReadError, scan_pages
from media.write import PageWriteError
from reorder.catalog import OrderRequest
from reorder.move import MoveSafetyError, write_target_layout


class ReorderInterrupted(RuntimeError):
    pass


def collect_sources(manifest: VolumeManifest, snapshot: tuple[PageImage | None, ...]) -> dict[str, PageImage]:
    expected = manifest.by_id()
    originals = {}
    for slot, image in enumerate(snapshot, start=1):
        if image is None:
            continue
        entry = expected.get(image.original_id)
        if entry is None or not matches_entry(entry, image.original_id, image.origin, image.reading, image.payload):
            raise MoveSafetyError(f"slot {slot} cannot be verified against the accepted manifest")
        originals[image.original_id] = image
    missing = tuple(identity for identity in expected if identity not in originals)
    if missing:
        raise MoveSafetyError(f"originals missing from the media: {missing!r}")
    return originals


def resume_request(root, manifest: VolumeManifest, request: OrderRequest, *, write_hook=None) -> None:
    try:
        layout = make_layout(manifest.volume_id, len(manifest.entries))
        snapshot = scan_pages(root, manifest.volume_id)
        if len(snapshot) != len(layout.all_slots):
            raise MoveSafetyError("physical layout differs from the accepted manifest")
        # Re-verify every readable page against the accepted manifest before touching the
        # panel, so no unverified or unknown bytes can take part in the reorder.
        originals = collect_sources(manifest, snapshot)
        write_target_layout(root, layout, request.target, originals, write_hook=write_hook)
    except (MoveSafetyError, PageReadError, PageWriteError) as exc:
        raise ReorderInterrupted(f"{request.volume_id!r} request {request.request_id!r}: {exc}") from exc
