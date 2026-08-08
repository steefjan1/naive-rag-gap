"""Gap 4 - "zero hallucination" is a claim, and claims get measured.

This runs the full pipeline over eval_set.jsonl and scores four things:

  groundedness   every factual statement is supported by a retrieved chunk
  citation_valid every cited ref_id exists in what was actually retrieved
  refusal        unanswerable questions produce a refusal, not a fluent guess
  retrieval_hit  the expected document appeared in the top-k

The fourth metric separates the two failure modes. A wrong answer with good
retrieval is a generation problem. A wrong answer with bad retrieval is a
retrieval problem. Without both numbers you will tune the wrong half of the
system for a week.

Run:  python -m 04_groundedness.evaluate
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from azure.search.documents.models import QueryType, VectorizableTextQuery

from common.clients import openai_client, search_client
from common.config import Settings

import importlib

SEMANTIC_CONFIG_NAME = importlib.import_module(
    "01_retrieval.create_index"
).SEMANTIC_CONFIG_NAME

EVAL_SET = Path(__file__).resolve().parent / "eval_set.jsonl"
REFUSAL = "Ik weet het niet"

# Three things make this prompt different from the diagram's "Prompt (Query+Context)":
#   1. an explicit refusal string, so refusal is detectable rather than inferred
#   2. mandatory ref_id citation, so every claim is checkable
#   3. an instruction to prefer the sources over prior knowledge, which is the
#      failure mode nobody tests for
ANSWER_PROMPT = """Je beantwoordt vragen over zorgverzekeringsvoorwaarden.

Regels:
- Gebruik uitsluitend de onderstaande bronnen. Negeer wat je zelf denkt te weten.
- Citeer na elke bewering de gebruikte bron als [ref_id].
- Staat het antwoord niet letterlijk in de bronnen, antwoord dan exact: {refusal}
- Klopt de aanname in de vraag niet volgens de bronnen, corrigeer die dan expliciet.

Bronnen:
{sources}

Vraag: {question}
"""

JUDGE_PROMPT = """You score a grounded answer. Return JSON only, no prose.

Sources (JSON array, each with ref_id and content):
{sources}

Question: {question}
Answer: {answer}

Score:
  "groundedness": 1 if every factual statement in the answer is directly
      supported by the sources, else 0. Statements that are plausible but not
      present score 0.
  "unsupported_claims": array of any statements not supported by the sources.

Return: {{"groundedness": 0 or 1, "unsupported_claims": []}}
"""


@dataclass
class Case:
    id: str
    question: str
    expected_doc: str | None
    answerable: bool


def load_cases() -> list[Case]:
    cases = []
    for line in EVAL_SET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            cases.append(
                Case(row["id"], row["question"], row["expected_doc"], row["answerable"])
            )
    return cases


def retrieve(settings, question: str, top: int = 5) -> list[dict]:
    client = search_client(settings)
    vector_query = VectorizableTextQuery(
        text=question, k_nearest_neighbors=50, fields="content_vector"
    )
    results = client.search(
        search_text=question,
        vector_queries=[vector_query],
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name=SEMANTIC_CONFIG_NAME,
        select=["chunk_id", "doc_id", "title", "content"],
        top=top,
    )
    return [
        {
            "ref_id": str(i),
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "content": doc["content"],
        }
        for i, doc in enumerate(results)
    ]


def answer(oai, settings, question: str, sources: list[dict]) -> str:
    prompt = ANSWER_PROMPT.format(
        refusal=REFUSAL,
        sources=json.dumps(sources, ensure_ascii=False),
        question=question,
    )
    response = oai.chat.completions.create(
        model=settings.chat_deployment,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def judge(oai, settings, question: str, sources: list[dict], text: str) -> dict:
    prompt = JUDGE_PROMPT.format(
        sources=json.dumps(sources, ensure_ascii=False),
        question=question,
        answer=text,
    )
    response = oai.chat.completions.create(
        model=settings.chat_deployment,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def cited_ids(text: str) -> set[str]:
    return set(re.findall(r"\[(\w+)\]", text))


def main() -> None:
    settings = Settings.load()
    oai = openai_client(settings)
    cases = load_cases()

    totals = {"groundedness": 0, "citation_valid": 0, "refusal": 0, "retrieval_hit": 0}
    refusal_cases = 0

    for case in cases:
        sources = retrieve(settings, case.question)
        text = answer(oai, settings, case.question, sources)
        refused = REFUSAL.lower() in text.lower()

        valid_ids = {s["ref_id"] for s in sources}
        citations = cited_ids(text)
        citation_valid = refused or (bool(citations) and citations <= valid_ids)

        retrieved_docs = {s["doc_id"] for s in sources}
        retrieval_hit = case.expected_doc is None or case.expected_doc in retrieved_docs

        verdict = judge(oai, settings, case.question, sources, text) if not refused else {
            "groundedness": 1,
            "unsupported_claims": [],
        }

        totals["groundedness"] += verdict["groundedness"]
        totals["citation_valid"] += citation_valid
        totals["retrieval_hit"] += retrieval_hit
        if not case.answerable:
            refusal_cases += 1
            totals["refusal"] += refused

        flag = "  " if verdict["groundedness"] and citation_valid else "!!"
        print(f"{flag} {case.id}  refused={refused!s:5}  {text.splitlines()[0][:70]}")
        for claim in verdict.get("unsupported_claims", []):
            print(f"      unsupported: {claim[:90]}")

    n = len(cases)
    print("\n--- scores ---")
    print(f"  groundedness    {totals['groundedness']}/{n}")
    print(f"  citation_valid  {totals['citation_valid']}/{n}")
    print(f"  retrieval_hit   {totals['retrieval_hit']}/{n}")
    print(f"  refusal         {totals['refusal']}/{refusal_cases} (unanswerable only)")
    print(
        "\nThe refusal number is the one to watch. A system that scores 10/10 on "
        "answerable questions and 0/4 on refusals is not grounded - it is fluent."
    )


if __name__ == "__main__":
    main()
