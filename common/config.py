"""Central configuration. Everything comes from the environment - no secrets in code."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# `azd up` writes .env at the repo root via its postprovision hook. Load it if
# present; real environment variables always win, so CI and container runs that
# inject values directly are unaffected.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing environment variable {name}. Copy .env.example to .env and fill it in."
        )
    return value


@dataclass(frozen=True)
class Settings:
    search_endpoint: str
    openai_endpoint: str
    embedding_deployment: str
    embedding_model: str
    chat_deployment: str
    openai_api_version: str
    index_name: str
    acl_index_name: str
    knowledge_base_name: str

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            search_endpoint=_required("AZURE_SEARCH_ENDPOINT"),
            openai_endpoint=_required("AZURE_OPENAI_ENDPOINT"),
            embedding_deployment=os.environ.get(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
            ),
            embedding_model=os.environ.get(
                "AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"
            ),
            chat_deployment=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini"),
            openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
            index_name=os.environ.get("AZURE_SEARCH_INDEX", "policies-demo"),
            acl_index_name=os.environ.get("AZURE_SEARCH_ACL_INDEX", "policies-acl-demo"),
            knowledge_base_name=os.environ.get("AZURE_SEARCH_KNOWLEDGE_BASE", "policies-kb"),
        )


SETTINGS = Settings.load
