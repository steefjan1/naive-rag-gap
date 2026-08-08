# naive-rag-gap

Four runnable samples for the four things a naive RAG diagram leaves out.

The familiar four-box picture — index, retrieve, augment, generate — is a fine
first explanation and a poor design. These samples show what breaks and what to
do instead, on Azure AI Search and Microsoft Foundry.

Companion to the post *The four things naive RAG diagrams leave out* on
[sjwiggers.com](https://sjwiggers.com).

## The gaps

| Gap | Sample | What it demonstrates |
| --- | ------ | -------------------- |
| 1. Retrieval is not vector search | `01_retrieval/` | Vector-only vs hybrid vs hybrid + semantic reranker, scored. Plus agentic retrieval for compound questions. |
| 2. Chunking is most of the work | `02_chunking/` | Three chunkers against the same document; counts how many chunks lost their table header. Runs offline. |
| 3. Retrieval without authorisation is a breach | `03_permissions/` | Group-based security trimming with an OData filter, and a leak test that fails the build. |
| 4. "Zero hallucination" is a measurable claim | `04_groundedness/` | Citation-enforced prompting, a refusal path, and an eval set that includes unanswerable questions. |

## Diagrams

One per gap, in `docs/diagrams/`. Plain SVG, no external fonts or assets, sized
1000px wide for a blog column. Each contrasts the naive pipeline with what the
gap actually requires.

| Gap | File |
| --- | ---- |
| 1 | `docs/diagrams/gap-1-retrieval.svg` |
| 2 | `docs/diagrams/gap-2-chunking.svg` |
| 3 | `docs/diagrams/gap-3-permissions.svg` |
| 4 | `docs/diagrams/gap-4-groundedness.svg` |

## Provisioning with azd

One command creates everything the samples need, keyless:

```bash
azd auth login
azd up
```

You are prompted for an environment name and a region. If a run ever fails validation with *The 'location' property must be specified*, azd did not capture the region — set it explicitly with `azd env set AZURE_LOCATION swedencentral` and re-run. That provisions an Azure
AI Search service (Basic, semantic ranker enabled), a Microsoft Foundry account
with `text-embedding-3-large` and `gpt-5-mini` deployed, and the role
assignments — including the one people forget: the **search service's own
managed identity** needs `Cognitive Services User` on the Foundry resource, or
integrated vectorization and agentic retrieval fail at query time with an
authorization error that reads like a config bug.

A postprovision hook writes `.env` for you. Then:

```bash
python -m 01_retrieval.create_index
python -m 01_retrieval.index_documents
python -m 01_retrieval.compare_retrieval
```

Tear it all down with `azd down --purge`. The `--purge` matters: Foundry
accounts soft-delete, and the name stays reserved until purged.

Costs money while it exists. Basic-tier search has no free option and bills
hourly regardless of use.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill it in
az login
```

Keyless throughout. On the search service the signed-in identity needs
**Search Service Contributor** (create indexes), **Search Index Data
Contributor** (upload), and **Search Index Data Reader** (query). On the Foundry
resource it needs **Cognitive Services OpenAI User**.

## Running

```bash
python -m 02_chunking.chunk_strategies        # no Azure needed, start here

python -m 01_retrieval.create_index           # gap 1
python -m 01_retrieval.index_documents
python -m 01_retrieval.compare_retrieval

python -m 03_permissions.setup_acl_index      # gap 3 - separate index, includes
python -m 03_permissions.security_trimming    #   the restricted document

python -m 04_groundedness.evaluate            # gap 4 - uses the gap 1 index
```

`01_retrieval/agentic_retrieve.py` additionally needs a knowledge base, which
none of the scripts create — set one up in the portal or via REST first.
Extractive agentic retrieval is GA in api-version `2026-04-01` and works on the
stable SDK; query planning, answer synthesis, and configurable reasoning effort
are preview-only in `2026-05-01-preview` and need `pip install --pre
azure-search-documents`.

## The sample corpus

Three short synthetic Dutch policy documents in `data/policies/`. They are
deliberately awkward in the ways real corpora are awkward: product codes that
only exact match will find, a table whose meaning dies if you split it, a code
that was withdrawn but still appears in the text, and one document nobody
outside a single role may see.

No real policy data. No real people. Nothing here is a product of any insurer.

## Where this is the wrong answer

If your corpus is a few dozen pages of prose with no codes, no tables, one
audience, and low stakes, the four-box diagram is enough and this repo is
overhead. Build the simple thing. Come back when the first exact-match question
returns the wrong table row.

## Caveats

The samples target Azure AI Search API versions current as of August 2026.
Agentic retrieval and document-level permissions are moving quickly; check
[what's new](https://learn.microsoft.com/en-us/azure/search/whats-new) before
assuming a preview flag is still a preview flag.
