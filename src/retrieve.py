"""Retrieve filing passages and generate a grounded, cited answer.

Uses the Google Gemini API, which has a free tier that covers this project.
Get a key at aistudio.google.com. No credit card required.

Embeddings run locally through ChromaDB's default model, so the retrieval
half of this system costs nothing and needs no key at all.

Retrieval design note, worth explaining in an interview.

An earlier version split filings into labeled sections and rebalanced
retrieval toward MD&A. The section labels turned out to be unreliable
(the item numbering differs across 10-K and 10-Q, and the table of contents
repeats the labels), so the real fix was in indexing: index the full filing
body and let semantic search find the right passage by meaning. Retrieval
here is therefore plain top-k, which is both simpler and more robust.

The system prompt is deliberately strict about refusing when the retrieved
context lacks the answer. Refusal rate is a scored metric. A system that
always answers is not trustworthy.
"""

import os

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

CHROMA_DIR = "data/chroma"
COLLECTION = "filings"
DEFAULT_K = 8
MODEL = "gemini-3.6-flash"

SYSTEM_PROMPT = """You answer questions about SEC filings using only the provided excerpts.

Rules:
1. Use only the excerpts. Do not use outside knowledge about the company.
2. Cite every factual claim with the excerpt number, like [1] or [2].
3. If the excerpts do not fully answer the question, answer what they DO support
   and state plainly what is missing. Do not refuse wholesale when partial
   evidence exists. Only refuse entirely when nothing relevant is present.
4. If the question contains a false or unsupported premise, correct it.
5. Distinguish what management states from what the numbers show.
6. Be concise. An analyst is reading this."""


def _client_collection():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_collection(COLLECTION)


def search(
    query: str,
    tickers: list[str] | None = None,
    k: int = DEFAULT_K,
    section: str | None = None,
) -> list[dict]:
    """Semantic search over the full filing body.

    The index no longer relies on fragile section labels, so this is plain
    top-k retrieval by meaning. tickers limits the search to one or more
    companies; None searches all of them.
    """
    collection = _client_collection()

    clauses = []
    if tickers:
        clauses.append({"ticker": {"$in": tickers}})
    if section:
        clauses.append({"section": section})

    if len(clauses) > 1:
        where = {"$and": clauses}
    elif clauses:
        where = clauses[0]
    else:
        where = None

    result = collection.query(query_texts=[query], n_results=k, where=where)

    return [
        {"text": doc, "metadata": meta, "distance": dist}
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


def format_context(passages: list[dict]) -> str:
    blocks = []
    for i, p in enumerate(passages, start=1):
        m = p["metadata"]
        header = (
            f"[{i}] {m['ticker']} {m['form']} filed {m['filing_date']}, "
            f"section: {m['section']}"
        )
        blocks.append(f"{header}\n{p['text']}")
    return "\n\n---\n\n".join(blocks)


def answer(
    query: str,
    tickers: list[str] | None = None,
    k: int = DEFAULT_K,
    section: str | None = None,
) -> dict:
    passages = search(query, tickers=tickers, k=k, section=section)

    if not passages:
        return {"answer": "No indexed filings matched that query.", "passages": []}

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,  # deterministic, so eval runs are comparable
        ),
        contents=f"Excerpts:\n\n{format_context(passages)}\n\nQuestion: {query}",
    )

    return {"answer": response.text, "passages": passages}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What drove the change in operating margin?"
    result = answer(q)
    print(result["answer"])
    print("\nSources:")
    for i, p in enumerate(result["passages"], start=1):
        m = p["metadata"]
        print(f"  [{i}] {m['ticker']} {m['filing_date']} {m['section']}")
