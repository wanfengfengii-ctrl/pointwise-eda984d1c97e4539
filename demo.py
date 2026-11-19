import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit.close import close
from audit.history import readback
from delivery.page import page
from delivery.ticket import ticket
from intake.catalog import initialize_catalog
from intake.manifest import ManifestEntry, VolumeManifest, original_digest
from intake.register import accept
from media.page import PageImage
from media.read import scan_pages
from media.store import initialize_media
from media.write import PageWriteError
from reorder.request import reorder
from reorder.resume import ReorderInterrupted


SAMPLE = Path(__file__).resolve().parent / 'samples' / 'haizhan.json'


def load_sample(path=SAMPLE):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    originals = tuple(PageImage(row['original_id'], row['origin'], row['reading'], bytes.fromhex(row['payload_hex']))
                      for row in data['originals'])
    entries = tuple(ManifestEntry(image.original_id, image.origin, image.reading, original_digest(image.payload))
                    for image in originals)
    return VolumeManifest(data['volume_id'], entries), originals, tuple(data['target'])


class LostWriteReply(PageWriteError):
    pass


def lose_first_overwrite_reply(volume_id, slot, phase, image):
    if slot == 1 and phase == 'after' and image is not None and image.original_id == 'B':
        raise LostWriteReply(f'{volume_id} slot 1 committed before the reply was lost')


def describe(lines):
    return [[line.original_id, line.origin, line.reading, line.payload.hex()] for line in lines]


def describe_slots(root, volume_id):
    return [image.original_id if image is not None else None for image in scan_pages(root, volume_id)]


def run_demo(root):
    initialize_catalog(root)
    initialize_media(root)
    manifest, originals, goal = load_sample()
    volume_id = manifest.volume_id
    admission = accept(root, manifest, originals)
    old = ticket(root, volume_id)
    first = page(root, old.number, 0, 1)
    try:
        reorder(root, volume_id, 'route-evening', goal, write_hook=lose_first_overwrite_reply)
    except ReorderInterrupted as exc:
        if not isinstance(exc.__cause__, LostWriteReply):
            raise
    else:
        raise RuntimeError('expected a lost write reply at the first overwrite')

    # Operations reopen their connections. These initializers also exercise repeat startup.
    initialize_catalog(root)
    initialize_media(root)
    paused_slots = describe_slots(root, volume_id)
    paused_ticket = ticket(root, volume_id)
    paused_full = page(root, paused_ticket.number, 0, 8)
    paused_tail = page(root, old.number, first.next_position, 8)
    receipt = reorder(root, volume_id, 'route-evening', goal)
    old_tail = page(root, old.number, first.next_position, 8)
    new_ticket = ticket(root, volume_id)
    new_full = page(root, new_ticket.number, 0, 8)
    old_audit = close(root, old.number, first.lines + old_tail.lines)
    new_audit = close(root, new_ticket.number, new_full.lines)
    old_history = readback(root, old_audit.record.number)
    new_history = readback(root, new_audit.record.number)

    a = ['A', '海栈站/东脚/E04', 7, '410007ff']
    b = ['B', '海栈站/西脚/W02', 11, '42000b0a']
    c = ['C', '海栈站/栈台/P03', 13, '43000d80']
    expected = {'admitted': ['A', 'B', 'C'], 'first': [a], 'cursor': 1, 'paused_slots': ['B', 'B', 'C', 'A'],
                'paused_full': [a, b, c], 'paused_tail': [b, c], 'old_tail': [b, c], 'new': [b, c, a],
                'final_slots': ['B', 'C', 'A', None], 'target': ['B', 'C', 'A']}
    actual = {'admitted': list(admission.original_ids), 'first': describe(first.lines), 'cursor': first.next_position,
              'paused_slots': paused_slots, 'paused_full': describe(paused_full.lines),
              'paused_tail': describe(paused_tail.lines), 'old_tail': describe(old_tail.lines),
              'new': describe(new_full.lines), 'final_slots': describe_slots(root, volume_id),
              'target': list(receipt.target)}
    downstream_expected = {'totals': [31, 31], 'history_totals': [31, 31], 'history': [[a, b, c], [b, c, a]]}
    downstream_actual = {'totals': [old_audit.record.total, new_audit.record.total],
                         'history_totals': [old_history.record.total, new_history.record.total],
                         'history': [describe(old_history.originals), describe(new_history.originals)]}
    if actual != expected or downstream_actual != downstream_expected:
        raise RuntimeError(f'交接核对失败，实际 {actual!r}，应为 {expected!r}。核账实际 {downstream_actual!r}，应为 {downstream_expected!r}')
    return {'case_id': 'lost_reply',
            'input': {'volume': volume_id, 'originals': describe(originals), 'target': list(goal),
                      'interruption': {'slot': 1, 'phase': 'after', 'original': 'B'}},
            'expected': expected, 'actual': actual,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
            'code_paths': ['intake/register.py', 'media/write.py', 'reorder/resume.py', 'reorder/activation.py',
                           'delivery/page.py', 'audit/close.py', 'audit/history.py'],
            'oracle': '按固定样例手工对照每个盘位、身份、出处和原字节。每票各计一次 7、11、13，合计 31。'}


def main():
    with TemporaryDirectory(prefix='haizhan-demo-') as directory:
        result = run_demo(Path(directory))
    print('原盘已改排为 B、C、A，旧票续领 B、C，新票领 B、C、A。')
    print('两张核账重开后各为 31 微应变。')
    print('POINTWISE_SCENARIO ' + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
