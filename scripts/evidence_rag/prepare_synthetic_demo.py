from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PASSAGES = [
    ("SYN-AYU-001", "SRC-AYUSOFT-PK", "Ayusoft Panchakarma overview", "2021-06-16 page update", "Panchakarma meaning", "Panchakarma is described by the Ayusoft overview as five therapeutic procedures and is also associated there with the idea of purification.", "en", "https://ayusoft.ayush.gov.in/hi/panchakarma/"),
    ("SYN-AYU-002", "SRC-AYUSOFT-PK", "Ayusoft Panchakarma overview", "2021-06-16 page update", "Five procedures", "The Ayusoft overview lists Vamana, Virechana, Basti, Nasya, and Raktamokshana among the five procedures it describes.", "en", "https://ayusoft.ayush.gov.in/hi/panchakarma/"),
    ("SYN-AYU-003", "SRC-AYUSOFT-PK", "Ayusoft Panchakarma overview", "2021-06-16 page update", "Procedure phases", "The Ayusoft overview names Poorvakarma, Pradhanakarma, and Paschatkarma as broad phases associated with a procedure.", "en", "https://ayusoft.ayush.gov.in/hi/panchakarma/"),
    ("SYN-AYU-004", "SRC-AYUSOFT-PK", "Ayusoft Panchakarma overview", "2021-06-16 page update", "Prerequisite concepts", "The Ayusoft overview describes oleation and sudation as prerequisites in its general account of these procedures.", "en", "https://ayusoft.ayush.gov.in/hi/panchakarma/"),
    ("SYN-NCISM-001", "SRC-NCISM-AYPG-AB-PK", "NCISM Applied Basics of Panchakarma curriculum", "Applicable from 2024-25", "Shodhana topics", "The NCISM Panchakarma curriculum lists the definition of Karma, Trividha Karma for Shodhana, and the importance of Panchakarma in health and disease as learning topics.", "en", "https://www.ncismindia.org/NCISM-AYPG-AB-PK.pdf"),
    ("SYN-NCISM-002", "SRC-NCISM-AYPG-AB-PK", "NCISM Applied Basics of Panchakarma curriculum", "Applicable from 2024-25", "Assessment topics", "The NCISM Panchakarma curriculum includes applied examination topics such as Trividha, Shadvidha, Ashtavidha, and Dashavidha Pariksha.", "en", "https://www.ncismindia.org/NCISM-AYPG-AB-PK.pdf"),
    ("SYN-NCISM-003", "SRC-NCISM-AYPG-AB-PK", "NCISM Applied Basics of Panchakarma curriculum", "Applicable from 2024-25", "Purva and Pashchata Karma", "The NCISM Panchakarma curriculum names the importance of Purva and Pashchata Karma in Shodhana and includes Parihara Vishaya as a topic.", "en", "https://www.ncismindia.org/NCISM-AYPG-AB-PK.pdf"),
    ("SYN-NCISM-004", "SRC-NCISM-AYPG-AB-PK", "NCISM Applied Basics of Panchakarma curriculum", "Applicable from 2024-25", "Research topics", "The NCISM Panchakarma curriculum includes areas of research in Panchakarma among its listed learning topics.", "en", "https://www.ncismindia.org/NCISM-AYPG-AB-PK.pdf"),
]


def main() -> None:
    records = []
    for chunk_id, source_id, title, version, section, text, language, url in PASSAGES:
        records.append({
            "chunk_id": chunk_id, "source_id": source_id, "document_title": title,
            "document_version": version, "page_start": None, "page_end": None,
            "section_heading": section, "text": text, "language": language, "source_url": url,
            "content_hash_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "extraction_method": "synthetic_paraphrase_authored_for_retrieval_pipeline_demo",
            "verification_status": "synthetic_reference_paraphrase_not_source_evidence",
            "rights_note": "Newly written synthetic paraphrase for software demonstration; not source text and not an evidence passage.",
        })
    output = ROOT / "research_dataset" / "synthetic_demo_corpus.jsonl"
    output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} synthetic demo passages to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
