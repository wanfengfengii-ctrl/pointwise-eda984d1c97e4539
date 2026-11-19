from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    original_id: str
    origin: str
    reading: int
    digest: str


@dataclass(frozen=True, slots=True)
class VolumeManifest:
    volume_id: str
    entries: tuple[ManifestEntry, ...]

    def by_id(self) -> dict[str, ManifestEntry]:
        return {entry.original_id: entry for entry in self.entries}

    @property
    def original_ids(self) -> tuple[str, ...]:
        return tuple(entry.original_id for entry in self.entries)


def require_text(value: str, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f'{field} must be nonblank text')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{field} must be valid UTF-8 text') from exc
    return value


def original_digest(payload: bytes) -> str:
    if type(payload) is not bytes:
        raise ValueError('original payload must be bytes')
    return sha256(payload).hexdigest()


def normalize_manifest(manifest: VolumeManifest) -> VolumeManifest:
    if not isinstance(manifest, VolumeManifest):
        raise ValueError('expected a volume manifest')
    volume_id = require_text(manifest.volume_id, 'volume identifier')
    entries = tuple(manifest.entries)
    seen = set()
    for entry in entries:
        if not isinstance(entry, ManifestEntry):
            raise ValueError('expected a manifest entry')
        identity = require_text(entry.original_id, 'original identifier')
        require_text(entry.origin, 'original source')
        if identity in seen:
            raise ValueError(f'duplicate original identifier {identity!r}')
        if type(entry.reading) is not int or entry.reading < 0:
            raise ValueError(f'invalid microstrain reading for {identity!r}')
        if (type(entry.digest) is not str or len(entry.digest) != 64
                or any(char not in '0123456789abcdef' for char in entry.digest)):
            raise ValueError(f'invalid SHA-256 digest for {identity!r}')
        seen.add(identity)
    return VolumeManifest(volume_id, entries)


def matches_entry(entry: ManifestEntry, original_id: str, origin: str,
                  reading: int, payload: bytes) -> bool:
    return (original_id == entry.original_id and origin == entry.origin
            and type(reading) is int and reading == entry.reading
            and type(payload) is bytes and original_digest(payload) == entry.digest)
