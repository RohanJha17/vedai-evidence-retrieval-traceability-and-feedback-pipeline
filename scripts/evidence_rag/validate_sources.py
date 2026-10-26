from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panchakarma_evidence.retrieval import load_corpus  # noqa: E402


import argparse

def main() -> None:
    """Validate the curated corpus and check local PDF copies against the preserved SHA-256 log."""
    parser = argparse.ArgumentParser(description="Validate corpus chunks and source documents.")
    parser.add_argument("--corpus", type=Path, default=ROOT / "research_dataset" / "corpus_chunks.jsonl")
    args = parser.parse_args()
    corpus_path = args.corpus
    doc_path = ROOT / "research_dataset" / "README.md"
    if not doc_path.exists():
        doc_path = ROOT / "research_dataset" / "extraction_log.md"
    corpus = load_corpus(corpus_path)
    log = doc_path.read_text(encoding="utf-8")
    entries = re.findall(r"- Local file: .*?/([^/\\]+?) \([^\r\n]*\)\r?\n- SHA-256: ([a-f0-9]{64})", log)
    if not entries:
        raise SystemExit(f"No source file hashes found in {doc_path.relative_to(ROOT)}")
    missing = []
    mismatches = []
    for filename, expected_hash in entries:
        source = ROOT / "research_dataset" / "source_documents" / filename
        if not source.exists():
            missing.append(filename)
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != expected_hash:
            mismatches.append(filename)
    if missing or mismatches:
        if missing:
            print("Local source copies not present (corpus remains usable): " + ", ".join(missing))
        if mismatches:
            raise SystemExit("Source hash mismatch: " + ", ".join(mismatches))
    print(f"Validated {len(corpus)} curated corpus records and {len(entries) - len(missing)} local source PDF hashes.")
    print("This command validates the human-curated corpus; it does not OCR or claim expert review.")


if __name__ == "__main__":
    main()
