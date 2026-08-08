"""Create the ACL index and load all three documents into it, including the
restricted one.

This index deliberately contains content the customer-facing caller must never
see. That is the whole point: the restricted document is present and reachable,
and only the filter keeps it away.

Run:  python -m 03_permissions.setup_acl_index
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from common.clients import index_client, openai_client, search_client
from common.config import Settings

_chunking = importlib.import_module("02_chunking.chunk_strategies")
_trimming = importlib.import_module("03_permissions.security_trimming")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"


def parse_group_ids(raw: str | None) -> list[str]:
    """Front matter stores group_ids as a JSON-ish list literal."""
    if not raw:
        return []
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def main() -> None:
    settings = Settings.load()

    index_client(settings).create_or_update_index(_trimming.build_acl_index(settings))
    print(f"Index '{settings.acl_index_name}' created or updated.")

    documents = []
    for path in sorted(DATA_DIR.glob("*.md")):
        meta, body = _chunking.parse_front_matter(path.read_text(encoding="utf-8"))
        groups = parse_group_ids(meta.get("group_ids"))
        if not groups:
            raise RuntimeError(
                f"{path.name} has no group_ids. Fail closed: refusing to index a "
                "document with no access list rather than defaulting it to public."
            )
        for chunk in _chunking.structure_aware(body, meta):
            documents.append(
                {
                    "chunk_id": chunk.chunk_id.replace("#", "_"),
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "section": chunk.section,
                    "classification": meta.get("classification", "unknown"),
                    "effective_from": f"{meta.get('effective_from')}T00:00:00Z",
                    "group_ids": groups,
                }
            )

    oai = openai_client(settings)
    response = oai.embeddings.create(
        model=settings.embedding_deployment, input=[d["content"] for d in documents]
    )
    for doc, item in zip(documents, response.data):
        doc["content_vector"] = item.embedding

    result = search_client(settings, settings.acl_index_name).upload_documents(documents)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"Uploaded {succeeded}/{len(documents)} chunks (including restricted content).")

    restricted = sum(1 for d in documents if d["doc_id"] == "WI-CLAIM-014")
    print(f"{restricted} restricted chunks are now in the index and reachable without a filter.")


if __name__ == "__main__":
    main()
