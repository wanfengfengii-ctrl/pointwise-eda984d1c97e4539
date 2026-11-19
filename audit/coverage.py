from delivery.provenance import DeliveryLine
from delivery.ticket import TicketOrder


class CoverageMismatch(ValueError):
    pass


def verify_coverage(fixed_ticket: TicketOrder, lines) -> tuple[DeliveryLine, ...]:
    try:
        submitted = tuple(lines)
    except TypeError as exc:
        raise CoverageMismatch('expected the full ordered list of delivery lines') from exc
    if len(submitted) != len(fixed_ticket.original_ids):
        raise CoverageMismatch('the number of submitted originals differs from the ticket')
    for position, (wanted, line) in enumerate(zip(fixed_ticket.original_ids, submitted)):
        if not isinstance(line, DeliveryLine) or line.original_id != wanted:
            raise CoverageMismatch(f'ticket position {position} requires original {wanted!r}')
    return submitted
