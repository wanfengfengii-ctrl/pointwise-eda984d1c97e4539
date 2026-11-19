from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VolumeLayout:
    volume_id: str
    normal_count: int

    @property
    def normal_slots(self) -> range:
        return range(1, self.normal_count + 1)

    @property
    def spare_slot(self) -> int:
        return self.normal_count + 1

    @property
    def all_slots(self) -> range:
        return range(1, self.spare_slot + 1)


def make_layout(volume_id: str, normal_count: int) -> VolumeLayout:
    if type(volume_id) is not str or not volume_id.strip():
        raise ValueError('layout requires a volume identifier')
    if type(normal_count) is not int or normal_count < 0:
        raise ValueError('normal page count must be a nonnegative integer')
    return VolumeLayout(volume_id, normal_count)


def validate_slot(layout: VolumeLayout, slot_number: int) -> None:
    if type(slot_number) is not int or slot_number not in layout.all_slots:
        raise ValueError(f'invalid physical slot {slot_number!r} for {layout.volume_id!r}')
