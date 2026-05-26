"""UIF issues via kardex_snapshot (same engine as SISGEN search)."""

from uif.services.kardex_snapshot import validate_kardex_number

from compliance.services.payload import build_uif_block


def collect_uif_issues(kardex: str) -> dict:
    return build_uif_block(validate_kardex_number(kardex))
