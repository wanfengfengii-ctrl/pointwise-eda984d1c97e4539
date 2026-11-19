from delivery.provenance import DeliveryLine


def sum_microstrain(verified_lines: tuple[DeliveryLine, ...]) -> int:
    return sum(line.reading for line in verified_lines)
