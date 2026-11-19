EXPECTED_ORIGINALS = {
    'A': ('海栈站/东脚/E04', 7, b'A\x00\x07\xff'),
    'B': ('海栈站/西脚/W02', 11, b'B\x00\x0b\n'),
    'C': ('海栈站/栈台/P03', 13, b'C\x00\x0d\x80'),
}


def assert_originals(case, lines, ordered_ids):
    case.assertEqual(tuple(line.original_id for line in lines), tuple(ordered_ids))
    for line in lines:
        case.assertEqual((line.origin, line.reading, line.payload), EXPECTED_ORIGINALS[line.original_id])
        case.assertIs(type(line.reading), int)


def assert_slots(case, pages, identities):
    case.assertEqual(tuple(image.original_id if image is not None else None for image in pages), tuple(identities))
    assert_originals(case, tuple(image for image in pages if image is not None),
                     tuple(identity for identity in identities if identity is not None))
