from audit.records import AuditResult, load_audit_record
from delivery.page import collect_originals
from intake.catalog import open_catalog


class UnknownAuditNumber(LookupError):
    pass


def readback(root, audit_number: int) -> AuditResult:
    with open_catalog(root) as db:
        record = load_audit_record(db, audit_number)
    if record is None:
        raise UnknownAuditNumber(audit_number)
    entries = tuple(line.as_manifest_entry() for line in record.lines)
    return AuditResult(record, collect_originals(root, record.volume_id, entries))
