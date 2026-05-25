"""
Avaliação comparativa dos três pipelines RAG.

Implementa as 4 métricas-chave do RAGAS manualmente via LLM (gpt-4o-mini),
contornando incompatibilidade da biblioteca ragas com Python 3.14.

Métricas:
  faithfulness      — % de afirmações da resposta suportadas pelo contexto
  answer_relevancy  — similaridade coseno entre pergunta e resposta (embeddings)
  context_recall    — % do gabarito coberto pelo contexto
  context_precision — % do contexto que é de fato necessário para a resposta

Uso:
    bun run src/evaluation/run_eval.ts   # gera respostas_brutas.json
    python src/evaluation/ragas_eval.py  # calcula métricas
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parents[2] / ".env")

RESULTS_DIR = Path(__file__).parents[2] / "data" / "evaluation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
EVAL_MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"


# ─────────────────────────────────────────────
# Helpers LLM
# ─────────────────────────────────────────────

def _chat(system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=EVAL_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=2000,
    )
    return resp.choices[0].message.content.strip()


def _embed(text: str) -> list[float]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=text[:8000])
    return resp.data[0].embedding


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb else 0.0


def _score_01(text: str) -> float:
    """Extrai float 0-1 do texto do LLM, com fallback."""
    clean = text.replace(",", ".").strip()
    for token in clean.split():
        try:
            v = float(token)
            if 0.0 <= v <= 1.0:
                return v
            if 0.0 <= v <= 100.0:
                return v / 100.0
        except ValueError:
            pass
    return math.nan


# ─────────────────────────────────────────────
# Métricas
# ─────────────────────────────────────────────

SYS_FAITHFULNESS = (
    "Você avalia se uma resposta é fiel ao contexto fornecido. "
    "Responda APENAS com um número de 0 a 1, onde 1 = todas as afirmações "
    "estão suportadas pelo contexto e 0 = resposta inventada sem base no contexto."
)

SYS_RECALL = (
    "Você avalia se o contexto contém as informações necessárias para responder "
    "conforme o gabarito. Responda APENAS com um número de 0 a 1, onde 1 = o "
    "contexto cobre completamente o gabarito e 0 = o contexto não contém nada relevante."
)

SYS_PRECISION = (
    "Você avalia se o contexto recuperado é preciso e relevante para a pergunta. "
    "Responda APENAS com um número de 0 a 1, onde 1 = todo o contexto é essencial "
    "para a resposta e 0 = o contexto é irrelevante ou ruidoso."
)


_INDISPONIVEL = "[VectorRAG indisponível"

def _contexto_valido(ctx: str) -> bool:
    """Retorna True se o contexto tem conteúdo real (não vazio e não mensagem de erro)."""
    s = ctx.strip()
    return bool(s) and not s.startswith(_INDISPONIVEL)


_CTX_LIMIT = 6000   # chars enviados ao juiz LLM por chamada


def faithfulness(resposta: str, contexto: str) -> float:
    if not _contexto_valido(contexto):
        return math.nan
    prompt = f"Contexto:\n{contexto[:_CTX_LIMIT]}\n\nResposta:\n{resposta[:1000]}"
    raw = _chat(SYS_FAITHFULNESS, prompt)
    return _score_01(raw)


def answer_relevancy(pergunta: str, resposta: str) -> float:
    if not resposta.strip():
        return 0.0
    return round(_cosine(_embed(pergunta), _embed(resposta)), 4)


def context_recall(contexto: str, gabarito: str) -> float:
    if not _contexto_valido(contexto):
        return math.nan
    prompt = f"Gabarito:\n{gabarito[:1000]}\n\nContexto:\n{contexto[:_CTX_LIMIT]}"
    raw = _chat(SYS_RECALL, prompt)
    return _score_01(raw)


def context_precision(pergunta: str, contexto: str) -> float:
    if not _contexto_valido(contexto):
        return math.nan
    prompt = f"Pergunta:\n{pergunta}\n\nContexto:\n{contexto[:_CTX_LIMIT]}"
    raw = _chat(SYS_PRECISION, prompt)
    return _score_01(raw)


# ─────────────────────────────────────────────
# Avaliação por modo
# ─────────────────────────────────────────────

def avaliar_amostra(
    pergunta: str,
    resposta: str,
    contexto: str,
    gabarito: str,
    modo: str,
) -> dict[str, float]:
    faith = faithfulness(resposta, contexto)
    ar    = answer_relevancy(pergunta, resposta)

    if modo == "no_rag":
        cr = math.nan
        cp = math.nan
    else:
        cr = context_recall(contexto, gabarito)
        cp = context_precision(pergunta, contexto)

    return {
        "faithfulness":      round(faith, 4) if not math.isnan(faith) else math.nan,
        "answer_relevancy":  round(ar,    4),
        "context_recall":    round(cr,    4) if not math.isnan(cr) else math.nan,
        "context_precision": round(cp,    4) if not math.isnan(cp) else math.nan,
    }


def media(valores: list[float]) -> float:
    validos = [v for v in valores if not math.isnan(v)]
    return round(sum(validos) / len(validos), 4) if validos else math.nan


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main() -> None:
    cache = RESULTS_DIR / "respostas_brutas.json"
    if not cache.exists():
        print("Arquivo respostas_brutas.json não encontrado.")
        print("Execute: bun run src/evaluation/run_eval.ts")
        sys.exit(1)

    resultados: list[dict[str, Any]] = json.loads(cache.read_text(encoding="utf-8"))
    print(f"Avaliando {len(resultados)} perguntas × 3 modos ({EVAL_MODEL})...\n")

    acumulado: dict[str, dict[str, list[float]]] = {
        "no_rag":     {"faithfulness": [], "answer_relevancy": [], "context_recall": [], "context_precision": []},
        "vector_rag": {"faithfulness": [], "answer_relevancy": [], "context_recall": [], "context_precision": []},
        "graph_rag":  {"faithfulness": [], "answer_relevancy": [], "context_recall": [], "context_precision": []},
    }

    scores_por_pergunta: list[dict[str, Any]] = []

    for i, r in enumerate(resultados, 1):
        q  = r["pergunta"]
        gt = r["gabarito"]
        print(f"[{i}/{len(resultados)}] {q[:65]}...")

        pares = {
            "no_rag":     (r["resposta_norag"],    ""),
            "vector_rag": (r["resposta_vectorrag"], r.get("contexto_vectorrag", "")),
            "graph_rag":  (r["resposta_graphrag"],  r["contexto_graphrag"]),
        }

        entrada: dict[str, Any] = {"pergunta": q, "gabarito": gt}
        for modo, (resp, ctx) in pares.items():
            scores = avaliar_amostra(q, resp, ctx, gt, modo)
            for metrica, val in scores.items():
                acumulado[modo][metrica].append(val)
            entrada[modo] = scores
            print(f"  {modo:12} | faith={scores['faithfulness']!s:6} "
                  f"ar={scores['answer_relevancy']!s:6} "
                  f"cr={scores['context_recall']!s:6} "
                  f"cp={scores['context_precision']!s:6}")
        scores_por_pergunta.append(entrada)

    # Agrega médias
    scores_finais: dict[str, dict[str, Any]] = {}
    for modo, metricas in acumulado.items():
        scores_finais[modo] = {m: media(vals) for m, vals in metricas.items()}

    def _serial(obj: Any) -> Any:
        return None if (isinstance(obj, float) and math.isnan(obj)) else obj

    out = RESULTS_DIR / "ragas_scores.json"
    out.write_text(
        json.dumps(scores_finais, ensure_ascii=False, indent=2, default=_serial),
        encoding="utf-8",
    )

    out_pq = RESULTS_DIR / "ragas_scores_por_pergunta.json"
    out_pq.write_text(
        json.dumps(scores_por_pergunta, ensure_ascii=False, indent=2, default=_serial),
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print("RESULTADOS FINAIS (médias)")
    print("=" * 72)
    print(f"{'Metrica':<22} {'No RAG':>10} {'Vector RAG':>12} {'Graph RAG':>11}")
    print("-" * 72)
    for m in ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]:
        row = f"{m:<22}"
        for modo in ["no_rag", "vector_rag", "graph_rag"]:
            v = scores_finais[modo].get(m, math.nan)
            row += f" {'N/A':>10}" if (isinstance(v, float) and math.isnan(v)) else f" {v:>10.4f}"
        print(row)

    print(f"\nResultados salvos em: {out}")


if __name__ == "__main__":
    main()
