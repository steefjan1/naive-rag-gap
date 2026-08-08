"""Chunk the sample corpus and push it into the index.

Uses the structure-aware chunker from gap 2, because the two gaps are not
independent: hybrid retrieval cannot rescue a chunk that lost its table header.

Run:  python -m 01_retrieval.index_documents
"""

from pathlib import Path

from common.clients import openai_client, search_client
from common.config import Settings

import importlib

_chunking = importlib.import_module("02_chunking.chunk_strategies")
parse_front_matter = _chunking.parse_front_matter
structure_aware = _chunking.structure_aware

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"


def embed(client, deployment: str, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=deployment, input=texts)
    return [item.embedding for item in response.data]


def main() -> None:
    settings = Settings.load()
    oai = openai_client(settings)
    search = search_client(settings)

    documents = []
    for path in sorted(DATA_DIR.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        # The restricted document is deliberately excluded from this index.
        # It belongs in the ACL index in gap 3, where access is enforced
        # rather than assumed.
        if meta.get("classification") == "internal-restricted":
            print(f"skipping {path.name} (restricted - see 03_permissions)")
            continue
        for chunk in structure_aware(body, meta):
            documents.append(
                {
                    "chunk_id": chunk.chunk_id.replace("#", "_"),
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "section": chunk.section,
                    "classification": chunk.metadata.get("classification", "public"),
                    "effective_from": f"{chunk.metadata.get('effective_from')}T00:00:00Z",
                }
            )

    vectors = embed(
        oai, settings.embedding_deployment, [d["content"] for d in documents]
    )
    for doc, vector in zip(documents, vectors):
        doc["content_vector"] = vector

    result = search.upload_documents(documents=documents)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"Uploaded {succeeded}/{len(documents)} chunks to '{settings.index_name}'.")


if __name__ == "__main__":
    main()
