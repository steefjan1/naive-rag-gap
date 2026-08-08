"""Client factories. Keyless by default - DefaultAzureCredential everywhere.

Run `az login` first. For the search service you need, at minimum:
  - Search Service Contributor  (to create indexes)
  - Search Index Data Contributor (to upload documents)
  - Search Index Data Reader (to query)
"""

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

from .config import Settings

_CREDENTIAL = DefaultAzureCredential()

SEARCH_SCOPE = "https://search.azure.com/.default"
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


def credential() -> DefaultAzureCredential:
    return _CREDENTIAL


def index_client(settings: Settings) -> SearchIndexClient:
    return SearchIndexClient(endpoint=settings.search_endpoint, credential=_CREDENTIAL)


def search_client(settings: Settings, index_name: str | None = None) -> SearchClient:
    return SearchClient(
        endpoint=settings.search_endpoint,
        index_name=index_name or settings.index_name,
        credential=_CREDENTIAL,
    )


def openai_client(settings: Settings) -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=settings.openai_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(_CREDENTIAL, COGNITIVE_SCOPE),
        api_version=settings.openai_api_version,
    )


def user_search_token() -> str:
    """Token representing the *calling user* for query-time permission filtering.

    In a real application this is the end user's token from your API gateway,
    not a token minted from the service identity. This helper exists so the
    sample runs end to end with a single signed-in developer.
    """
    return get_bearer_token_provider(_CREDENTIAL, SEARCH_SCOPE)()
