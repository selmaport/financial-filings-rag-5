"""Chunk filing narrative sections and build the vector index.

Chunking strategy is a real design decision, not boilerplate. Filings have
labeled sections (Item 7 MD&A, Item 1A Risk Factors). Splitting on those
boundaries first, then chunking inside them, keeps retrieved passages
attributable to a section. Record this choice and your reasoning in the README.
"""

import json
import re
from pathlib import Path

import chromadb
from bs4 import BeautifulSoup

RAW_DIR = Path("data/raw")
CHROMA_DIR = "data/chroma"
COLLECTION = "filings"

# Sections worth indexing. Everything else is boilerplate or tables.
SECTION_PATTERNS = {
    "mdna": r"item\s*7[.\s]*management.s discussion",
    "risk_factors": r"item\s*1a[.\s]*risk factors",
    "business": r"item\s*1[.\s]*business",
}

CHUNK_CHARS = 3200      # roughly 800 tokens
CHUNK_OVERLAP = 400     # carries context across a boundary


def html_to_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text)


def split_sections(text: str) -> dict[str, str]:
    """Locate labeled sections. Returns whatever it finds, plus a full fallback."""
    lowered = text.lower()
    hits = []
    for name, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, lowered)
        if match:
            hits.append((match.start(), name))

    if not hits:
        return {"full_document": text}

    hits.sort()
    sections = {}
    for i, (start, name) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        sections[name] = text[start:end]
    return sections


def chunk(text: str) -> list[str]:
    chunks, cursor = [], 0
    while cursor < len(text):
        piece = text[cursor:cursor + CHUNK_CHARS].strip()
        if len(piece) > 200:  # drop fragments too small to be useful
            chunks.append(piece)
        cursor += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(COLLECTION)

    total = 0
    for manifest_path in RAW_DIR.glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text())

        for filing in manifest:
            path = Path(filing["path"])
            if not path.exists():
                continue

            text = html_to_text(path)
            for section_name, section_text in split_sections(text).items():
                for i, piece in enumerate(chunk(section_text)):
                    doc_id = f"{filing['ticker']}_{filing['filing_date']}_{section_name}_{i}"
                    collection.upsert(
                        ids=[doc_id],
                        documents=[piece],
                        metadatas=[{
                            "ticker": filing["ticker"],
                            "form": filing["form"],
                            "filing_date": filing["filing_date"],
                            "section": section_name,
                            "chunk_index": i,
                        }],
                    )
                    total += 1
            print(f"indexed {filing['ticker']} {filing['filing_date']} {filing['form']}")

    print(f"\n{total} chunks in collection '{COLLECTION}'")


if __name__ == "__main__":
    main()
