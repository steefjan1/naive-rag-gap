"""Gap 3 - the one the diagram leaves out entirely.

A single index over documents with different authorisation levels, queried with
no permission filter, is a data breach with a chat interface in front of it.

Two mechanisms, and you should understand both:

  A. Explicit ACL field + OData filter (shown here, GA, works everywhere).
     You own the filter. It is applied server-side by the search engine, never
     by the LLM, and never in the prompt. A filter in the system prompt is not
     a control; it is a suggestion.

  B. Built-in document-level permissions. You set `ingestionPermissionOptions`
     on the knowledge source at ingestion time and pass the end user's token in
     the `x-ms-query-source-authorization` header at query time. As of the
     2026-04-01 GA release this remains preview and requires 2026-05-01-preview.
     Sketched at the bottom of this file.

The rule that survives both: the trimming filter is derived from the caller's
validated token claims, never from anything the user typed.

Run:  python -m 03_permissions.security_trimming
"""

from __future__ import annotations

from dataclasses import dataclass

from azure.search.documents.indexes.models import (
    SearchFieldDataType,
    SimpleField,
)
from azure.search.documents.models import QueryType, VectorizedQuery

from common.clients import index_client, openai_client, search_client
from common.config import Settings

import importlib

_create_index = importlib.import_module("01_retrieval.create_index")
_chunking = importlib.import_module("02_chunking.chunk_strategies")
SEMANTIC_CONFIG_NAME = _create_index.SEMANTIC_CONFIG_NAME


@dataclass(frozen=True)
class Caller:
    """Whatever your gateway produced after validating the incoming token."""

    name: str
    group_ids: tuple[str, ...]


# Two callers. One is allowed to see the restricted work instruction, one is not.
CUSTOMER_AGENT = Caller("customer service agent", ("all-employees", "customer-facing"))
CLAIMS_ASSESSOR = Caller("claims assessor", ("all-employees", "claims-assessors"))

PROBE = "Hoeveel coulance mag een behandelaar toekennen zonder tweede handtekening?"


def build_acl_index(settings: Settings):
    """Same index as gap 1, plus a filterable collection of permitted groups."""
    index = _create_index.build_index(settings, settings.acl_index_name)
    index.fields.append(
        SimpleField(
            name="group_ids",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
        )
    )
    return index


def trimming_filter(caller: Caller) -> str:
    """Build the OData filter from validated claims.

    `search.in` is the right function here: it is a set membership test over a
    collection field, and it does not string-concatenate user input into the
    filter expression.
    """
    if not caller.group_ids:
        # Fail closed. An empty group list means "see nothing", never "see all".
        return "group_ids/any(g: g eq '__none__')"
    joined = ",".join(caller.group_ids)
    return f"group_ids/any(g: search.in(g, '{joined}', ','))"


def query_as(settings, caller: Caller, question: str, apply_trimming: bool = True):
    client = search_client(settings, settings.acl_index_name)
    embedded = openai_client(settings).embeddings.create(
        model=settings.embedding_deployment, input=[question]
    ).data[0].embedding
    vector_query = VectorizedQuery(
        vector=embedded, k_nearest_neighbors=50, fields="content_vector"
    )
    return list(
        client.search(
            search_text=question,
            vector_queries=[vector_query],
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name=SEMANTIC_CONFIG_NAME,
            filter=trimming_filter(caller) if apply_trimming else None,
            select=["chunk_id", "doc_id", "title", "classification"],
            top=5,
        )
    )


def main() -> None:
    settings = Settings.load()

    print("--- with trimming (correct) ---")
    for caller in (CUSTOMER_AGENT, CLAIMS_ASSESSOR):
        hits = query_as(settings, caller, PROBE)
        docs = sorted({h["doc_id"] for h in hits})
        print(f"  {caller.name:24} -> {docs or '(nothing)'}")

    print("\n--- without trimming (the diagram's pipeline) ---")
    hits = query_as(settings, CUSTOMER_AGENT, PROBE, apply_trimming=False)
    print(f"  {CUSTOMER_AGENT.name:24} -> {sorted({h['doc_id'] for h in hits})}")

    # The assertion is the point of the sample. Run it in CI.
    leaked = [
        h for h in query_as(settings, CUSTOMER_AGENT, PROBE) if h["doc_id"] == "WI-CLAIM-014"
    ]
    assert not leaked, "LEAK: restricted work instruction returned to an unauthorised caller"
    print("\nLeak test passed.")


# ---------------------------------------------------------------------------
# Mechanism B, for reference. Requires `pip install --pre azure-search-documents`
# and api-version 2026-05-01-preview. The knowledge source must have been
# created with ingestionPermissionOptions, or results come back UNFILTERED
# regardless of the header - which is the failure mode worth knowing about.
#
#   from common.clients import credential, user_search_token
#   result = kb_client.retrieve(
#       retrieval_request=request,
#       x_ms_query_source_authorization=user_search_token(),
#   )
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    main()
