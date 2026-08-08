"""Gap 1, continued - the diagram assumes one clean question per turn.

Real questions are compound and conversational: "we switched to Compleet in
March, does my son's dental work fall under that or under the basic policy?"
That is three subqueries, and a single embedding of the whole sentence
retrieves the average of them, which is nothing in particular.

Agentic retrieval decomposes the query, runs the subqueries in parallel,
reranks each, and merges. The activity log tells you what it actually did -
which is the part you want in an audit trail.

Extractive retrieval is GA in api-version 2026-04-01. Query planning, answer
synthesis, and configurable reasoning effort are preview-only and require
2026-05-01-preview, so this sample needs the preview package:

    pip install --pre azure-search-documents

Run:  python -m 01_retrieval.agentic_retrieve
"""

from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    SearchIndexKnowledgeSourceParams,
)

from common.clients import credential
from common.config import Settings

GROUNDING_INSTRUCTION = (
    "You answer questions about health insurance policy conditions. "
    "Sources are JSON with a ref_id that must be cited in the answer. "
    "If the sources do not contain the answer, respond exactly with 'Ik weet het niet'."
)

COMPOUND_QUESTION = (
    "We zijn in maart overgestapt naar het Compleet pakket. Valt de tandarts "
    "van mijn zoon van 12 daaronder, of onder de basisverzekering, en geldt "
    "het eigen risico daarvoor?"
)


def main() -> None:
    settings = Settings.load()

    client = KnowledgeBaseRetrievalClient(
        endpoint=settings.search_endpoint,
        knowledge_base_name=settings.knowledge_base_name,
        credential=credential(),
    )

    request = KnowledgeBaseRetrievalRequest(
        messages=[
            KnowledgeBaseMessage(
                role="assistant",
                content=[KnowledgeBaseMessageTextContent(text=GROUNDING_INSTRUCTION)],
            ),
            KnowledgeBaseMessage(
                role="user",
                content=[KnowledgeBaseMessageTextContent(text=COMPOUND_QUESTION)],
            ),
        ],
        knowledge_source_params=[
            SearchIndexKnowledgeSourceParams(
                knowledge_source_name=f"{settings.index_name}-ks",
                # Never let a partial answer look like a complete one.
                fail_on_error=True,
                always_query_source=True,
                include_references=True,
            )
        ],
        include_activity=True,
        output_mode="extractedData",
        max_output_documents=8,
    )

    result = client.retrieve(request)

    print("--- grounding data ---")
    print(result.response[0].content[0].text[:1200])

    print("\n--- query plan (this is your audit trail) ---")
    for entry in result.activity or []:
        args = getattr(entry, "search_index_arguments", None)
        subquery = getattr(args, "search", None) if args else None
        print(f"  {entry.type:22} {subquery or ''}")

    print("\n--- references ---")
    for ref in result.references or []:
        print(f"  ref_id={ref.id}  docKey={ref.doc_key}")


if __name__ == "__main__":
    main()
