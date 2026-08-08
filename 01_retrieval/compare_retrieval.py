"""Gap 1 - prove the difference between vector-only and hybrid + reranked.

This is the sample worth running in front of a stakeholder. The queries below
are chosen to be the ones dense retrieval quietly fails: product codes, exact
figures, negation, and near-duplicate distractors.

Run:  python -m 01_retrieval.compare_retrieval
"""

from dataclasses import dataclass

from azure.search.documents.models import QueryType, VectorizableTextQuery

from common.clients import search_client
from common.config import Settings
from .create_index import SEMANTIC_CONFIG_NAME

# Each case names the chunk we expect at rank 1. Guessing is not evaluation.
CASES = [
    ("Welke korting hoort bij productcode BAS-VR-400?", "POL-BASIS-2026_1"),
    ("Is BAS-VR-350 nog geldig in 2026?", "POL-BASIS-2026_3"),
    ("Vanaf welke behandeling wordt fysiotherapie vergoed?", "POL-BASIS-2026_2"),
    ("Tandarts voor een kind van 12", "POL-AANV-2026_2"),
    ("Welk pakket heeft onbeperkte fysiotherapie?", "POL-AANV-2026_1"),
]

TOP_K = 5


@dataclass
class Result:
    strategy: str
    hits: int
    mrr: float


def _reciprocal_rank(doc_ids: list[str], expected: str) -> float:
    for position, doc_id in enumerate(doc_ids, start=1):
        if doc_id == expected:
            return 1.0 / position
    return 0.0


def run_strategy(client, strategy: str, query: str) -> list[str]:
    vector_query = VectorizableTextQuery(
        text=query, k_nearest_neighbors=50, fields="content_vector"
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

    for strategy in ("vector-only", "hybrid", "hybrid+rerank"):
        hits = 0
        rr_total = 0.0
        print(f"\n=== {strategy} ===")
        for query, expected in CASES:
            ranked = run_strategy(client, strategy, query)
            rr = _reciprocal_rank(ranked, expected)
            rr_total += rr
            top1 = ranked[0] if ranked else "(none)"
            ok = "OK " if top1 == expected else "MISS"
            hits += top1 == expected
            print(f"  [{ok}] {query[:52]:52} -> {top1}")
        result = Result(strategy, hits, rr_total / len(CASES))
        print(f"  top-1 correct: {result.hits}/{len(CASES)}   MRR@{TOP_K}: {result.mrr:.2f}")

    print(
        "\nIf vector-only wins here, your corpus has no exact-match vocabulary. "
        "Most enterprise corpora do."
    )


if __name__ == "__main__":
    main()
