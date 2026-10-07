"""Replay exactly one retained HPG FY2025 capital-note page. No network or production writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_common_shares_official_evidence_acquisition import qualify_retained_common_share_note
from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT
from official_financial_ocr_table_evidence import DEFAULT_ENGINE, OCR_CONFIG, _parse_tsv

SHA = 'f38c5f75becf7d3f145d27183eec81f119fd4f75e378b983a2763ddc3f7e0c07'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--landing-root', type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--knowledge-at', required=True, help='Timezone-aware qualification observation; never before retention')
    args = parser.parse_args()
    # Explicit fixed page/orientation after source-image review; no orientation search.
    import fitz
    evidence = args.landing_root / 'currency-refresh-20260929'
    manifest = json.loads((evidence / 'official_document_acquisition_manifest.json').read_text(encoding='utf8'))
    records = [r for r in manifest['records'] if r.get('sha256') == SHA and r.get('acquisition_status') == 'retained']
    if len(records) != 1: raise ValueError('RETAINED_DOCUMENT_NOT_UNIQUE')
    record = records[0]
    source = evidence / record['relative_path']
    if hashlib.sha256(source.read_bytes()).hexdigest() != SHA: raise ValueError('RETAINED_SOURCE_HASH_MISMATCH')
    with fitz.open(source) as pdf:
        page = pdf[40]
        page.set_rotation(270)
        image = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
    image_hash = hashlib.sha256(image).hexdigest()
    result = subprocess.run([str(DEFAULT_ENGINE), 'stdin', 'stdout', '-l', OCR_CONFIG['language'],
        '--psm', str(OCR_CONFIG['psm']), 'tsv'], input=image, capture_output=True, check=True)
    materialization = {'document_sha256': SHA, 'page_number': 41, 'rotation': 270,
        'rendered_image_sha256': image_hash, 'tokens': _parse_tsv(result.stdout, page_number=41, image_sha256=image_hash)}
    overlay = ROOT / 'derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl'
    assurance = next(json.loads(line)['assurance_evidence'] for line in overlay.read_text(encoding='utf8').splitlines()
        if json.loads(line)['document_sha256'] == SHA)
    observation = qualify_retained_common_share_note(materialization=materialization, document=record,
        assurance=assurance, effective_date='2025-12-31', knowledge_available_at=args.knowledge_at)
    args.output_root.mkdir(parents=True, exist_ok=True)
    target = args.output_root / 'share_observation.json'
    text = json.dumps(observation, ensure_ascii=False, indent=2) + '\n'
    if target.exists() and target.read_text(encoding='utf8') != text:
        raise ValueError('REFUSING_TO_OVERWRITE_DISTINCT_SHARE_OBSERVATION')
    if not target.exists(): target.write_text(text, encoding='utf8')
    print(json.dumps({'citation_id': observation['citation_id'], 'value': observation['value'],
        'effective_date': observation['effective_date'], 'network_requests': 0, 'pages_read': 1}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
