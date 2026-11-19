from audit.coverage import CoverageMismatch, verify_coverage
from audit.records import AuditResult, store_audit_record
from audit.totals import sum_microstrain
from delivery.provenance import ProvenanceMismatch, verify_provenance
from delivery.ticket import load_ticket
from intake.catalog import load_accepted_manifest, open_catalog


class AuditCloseError(ValueError):
    pass


def close(root, ticket_number: int, lines) -> AuditResult:
    with open_catalog(root, write=True) as db:
        fixed_ticket = load_ticket(db, ticket_number)
        by_id = load_accepted_manifest(db, fixed_ticket.volume_id).by_id()
        try:
            verified = verify_coverage(fixed_ticket, lines)
            entries = tuple(by_id[line.original_id] for line in verified)
            for entry, line in zip(entries, verified):
                verify_provenance(entry, line)
        except (CoverageMismatch, ProvenanceMismatch) as exc:
            raise AuditCloseError(str(exc)) from exc
        record = store_audit_record(db, fixed_ticket, entries, sum_microstrain(verified))
        return AuditResult(record, verified)
