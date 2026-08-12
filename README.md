# naive-rag-gap

Four runnable samples for the four things a naive RAG diagram leaves out.

The familiar four-box picture — index, retrieve, augment, generate — is a fine
first explanation and a poor design. These samples show what breaks and what to
do instead, on Azure AI Search and Microsoft Foundry.

Companion to [*The Four Things Naive RAG Diagrams Leave Out*](https://sjwiggers.com/2026/08/12/naive-rag-diagrams-leave-out/)
on Cloud Perspectives.

## The gaps

| Gap | Sample | What it demonstrates |
| --- | ------ | -------------------- |
| 1. Retrieval is not vector search | `01_retrieval/` | Vector-only vs hybrid vs hybrid + semantic reranker over 11 questions. Measured 7/11, 6/11, 11/11 — hybrid alone scored *below* vector-only. |
| 2. Chunking is most of the work | `02_chunking/` | Three chunkers against the same document; counts chunks that lost their table header. Runs offline, no Azure needed. |
| 3. Retrieval without authorisation is a breach | `03_permissions/` | Group-based security trimming from validated claims, and a leak test that fails the build. |
| 4. "Zero hallucination" is a measurable claim | `04_groundedness/` | Citation-enforced prompting, a refusal path, and an eval set where 5 of 14 questions are unanswerable. |

## Measured results

From a single run against a freshly provisioned service, 11 questions over 33
chunks:

| Strategy | Top-1 correct | MRR@5 |
| --- | --- | --- |
| Vector-only | 7 / 11 | 0.77 |
| Hybrid (BM25 + vector, RRF) | 6 / 11 | 0.72 |
| Hybrid + semantic reranker | 11 / 11 | 1.00 |

Adding keyword search made it worse. BM25 matched product codes literally, and
those codes appear in *changes* sections that name a code without pricing it —
so lexical matching promoted chunks that cannot answer the question, and RRF
fused positions rather than relevance. The cross-encoder reranker is what
recovered it.

Groundedness evaluation on the same corpus: 14/14 grounded, 14/14 valid
citations, 14/14 retrieval hit, 5/5 refusals on the unanswerable questions.

Treat these as one observation, not a benchmark. Eleven questions is a small
sample, the hybrid regression rests on a single case, and the groundedness judge
was the same model as the generator — which inflates that score by an unknown
amount. Run it yourself; that is what it is for.

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

You are prompted for an environment name and a region. That provisions an Azure
AI Search service (Basic, semantic ranker enabled), a Microsoft Foundry account
with `text-embedding-3-large` and `gpt-5-mini` deployed, and the role
assignments — including the one people forget: the **search service's own
managed identity** needs `Cognitive Services User` on the Foundry resource, or
integrated vectorization and agentic retrieval fail at query time with an
authorization error that reads like a config bug.

A postprovision hook writes `.env` for you. Then jump to [Running](#running).

Tear it all down with `azd down --purge`. The `--purge` matters: Foundry
accounts soft-delete, and the name stays reserved until purged.

This costs money while it exists. Basic-tier search has no free option and bills
hourly regardless of use.

## Setup without azd

If you already have a search service and a Foundry resource:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill it in
az login
```

On Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
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

Run order matters: `compare_retrieval` and `evaluate` both read the index that
`index_documents` populates, and `security_trimming` reads the separate ACL
index built by `setup_acl_index`.

### Not covered by the run above

`01_retrieval/agentic_retrieve.py` **has not been run against a live service.**
It needs a knowledge base, which none of the scripts create — set one up in the
portal or via REST first. The request shape follows the current documented API,
but unlike the other four samples it is unverified, so treat it as a sketch
rather than a working example.

Extractive agentic retrieval is GA in api-version `2026-04-01` and works on the
stable SDK. Query planning, answer synthesis, and configurable reasoning effort
are preview-only in `2026-05-01-preview` and need `pip install --pre
azure-search-documents`.

## The sample corpus

Eight short synthetic Dutch policy documents in `data/policies/`, deliberately
awkward in the ways real corpora are awkward.

The awkwardness is the design. Three documents carry structurally identical
"Eigen risico" tables with different code families and different prices. Two
years of the same policy sit side by side with near-identical prose and opposite
answers. Four sections discuss fysiotherapie, one of which says it is *not*
covered. A withdrawn product code appears by name with no price attached. And
one document nobody outside a single role may see.

A corpus with nothing to confuse cannot demonstrate confusion, which is why the
first version of this repo — three documents, eight chunks — understated the
retrieval gap. Vector-only scored 4/5 on that one.

No real policy data. No real people. Nothing here is a product of any insurer.

## Troubleshooting

**`Could not complete vectorization action ... 404`** — `AZURE_OPENAI_ENDPOINT`
is on the `cognitiveservices.azure.com` hostname. The OpenAI SDK accepts it, but
the search service's server-side vectorizer call does not, and the failure is
intermittent rather than immediate. Switch to the `openai.azure.com` form of the
same resource and re-run `create_index` so the stored vectorizer definition is
updated:

```
AZURE_OPENAI_ENDPOINT="https://<your-foundry-name>.openai.azure.com/"
```

The measurement samples embed queries client-side and no longer depend on this
path; the vectorizer stays on the index because agentic retrieval needs it.

**`The 'location' property must be specified`** during `azd up` — azd did not
capture the region. Set it explicitly and re-run:

```
azd env set AZURE_LOCATION swedencentral
```

**403 on the first run after `azd up`** — role assignments take a few minutes to
propagate. Wait, then retry before assuming misconfiguration.

**Windows on ARM** — `cryptography`, a transitive dependency of
`azure-identity`, has no prebuilt `win_arm64` wheel for Python 3.12 or 3.13, so
pip falls back to a Rust build that needs the MSVC linker. Use Python 3.11 or
3.14 on ARM64, or an x64 build.

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

Everything here is synthetic and built to illustrate an argument. It is not a
production reference architecture, and the security trimming sample in
particular is a demonstration of a mechanism rather than a complete
authorisation design.
