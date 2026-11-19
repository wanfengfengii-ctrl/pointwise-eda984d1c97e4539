from media.layout import VolumeLayout
from media.page import PageImage
from media.write import clear_page, write_page


class MoveSafetyError(RuntimeError):
    pass


def write_target_layout(root, layout: VolumeLayout, target: tuple[str, ...],
                        snapshot: tuple[PageImage | None, ...], originals: dict[str, PageImage],
                        *, write_hook=None) -> None:
    for slot, identity in zip(layout.normal_slots, target):
        wanted = originals[identity]
        if snapshot[slot - 1] != wanted:
            write_page(root, layout.volume_id, slot, wanted, write_hook=write_hook)
    if snapshot[layout.spare_slot - 1] is not None:
        clear_page(root, layout.volume_id, layout.spare_slot, write_hook=write_hook)
