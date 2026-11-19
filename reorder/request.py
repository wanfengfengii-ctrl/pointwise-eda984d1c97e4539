import sqlite3

from intake.catalog import load_accepted_manifest, open_catalog
from intake.manifest import VolumeManifest, require_text
from reorder.activation import ActivationError, activate_order
from reorder.catalog import OrderReceipt, find_pending_request, insert_pending_request, load_request
from reorder.resume import resume_request


class ReorderRequestError(ValueError):
    pass


def validate_target(manifest: VolumeManifest, target) -> tuple[str, ...]:
    if isinstance(target, (str, bytes)):
        raise ReorderRequestError('target must be a sequence of original identifiers')
    try:
        goal = tuple(require_text(identity, 'target original identifier') for identity in target)
    except (TypeError, ValueError) as exc:
        raise ReorderRequestError(str(exc)) from exc
    if len(goal) != len(manifest.entries) or set(goal) != set(manifest.original_ids):
        raise ReorderRequestError('target must be a permutation of all accepted originals')
    return goal


def reorder(root, volume_id: str, request_id: str, target, *, write_hook=None, before_commit=None) -> OrderReceipt:
    try:
        require_text(request_id, 'request identifier')
        require_text(volume_id, 'volume identifier')
    except ValueError as exc:
        raise ReorderRequestError(str(exc)) from exc

    with open_catalog(root, write=True) as db:
        manifest = load_accepted_manifest(db, volume_id)
        goal = validate_target(manifest, target)
        previous = load_request(db, volume_id, request_id)
        if previous is not None:
            if previous.target != goal:
                raise ReorderRequestError('request identifier is already bound to a different target')
            if previous.receipt is not None:
                return previous.receipt
        else:
            if find_pending_request(db, volume_id) is not None:
                raise ReorderRequestError('volume already has a pending reorder')
            insert_pending_request(db, volume_id, request_id, goal)

    # The request survives interruption independently of the publication transaction.
    try:
        with open_catalog(root, write=True) as db:
            request = load_request(db, volume_id, request_id)
            if request is None:
                raise ReorderRequestError('registered request disappeared')
            if request.receipt is not None:
                return request.receipt
            resume_request(root, manifest, request, write_hook=write_hook)
            return activate_order(root, db, manifest, request, before_commit=before_commit)
    except sqlite3.Error as exc:
        raise ActivationError(f'could not publish {volume_id!r} request {request_id!r}') from exc
