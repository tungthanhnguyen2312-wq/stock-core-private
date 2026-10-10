"""Compatibility launcher for the existing offline official-document import CLI."""
from stocklookup_core.evidence.official_document_acquisition import main

if __name__ == "__main__":
    raise SystemExit(main())
