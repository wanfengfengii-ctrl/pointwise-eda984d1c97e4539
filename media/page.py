import json
from dataclasses import dataclass


class InvalidPageImage(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PageImage:
    original_id: str
    origin: str
    reading: int
    payload: bytes


def _check_header(original_id, origin, reading) -> None:
    if type(original_id) is not str or not original_id.strip() or type(origin) is not str or not origin.strip():
        raise InvalidPageImage('a page needs its original identifier and source')
    if type(reading) is not int or reading < 0:
        raise InvalidPageImage('a page needs an exact nonnegative reading')


def pack_page(image: PageImage | None) -> bytes | None:
    if image is None:
        return None
    if not isinstance(image, PageImage) or type(image.payload) is not bytes:
        raise InvalidPageImage('a complete page needs a byte payload')
    _check_header(image.original_id, image.origin, image.reading)
    header = json.dumps([image.original_id, image.origin, format(image.reading, 'x')]).encode('ascii')
    return len(header).to_bytes(4, 'big') + header + image.payload


def unpack_page(packed: bytes | None) -> PageImage | None:
    if packed is None:
        return None
    if type(packed) is not bytes or len(packed) < 4:
        raise InvalidPageImage('missing page header length')
    header_end = 4 + int.from_bytes(packed[:4], 'big')
    if header_end <= 4 or header_end > len(packed):
        raise InvalidPageImage('truncated page header')
    try:
        fields = json.loads(packed[4:header_end].decode('ascii'))
        if not isinstance(fields, list) or len(fields) != 3:
            raise InvalidPageImage('invalid page header fields')
        original_id, origin, reading_hex = fields
        if (type(reading_hex) is not str or not reading_hex
                or any(char not in '0123456789abcdef' for char in reading_hex)):
            raise InvalidPageImage('invalid encoded page reading')
        reading = int(reading_hex, 16)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidPageImage('invalid encoded page header') from exc
    _check_header(original_id, origin, reading)
    return PageImage(original_id, origin, reading, packed[header_end:])
