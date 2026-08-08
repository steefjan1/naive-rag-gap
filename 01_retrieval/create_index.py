"""Gap 1 - build an index that can actually do hybrid retrieval.

The four-box diagram gives you a vector store. This gives you:
  - a searchable text field with a Dutch analyzer (BM25 half of hybrid)
  - a vector field with an integrated vectorizer (dense half)
  - a semantic configuration (the L2 reranker)
  - filterable metadata (so gap 3 has something to filter on)

Run:  python -m 01_retrieval.create_index
"""

from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from common.clients import index_client
from common.config import Settings

SEMANTIC_CONFIG_NAME = "policies-semantic"
VECTOR_PROFILE_NAME = "policies-hnsw-profile"


def build_index(settings: Settings, index_name: str) -> SearchIndex:
    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        # analyzer_name matters more than people expect: "nl.microsoft" stems Dutch
        # correctly, which is half the reason BM25 beats dense retrieval on
        # domain vocabulary like "eigen risico" or "coulancebeoordeling".
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            analyzer_name="nl.microsoft",
        ),
        SearchableField(name="section", type=SearchFieldDataType.String, filterable=True),
        SimpleField(
            name="classification", type=SearchFieldDataType.String, filterable=True
        ),
        SimpleField(
            name="effective_from",
            type=SearchFieldDataType.DateTimeOffset,
            filterable=True,
            sortable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,  # text-embedding-3-large
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="policies-hnsw")],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE_NAME,
                algorithm_configuration_name="policies-hnsw",
                vectorizer_name="policies-vectorizer",
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="policies-vectorizer",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=settings.openai_endpoint,
                    deployment_name=settings.embedding_deployment,
                    model_name=settings.embedding_model,
                ),
            )
        ],
    )

    # Without this block there is no reranker, and "hybrid search" is just
    # RRF over two mediocre result lists.
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG_NAME,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="section")],
                ),
            )
        ]
    )

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def main() -> None:
    settings = Settings.load()
    client = index_client(settings)
    index = build_index(settings, settings.index_name)
    client.create_or_update_index(index)
    print(f"Index '{settings.index_name}' created or updated.")


if __name__ == "__main__":
    main()
