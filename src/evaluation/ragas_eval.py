"""
Avaliação comparativa dos três pipelines RAG com o framework RAGAS.

Modos avaliados:
  - no_rag:     LLM sem contexto externo (baseline sem recuperação)
  - vector_rag: RAG vetorial via Neo4j Vector Index
  - graph_rag:  GraphRAG via grafo de conhecimento Neo4j

Métricas RAGAS utilizadas:
  Reference-free (todos os modos):
    - faithfulness:      fidelidade da resposta ao contexto recuperado
    - answer_relevancy:  relevância da resposta à pergunta formulada
    - context_relevance: proporção do contexto que é necessário para a resposta

  Reference-based (só modos com recuperação):
    - context_recall:    quanto do gabarito é coberto pelo contexto
    - context_precision: precisão do ranqueamento dos chunks recuperados

  Para No-RAG: context_recall e context_precision são marcados como N/A (NaN).
  RAGAS v0.2+: avaliação por LLM (gpt-4o-mini) — resultados dependem do modelo.

Referência:
  Es et al. (EACL 2024) — https://aclanthology.org/2024.eacl-demo.16
  Ahmad et al. (2025, arXiv:2507.03608) — benchmark GraphRAG vs Vector RAG com RAGAS

Pré-requisitos:
    pip install "ragas>=0.2.0" openai langchain-openai datasets python-dotenv requests

Uso:
    python src/evaluation/ragas_eval.py

    O servidor TypeScript (bun run src/app/index.ts) deve estar rodando
    em http://localhost:3000 antes de executar este script.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# Importações RAGAS
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
        ContextRelevance,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
except ImportError as e:
    print(f"Dependência não encontrada: {e}")
    print('Execute: pip install "ragas>=0.2.0" openai langchain-openai datasets python-dotenv')
    sys.exit(1)

load_dotenv(Path(__file__).parents[2] / ".env")

API_URL = os.getenv("API_URL", "http://localhost:3000")
RESULTS_DIR = Path(__file__).parents[2] / "data" / "evaluation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# Perguntas e gabaritos de avaliação
# ─────────────────────────────────────────────
PERGUNTAS: list[dict[str, str]] = [
    {
        "pergunta": "Quais municípios do Rio Grande do Sul tiveram mais enchentes entre 2020 e 2024?",
        "gabarito": "Municípios gaúchos com maior frequência de eventos de enchente no período incluem "
                    "cidades da Região Metropolitana e do Vale do Taquari, como Porto Alegre, Lajeado, "
                    "Canoas e municípios do litoral norte.",
    },
    {
        "pergunta": "Houve eventos de calor extremo em Mato Grosso em 2023?",
        "gabarito": "Sim. Municípios do Mato Grosso registraram temperaturas máximas acima de 40°C em 2023, "
                    "com destaque para o período de setembro a novembro, quando a combinação de seca e calor "
                    "foi mais intensa.",
    },
    {
        "pergunta": "Quais estados brasileiros registraram mais deslizamentos nos últimos 5 anos?",
        "gabarito": "São Paulo, Rio de Janeiro e Santa Catarina concentram os maiores registros de "
                    "deslizamentos no Brasil, com ocorrências frequentes nas encostas serranas durante "
                    "o período chuvoso.",
    },
    {
        "pergunta": "Em quais meses o fenômeno de geada é mais frequente no Sul do Brasil?",
        "gabarito": "As geadas são mais frequentes entre junho e agosto, especialmente em municípios "
                    "serranos do Rio Grande do Sul, Santa Catarina e Paraná, durante o inverno austral.",
    },
    {
        "pergunta": "Qual foi a precipitação mais extrema registrada em São Paulo nos últimos 10 anos?",
        "gabarito": "São Paulo registrou episódios com precipitação diária superior a 100 mm, "
                    "com eventos extremos no verão (janeiro-março) causando alagamentos na capital "
                    "e municípios da Grande SP.",
    },
]


# ─────────────────────────────────────────────
# Coleta de respostas dos três modos
# ─────────────────────────────────────────────

def coletar_respostas() -> list[dict[str, Any]]:
    """Chama o endpoint /avaliar da API TypeScript e retorna os resultados."""
    print("Coletando respostas da API...")
    try:
        resp = requests.post(f"{API_URL}/avaliar", timeout=300)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        print(f"Erro: API não está rodando em {API_URL}")
        print("Execute 'bun run src/app/index.ts' em outro terminal.")
        sys.exit(1)


def construir_datasets(
    resultados: list[dict[str, Any]],
) -> dict[str, Dataset]:
    """
    Transforma os resultados da API nos datasets RAGAS para cada modo.
    Retorna um dict {modo: Dataset}.
    """
    modos = {
        "no_rag": {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        },
        "vector_rag": {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        },
        "graph_rag": {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        },
    }

    for r in resultados:
        q = r["pergunta"]
        gt = r["gabarito"]
        ctx_graph = [r["contexto_graphrag"]] if r.get("contexto_graphrag") else [""]
        ctx_vector = [r.get("contexto_vectorrag", "")] if r.get("contexto_vectorrag") else [""]

        modos["no_rag"]["question"].append(q)
        modos["no_rag"]["answer"].append(r["resposta_norag"])
        modos["no_rag"]["contexts"].append([""])  # sem contexto
        modos["no_rag"]["ground_truth"].append(gt)

        modos["vector_rag"]["question"].append(q)
        modos["vector_rag"]["answer"].append(r["resposta_vectorrag"])
        modos["vector_rag"]["contexts"].append(ctx_vector)
        modos["vector_rag"]["ground_truth"].append(gt)

        modos["graph_rag"]["question"].append(q)
        modos["graph_rag"]["answer"].append(r["resposta_graphrag"])
        modos["graph_rag"]["contexts"].append(ctx_graph)
        modos["graph_rag"]["ground_truth"].append(gt)

    return {modo: Dataset.from_dict(dados) for modo, dados in modos.items()}


# ─────────────────────────────────────────────
# Avaliação RAGAS
# ─────────────────────────────────────────────

def avaliar_dataset(
    dataset: Dataset, nome: str, llm: Any, emb: Any, com_recuperacao: bool = True
) -> dict[str, float]:
    """Roda métricas RAGAS no dataset e retorna scores médios."""
    import math
    print(f"\nAvaliando modo: {nome}")

    # Métricas reference-free (todos os modos)
    metricas: list[Any] = [
        Faithfulness(llm=llm),
        AnswerRelevancy(llm=llm, embeddings=emb),
        ContextRelevance(llm=llm),
    ]

    # Métricas reference-based (só modos com contexto real)
    if com_recuperacao:
        metricas += [
            ContextRecall(llm=llm),
            ContextPrecision(llm=llm),
        ]

    resultado = evaluate(dataset=dataset, metrics=metricas)

    scores: dict[str, float] = {
        "faithfulness": round(float(resultado.get("faithfulness", math.nan)), 4),
        "answer_relevancy": round(float(resultado.get("answer_relevancy", math.nan)), 4),
        "context_relevance": round(float(resultado.get("context_relevance", math.nan)), 4),
    }
    if com_recuperacao:
        scores["context_recall"] = round(float(resultado.get("context_recall", math.nan)), 4)
        scores["context_precision"] = round(float(resultado.get("context_precision", math.nan)), 4)
    else:
        scores["context_recall"] = float("nan")
        scores["context_precision"] = float("nan")

    print(f"  {scores}")
    return scores


def main() -> None:
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("Erro: OPENAI_API_KEY não definida no .env")
        sys.exit(1)

    llm_wrapper = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", api_key=openai_key))
    emb_wrapper = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_key)
    )

    resultados = coletar_respostas()

    # Salva respostas brutas para análise qualitativa
    raw_path = RESULTS_DIR / "respostas_brutas.json"
    raw_path.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Respostas brutas salvas em {raw_path}")

    datasets = construir_datasets(resultados)

    scores_finais: dict[str, dict[str, float]] = {}
    for nome, ds in datasets.items():
        com_recuperacao = nome != "no_rag"
        scores_finais[nome] = avaliar_dataset(ds, nome, llm_wrapper, emb_wrapper, com_recuperacao)

    # Salva resultado final
    result_path = RESULTS_DIR / "ragas_scores.json"
    result_path.write_text(json.dumps(scores_finais, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("RESULTADOS FINAIS")
    print("=" * 72)
    header = f"{'Métrica':<24} {'No RAG':>10} {'Vector RAG':>12} {'Graph RAG':>11}"
    print(header)
    print("-" * 72)
    metricas_ordem = [
        "faithfulness",
        "answer_relevancy",
        "context_relevance",
        "context_recall",
        "context_precision",
    ]
    for metrica in metricas_ordem:
        row = f"{metrica:<24}"
        for modo in ["no_rag", "vector_rag", "graph_rag"]:
            v = scores_finais[modo].get(metrica, float("nan"))
            if v != v:  # nan
                row += f" {'N/A':>10}"
            else:
                row += f" {v:>10.4f}"
        print(row)
    print(f"\nResultados salvos em {result_path}")


if __name__ == "__main__":
    main()
