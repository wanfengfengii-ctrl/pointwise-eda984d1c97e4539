import json
from pathlib import Path
from tempfile import TemporaryDirectory

from delivery.page import page
from delivery.ticket import ticket
from demo import LostWriteReply, describe, describe_slots, load_sample, lose_first_overwrite_reply
from intake.catalog import initialize_catalog, open_catalog
from intake.register import accept
from media.store import initialize_media
from media.write import write_page
from reorder.catalog import load_request
from reorder.request import reorder
from reorder.resume import ReorderInterrupted


def initialize(root):
    initialize_catalog(root)
    initialize_media(root)


def start(root, manifest, originals):
    initialize(root)
    accept(root, manifest, originals)
    issued = ticket(root, manifest.volume_id)
    return issued, page(root, issued.number, 0, 1)


def window(root, issued, position):
    result = page(root, issued.number, position, 8)
    return {"rows": describe(result.lines), "next_position": result.next_position}


def interrupted(root, manifest, originals, target):
    volume = manifest.volume_id
    old, first = start(root, manifest, originals)
    try:
        reorder(root, volume, "route", target, write_hook=lose_first_overwrite_reply)
    except ReorderInterrupted as exc:
        if not isinstance(exc.__cause__, LostWriteReply):
            raise
    else:
        raise RuntimeError("the prescribed write did not lose its reply")
    initialize(root)
    with open_catalog(root) as db:
        request = load_request(db, volume, "route")
    paused = ticket(root, volume)
    return {"slots": describe_slots(root, volume), "pending": request is not None and request.receipt is None,
            "full": window(root, paused, 0), "tail": window(root, old, first.next_position)}


def midway(root, manifest, originals):
    volume = manifest.volume_id
    old, first = start(root, manifest, originals)
    a, b, c = originals
    write_page(root, volume, 4, a)
    write_page(root, volume, 1, b)
    write_page(root, volume, 2, c)
    return {"slots": describe_slots(root, volume), "tail": window(root, old, first.next_position)}


def completed(root, manifest, originals, target):
    volume = manifest.volume_id
    old, first = start(root, manifest, originals)
    receipt = reorder(root, volume, "route", target)
    initialize(root)
    current = ticket(root, volume)
    return {"slots": describe_slots(root, volume), "published": list(receipt.target),
            "old_tail": window(root, old, first.next_position), "new_full": window(root, current, 0)}


def main():
    with TemporaryDirectory(prefix="haizhan-incident-") as directory:
        home = Path(directory)
        manifest, originals, target = load_sample()
        actual = {"interrupted": interrupted(home / "interrupted", manifest, originals, target),
                  "midway": midway(home / "midway", manifest, originals),
                  "completed": completed(home / "completed", manifest, originals, target)}
    a, b, c = describe(originals)
    full_old = {"rows": [a, b, c], "next_position": None}
    tail = {"rows": [b, c], "next_position": None}
    full_new = {"rows": [b, c, a], "next_position": None}
    expected = {"interrupted": {"slots": ["B", "B", "C", "A"], "pending": True, "full": full_old, "tail": tail},
                "midway": {"slots": ["B", "C", "C", "A"], "tail": tail},
                "completed": {"slots": ["B", "C", "A", None], "published": ["B", "C", "A"],
                              "old_tail": tail, "new_full": full_new}}
    for name in expected:
        print(json.dumps({"case": name, "actual": actual[name], "expected": expected[name]}, ensure_ascii=False))
    if actual != expected:
        print("REORDER_HANDOFF_MISMATCH")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
