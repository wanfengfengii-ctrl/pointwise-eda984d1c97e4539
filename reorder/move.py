from media.layout import VolumeLayout
from media.page import PageImage
from media.read import scan_pages
from media.write import clear_page, write_page


class MoveSafetyError(RuntimeError):
    pass


def _has_another_copy(snapshot: tuple[PageImage | None, ...], slot: int) -> bool:
    image = snapshot[slot - 1]
    return image is not None and any(
        other != slot and snapshot[other - 1] == image for other in range(1, len(snapshot) + 1))


def write_target_layout(root, layout: VolumeLayout, target: tuple[str, ...],
                        originals: dict[str, PageImage], *, write_hook=None) -> None:
    """Drive the media toward ``target`` using the single spare slot as working space.

    Each page rewrite is an independent all-or-nothing write, and a reported failure may
    still have landed on disk.  The planner therefore keeps one invariant: a normal slot is
    only overwritten while an identical, manifest-verified copy of its occupant already
    exists in another slot (the spare or a duplicate normal slot), and the spare is only
    cleared once every normal slot is correct.  Any interruption consequently leaves all
    original bytes and provenance on the media.  Rerunning the same volume/request/target
    reopens from the on-disk intermediate state and converges.
    """
    volume_id = layout.volume_id
    spare = layout.spare_slot
    normal_slots = tuple(layout.normal_slots)

    while True:
        snapshot = scan_pages(root, volume_id)
        if len(snapshot) != len(layout.all_slots):
            raise MoveSafetyError("physical layout differs from the accepted manifest")

        correct = tuple(slot for slot, identity in zip(normal_slots, target)
                        if snapshot[slot - 1] == originals[identity])
        if len(correct) == len(normal_slots):
            if snapshot[spare - 1] is not None:
                clear_page(root, volume_id, spare, write_hook=write_hook)
            return

        wrong = [slot for slot in normal_slots if slot not in correct]

        empty_normal = next((slot for slot in wrong if snapshot[slot - 1] is None), None)
        if empty_normal is not None:
            # Resume from an interrupted rebuild: refill an empty normal slot from the
            # surviving copy of its wanted original (the spare holds the displaced page).
            wanted = originals[target[empty_normal - 1]]
            if not any(image == wanted for image in snapshot):
                raise MoveSafetyError(f"original {target[empty_normal - 1]!r} is missing from the media")
            write_page(root, volume_id, empty_normal, wanted, write_hook=write_hook)
            continue

        if snapshot[spare - 1] is None:
            # Open the next permutation cycle: park the first displaced original in the
            # spare before its normal slot can be overwritten.
            displaced = snapshot[wrong[0] - 1]
            write_page(root, volume_id, spare, displaced, write_hook=write_hook)
            continue

        # The spare holds an original.  Overwrite the first wrong slot whose occupant is
        # already preserved elsewhere, so no unique copy can ever be destroyed.
        safe_slot = next((slot for slot in wrong if _has_another_copy(snapshot, slot)), None)
        if safe_slot is not None:
            wanted = originals[target[safe_slot - 1]]
            write_page(root, volume_id, safe_slot, wanted, write_hook=write_hook)
            continue

        # No safe overwrite remains: the spare must hold a duplicate of a parked original,
        # so freeing it loses nothing and lets the next permutation cycle start.
        spare_image = snapshot[spare - 1]
        if not any(snapshot[slot - 1] == spare_image for slot in normal_slots):
            raise MoveSafetyError("spare holds the only copy of an original; panel is unsafe")
        clear_page(root, volume_id, spare, write_hook=write_hook)
