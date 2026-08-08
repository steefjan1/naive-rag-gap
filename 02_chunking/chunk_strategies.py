"""Gap 2 - "chunk text for sharp recall" is one bullet hiding most of the work.

Three strategies against the same document. The third one is boring and wins.

Run:  python -m 02_chunking.chunk_strategies
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    content: str
    metadata: dict = field(default_factory=dict)

    @property
    def splits_a_table(self) -> bool:
        """A chunk that contains table rows but no header row is unanswerable.

        The model sees `| EUR 400 | EUR 14,00 | BAS-VR-400 |` with no column
        names and will happily invent what the columns mean.
        """
        rows = [line for line in self.content.splitlines() if line.strip().startswith("|")]
        if not rows:
            return False
        has_separator = any(set(row.replace("|", "").strip()) <= set("- :") for row in rows)
        return not has_separator


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, raw, body = text.split("---", 2)
    meta: dict = {}
    for line in raw.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, body.strip()


def fixed_size(text: str, meta: dict, size: int = 400, overlap: int = 50) -> list[Chunk]:
    """Strategy A: split on character count. What every quickstart does."""
    chunks = []
    step = size - overlap
    for i, start in enumerate(range(0, len(text), step)):
        window = text[start : start + size]
        if not window.strip():
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{meta['doc_id']}#{i}",
                doc_id=meta["doc_id"],
                title=meta.get("title", ""),
                section="",
                content=window,
            )
        )
    return chunks


def recursive_split(text: str, meta: dict, size: int = 800) -> list[Chunk]:
    """Strategy B: split on paragraph boundaries, pack up to size.

    Better than A, still splits a long table across two chunks.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buffer = [], ""
    for para in paragraphs:
        if len(buffer) + len(para) > size and buffer:
            chunks.append(buffer)
            buffer = para
        else:
            buffer = f"{buffer}\n\n{para}" if buffer else para
    if buffer:
        chunks.append(buffer)
    return [
        Chunk(
            chunk_id=f"{meta['doc_id']}#{i}",
            doc_id=meta["doc_id"],
            title=meta.get("title", ""),
            section="",
            content=body,
        )
        for i, body in enumerate(chunks)
    ]


def structure_aware(text: str, meta: dict) -> list[Chunk]:
    """Strategy C: split on headings, keep tables whole, carry context down.

    Two things matter here and neither is glamorous:
      1. A table is never split. If a section is oversized, the prose splits
         and the table stays intact with its header.
      2. Every chunk carries the document title and its section heading in the
         text itself, so a chunk retrieved in isolation still says what it is.
    """
    sections = re.split(r"\n(?=#{1,3} )", text)
    chunks = []
    for i, section in enumerate(sections):
        body = section.strip()
        if not body:
            continue
        heading = body.splitlines()[0].lstrip("# ").strip()
        contextualised = (
            f"[{meta.get('title', '')} | {heading}]\n\n{body}"
        )
        chunks.append(
            Chunk(
                chunk_id=f"{meta['doc_id']}#{i}",
                doc_id=meta["doc_id"],
                title=meta.get("title", ""),
                section=heading,
                content=contextualised,
                metadata={
                    "classification": meta.get("classification", "unknown"),
                    "effective_from": meta.get("effective_from"),
                    "group_ids": meta.get("group_ids", "[]"),
                },
            )
        )
    return chunks


STRATEGIES = {
    "fixed-size(400/50)": fixed_size,
    "recursive-paragraph(800)": recursive_split,
    "structure-aware": structure_aware,
}


def main() -> None:
    source = DATA_DIR / "polis-basis-2026.md"
    meta, body = parse_front_matter(source.read_text(encoding="utf-8"))

    for name, fn in STRATEGIES.items():
        chunks = fn(body, meta)
        broken = sum(c.splits_a_table for c in chunks)
        orphaned = sum(1 for c in chunks if not c.section)
        print(f"\n=== {name} ===")
        print(f"  chunks: {len(chunks)}")
        print(f"  chunks with headerless table rows: {broken}")
        print(f"  chunks with no section context:    {orphaned}")
        for c in chunks:
            if c.splits_a_table:
                preview = c.content.strip().splitlines()[0][:70]
                print(f"    ! {c.chunk_id}: {preview}")

    print(
        "\nThe headerless-table count is the number of chunks that can produce a "
        "confident wrong answer about a product code."
    )


if __name__ == "__main__":
    main()
