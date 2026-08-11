"""Chunk filing text and build the vector index.

Design note, worth explaining in an interview.

An earlier version split each filing into labeled sections (Item 7 MD&A,
Item 1A Risk Factors) and tagged every chunk with its section. That looked
principled but was fragile: 10-Q and 10-K item numbering differs, and the
table of contents repeats the labels, so the splitter routinely mislabeled
MD&A content as risk factors. Retrieval then missed the very passages that
answered performance questions.

The fix is to stop gating on fragile labels. Index the full filing body and
let semantic search find the right passage by meaning. A lightweight section
GUESS is still attached as a hint for display and optional filtering, but it
never blocks retrieval. This removed the "not in the excerpts" failures on
margin and driver questions.
"""

import json
import re
from pathlib import Path

import chromadb
from bs4 import BeautifulSoup

RAW_DIR = Path("data/raw")
CHROMA_DIR = "data/chroma"
COLLECTION = "filings"

CHUNK_CHARS = 2400      # ~600 tokens, smaller so retrieval is more precise
CHUNK_OVERLAP = 400

# Boilerplate we skip so the index is not polluted with legal filler.
SKIP_MARKERS = (
    "table of contents",
    "incorporated by reference",
    "exhibit index",
)

# Lightweight hint only. Never used to gate retrieval.
SECTION_HINTS = {
    "mdna": ("management's discussion", "results of operations",
             "operating margin", "net revenue", "provision for credit"),
    "risk_factors": ("risk factors", "could adversely affect",
                     "we are subject to", "may harm our"),
    "business": ("our business", "we operate", "products and services"),
}


def html_to_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text)


def guess_section(chunk_text: str) -> str:
    """Best-effort label from content. A hint, not a gate."""
    lowered = chunk_text.lower()
    scores = {
        name: sum(lowered.count(kw) for kw in kws)
        for name, kws in SECTION_HINTS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def chunk(text: str) -> list[str]:
    chunks, cursor = [], 0
    while cursor < len(text):
        piece = text[cursor:cursor + CHUNK_CHARS].strip()
        low = piece.lower()
        is_boiler = len(piece) < 300 or any(m in low[:120] for m in SKIP_MARKERS)
        if not is_boiler:
            chunks.append(piece)
        cursor += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Rebuild clean so old mislabeled chunks do not linger.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.get_or_create_collection(COLLECTION)

    total = 0
    for manifest_path in RAW_DIR.glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text())

        for filing in manifest:
            path = Path(filing["path"])
            if not path.exists():
                continue

            text = html_to_text(path)
            pieces = chunk(text)

            ids, docs, metas = [], [], []
            for i, piece in enumerate(pieces):
                ids.append(f"{filing['ticker']}_{filing['filing_date']}_{i}")
                docs.append(piece)
                metas.append({
                    "ticker": filing["ticker"],
                    "form": filing["form"],
                    "filing_date": filing["filing_date"],
                    "section": guess_section(piece),
                    "chunk_index": i,
                })

            # Upsert in batches to stay well under memory limits on free hosting.
            for j in range(0, len(ids), 200):
                collection.upsert(
                    ids=ids[j:j + 200],
                    documents=docs[j:j + 200],
                    metadatas=metas[j:j + 200],
                )
            total += len(ids)
            print(f"indexed {filing['ticker']} {filing['filing_date']} "
                  f"{filing['form']} ({len(ids)} chunks)")

    print(f"\n{total} chunks in collection '{COLLECTION}'")


if __name__ == "__main__":
    main()
