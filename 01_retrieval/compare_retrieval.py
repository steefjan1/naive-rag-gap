"""Gap 1 - prove the difference between vector-only and hybrid + reranked.

This is the sample worth running in front of a stakeholder. The queries below
are chosen to be the ones dense retrieval quietly fails: product codes, exact
figures, negation, and near-duplicate distractors.

Run:  python -m 01_retrieval.compare_retrieval
"""

from dataclasses import dataclass

from azure.search.documents.models import QueryType, VectorizedQuery

from common.clients import openai_client, search_client
from common.config import Settings
from .create_index import SEMANTIC_CONFIG_NAME

# Each case names the chunk(s) that would be a correct rank-1 answer. Guessing is
# not evaluation. Several documents now share near-identical structure and
# vocabulary - three "Eigen risico" tables, four "Fysiotherapie" sections - which
# is the point: a corpus with nothing to confuse cannot demonstrate confusion.
CASES = [
    # Same code family, different years. Only 2026 has 400; only 2025 has 350.
    ("Welke korting hoort bij productcode BAS-VR-400?", {"POL-BASIS-2026_1"}),
    ("Welke korting hoort bij productcode BAS-VR-350?", {"POL-BASIS-2025_1"}),
    # Different code family, structurally identical table.
    ("Welke korting hoort bij productcode COL-VR-300?", {"POL-COL-2026_1"}),
    # Year disambiguation on otherwise near-identical prose.
    ("Hoeveel behandelingen fysiotherapie in het Extra pakket in 2025?", {"POL-AANV-2025_1"}),
    ("Geldt in 2026 medische acceptatie voor pakket AANV-CO-03?", {"POL-AANV-2026_3"}),
    # Negation: the answer is that it is NOT covered.
    ("Wordt fysiotherapie in het buitenland vergoed?", {"POL-BUIT-2026_3"}),
    # Different domain, same "vergoeding" vocabulary.
    ("Wat is de maximale vergoeding voor een hoortoestel?", {"REG-HULP-2026_2"}),
    ("Hoe hoog is de eigen bijdrage voor een hoortoestel?", {"REG-HULP-2026_3"}),
    # Withdrawal notice rather than the price table.
    ("Is BAS-VR-350 nog geldig in 2026?", {"POL-BASIS-2026_3"}),
    ("Loopt de collectieve korting door na uitdiensttreding?", {"POL-COL-2026_3"}),
    ("Welk pakket heeft onbeperkte fysiotherapie?", {"POL-AANV-2026_1"}),
]

TOP_K = 5


@dataclass
class Result:
    strategy: str
    hits: int
    mrr: float


def _reciprocal_rank(doc_ids: list[str], expected: set[str]) -> float:
    for position, doc_id in enumerate(doc_ids, start=1):
        if doc_id in expected:
            return 1.0 / position
    return 0.0


def run_strategy(client, strategy: str, query: str, vector: list[float]) -> list[str]:
    # The query vector is computed client-side and reused across all three
    # strategies. Two reasons, and the second one matters more than it looks:
    #
    #   1. Every strategy then searches with an identical vector, so any
    #      difference in the results comes from the retrieval strategy rather
    #      than from a re-embedding.
    #   2. Server-side vectorization (VectorizableTextQuery) makes the search
    #      service call the embedding endpoint on your behalf. That is one more
    #      thing that can fail mid-comparison, and in testing it did - an
    #      intermittent 404 from the vectorization action after roughly ten
    #      calls. Keep the vectorizer on the index (agentic retrieval needs it)
    #      but do not make a measurement depend on it.
    vector_query = VectorizedQuery(
        vector=vector, k_nearest_neighbors=50, fields="content_vector"
    )

    if strategy == "vector-only":
        # This is the diagram's pipeline.
        results = client.search(
            search_text=None, vector_queries=[vector_query], top=TOP_K
        )
    elif strategy == "hybrid":
        # BM25 + vector, fused with RRF. One extra argument.
        results = client.search(
            search_text=query, vector_queries=[vector_query], top=TOP_K
        )
    elif strategy == "hybrid+rerank":
        # The L2 semantic reranker reorders the fused list. This is the one
        # that recovers exact-match questions.
        results = client.search(
            search_text=query,
            vector_queries=[vector_query],
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name=SEMANTIC_CONFIG_NAME,
            top=TOP_K,
        )
    else:
        raise ValueError(strategy)

    return [doc["chunk_id"] for doc in results]


def main() -> None:
    settings = Settings.load()
    client = search_client(settings)

    # Embed every query once, up front.
    oai = openai_client(settings)
    response = oai.embeddings.create(
        model=settings.embedding_deployment, input=[q for q, _ in CASES]
    )
    vectors = {q: item.embedding for (q, _), item in zip(CASES, response.data)}

    for strategy in ("vector-only", "hybrid", "hybrid+rerank"):
        hits = 0
        rr_total = 0.0
        print(f"\n=== {strategy} ===")
        for query, expected in CASES:
            ranked = run_strategy(client, strategy, query, vectors[query])
            rr = _reciprocal_rank(ranked, expected)
            rr_total += rr
            top1 = ranked[0] if ranked else "(none)"
            ok = "OK " if top1 in expected else "MISS"
            hits += top1 in expected
            print(f"  [{ok}] {query[:58]:58} -> {top1}")
        result = Result(strategy, hits, rr_total / len(CASES))
        print(f"  top-1 correct: {result.hits}/{len(CASES)}   MRR@{TOP_K}: {result.mrr:.2f}")

    print(
        "\nWatch the middle row, not just the last one. Hybrid retrieval widens "
        "the candidate pool but does not judge relevance - RRF fuses positions, "
        "not answers - so it can score below vector-only. The cross-encoder "
        "reranker is what converts the wider pool into better answers."
    )


if __name__ == "__main__":
    main()
