"""
Avaliação comparativa dos três pipelines RAG (No RAG, VectorRAG, GraphRAG).

Mudanças em relação à primeira versão
─────────────────────────────────────
1. Juiz por decomposição em afirmações, não score holístico.
   Pedir "dê uma nota de 0 a 1" a um LLM produz notas mal calibradas e pouco
   reprodutíveis. Aqui a resposta é quebrada em afirmações atômicas e cada uma é
   verificada individualmente (estilo NLI), como faz o RAGAS/RAGChecker. Scoring
   por afirmação correlaciona melhor com julgamento humano do que nota holística.

2. Saída do juiz em JSON estruturado, não texto livre.
   Elimina o parsing frágil por regex e a variância de formato.

3. Métrica determinística sem LLM: `cobertura_fatos`.
   Cada item do benchmark carrega `fatos_chave` (números e entidades que uma
   resposta correta precisa conter). A cobertura é medida por casamento de string
   normalizado — não passa por juiz nenhum, então serve de âncora contra
   eventuais vieses do LLM avaliador.

4. Intervalos de confiança por bootstrap.
   Com 70 perguntas, diferenças pequenas entre modos podem ser ruído. Cada média
   vem com IC 95%, e as comparações GraphRAG vs VectorRAG saem com p-valor de
   teste de permutação pareado.

5. Recorte por categoria de pergunta.
   A média global esconde o essencial: onde cada arquitetura ganha ou perde.

Métricas
────────
    faithfulness       — % das afirmações da resposta suportadas pelo contexto
    answer_relevancy   — similaridade coseno entre pergunta e resposta
    answer_correctness — % das afirmações do gabarito presentes na resposta
    context_recall     — % das afirmações do gabarito cobertas pelo contexto
    context_precision  — % do contexto recuperado que é relevante à pergunta
    cobertura_fatos    — % dos fatos_chave presentes na resposta (determinística)
    abstencao_correta  — só para C7: a resposta declarou ausência de dados?

Uso:
    bun run src/evaluation/run_eval.ts        # gera respostas_brutas.json
    .venv/Scripts/python.exe src/evaluation/ragas_eval.py
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import sys
import threading
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
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

CTX_LIMIT = 8000      # chars de contexto enviados ao juiz
RESP_LIMIT = 2500     # chars de resposta
WORKERS = 6           # chamadas simultâneas ao juiz
BOOTSTRAP_N = 10000
SEED = 42

MODOS = ["no_rag", "vector_rag", "graph_rag"]
METRICAS = [
    "faithfulness", "answer_relevancy", "answer_correctness",
    "context_recall", "context_precision", "cobertura_fatos",
]

_INDISPONIVEL = "[VectorRAG indisponível"
_lock = threading.Lock()


# ─────────────────────────────────────────────
# Infra LLM
# ─────────────────────────────────────────────

def _chat_json(system: str, user: str, tentativas: int = 3) -> dict[str, Any]:
    """Chamada ao juiz com resposta em JSON. Retorna {} se falhar de vez."""
    for i in range(tentativas):
        try:
            resp = client.chat.completions.create(
                model=EVAL_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content or "{}")
        except Exception as exc:
            if i == tentativas - 1:
                with _lock:
                    print(f"    juiz falhou: {exc}", file=sys.stderr)
                return {}
    return {}


def _embed(text: str) -> list[float]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=text[:8000] or " ")
    return resp.data[0].embedding


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb else 0.0


def _contexto_valido(ctx: str) -> bool:
    s = (ctx or "").strip()
    return bool(s) and not s.startswith(_INDISPONIVEL)


def _fracao(itens: list[Any], chave: str) -> float:
    """Fração de itens cujo campo booleano `chave` é verdadeiro."""
    validos = [i for i in itens if isinstance(i, dict) and chave in i]
    if not validos:
        return math.nan
    return sum(1 for i in validos if bool(i[chave])) / len(validos)


# ─────────────────────────────────────────────
# Métricas por decomposição em afirmações
# ─────────────────────────────────────────────

SYS_FAITHFULNESS = """Você verifica fidelidade factual.
Quebre a RESPOSTA em afirmações atômicas (cada uma um único fato verificável).
Para cada afirmação, decida se ela é sustentada pelo CONTEXTO.
Afirmação sustentada = o contexto afirma o mesmo, ou permite deduzi-la diretamente.
Conhecimento geral do mundo NÃO conta como suporte — só o contexto conta.
Ignore frases sem conteúdo factual (saudações, ressalvas, ofertas de ajuda).

Responda em JSON: {"afirmacoes": [{"texto": "...", "sustentada": true|false}]}"""

SYS_CORRECTNESS = """Você verifica se uma RESPOSTA cobre o que diz o GABARITO.
Quebre o GABARITO em afirmações atômicas.
Para cada afirmação do gabarito, decida se a RESPOSTA a contém (mesmo com outras
palavras). Números precisam bater; um número diferente conta como não presente.

Responda em JSON: {"afirmacoes": [{"texto": "...", "presente": true|false}]}"""

SYS_RECALL = """Você verifica cobertura de contexto.
Quebre o GABARITO em afirmações atômicas.
Para cada uma, decida se o CONTEXTO recuperado contém a informação necessária
para sustentá-la (ainda que exija somar ou contar linhas do contexto).

Responda em JSON: {"afirmacoes": [{"texto": "...", "coberta": true|false}]}"""

SYS_PRECISION = """Você avalia precisão de recuperação.
Divida o CONTEXTO em blocos (uma seção ou linha por bloco, no máximo 30 blocos).
Para cada bloco, decida se ele é relevante para responder à PERGUNTA.
Bloco relevante = contribui com informação usada na resposta ideal.
Ruído, repetição e registros fora do escopo da pergunta são irrelevantes.

Responda em JSON: {"blocos": [{"resumo": "...", "relevante": true|false}]}"""

SYS_ABSTENCAO = """A PERGUNTA não tem resposta na base de dados: a resposta correta
é declarar que não há registros, sem inventar números.
Decida se a RESPOSTA fez isso corretamente.
- abstencao=true  : declara ausência de dados / diz que não há registros / responde zero
- abstencao=false : apresenta contagens, estimativas ou fatos como se existissem

Responda em JSON: {"abstencao": true|false, "justificativa": "..."}"""


def faithfulness(resposta: str, contexto: str) -> float:
    if not _contexto_valido(contexto) or not resposta.strip():
        return math.nan
    out = _chat_json(
        SYS_FAITHFULNESS,
        f"CONTEXTO:\n{contexto[:CTX_LIMIT]}\n\nRESPOSTA:\n{resposta[:RESP_LIMIT]}",
    )
    return _fracao(out.get("afirmacoes", []), "sustentada")


def answer_correctness(resposta: str, gabarito: str) -> float:
    if not resposta.strip():
        return 0.0
    out = _chat_json(
        SYS_CORRECTNESS,
        f"GABARITO:\n{gabarito[:RESP_LIMIT]}\n\nRESPOSTA:\n{resposta[:RESP_LIMIT]}",
    )
    return _fracao(out.get("afirmacoes", []), "presente")


def context_recall(contexto: str, gabarito: str) -> float:
    if not _contexto_valido(contexto):
        return math.nan
    out = _chat_json(
        SYS_RECALL,
        f"GABARITO:\n{gabarito[:RESP_LIMIT]}\n\nCONTEXTO:\n{contexto[:CTX_LIMIT]}",
    )
    return _fracao(out.get("afirmacoes", []), "coberta")


def context_precision(pergunta: str, contexto: str) -> float:
    if not _contexto_valido(contexto):
        return math.nan
    out = _chat_json(
        SYS_PRECISION,
        f"PERGUNTA:\n{pergunta}\n\nCONTEXTO:\n{contexto[:CTX_LIMIT]}",
    )
    return _fracao(out.get("blocos", []), "relevante")


def abstencao_correta(pergunta: str, resposta: str) -> float:
    out = _chat_json(
        SYS_ABSTENCAO,
        f"PERGUNTA:\n{pergunta}\n\nRESPOSTA:\n{resposta[:RESP_LIMIT]}",
    )
    if "abstencao" not in out:
        return math.nan
    return 1.0 if out["abstencao"] else 0.0


def answer_relevancy(pergunta: str, resposta: str) -> float:
    if not resposta.strip():
        return 0.0
    try:
        return round(_cosine(_embed(pergunta), _embed(resposta)), 4)
    except Exception:
        return math.nan


# ─────────────────────────────────────────────
# Métrica determinística
# ─────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t)


def cobertura_fatos(resposta: str, fatos: list[str]) -> float:
    """Fração dos fatos_chave presentes na resposta. Sem LLM.

    Números são casados como token isolado para que "15" não case dentro de
    "2015"; textos são casados como substring normalizada.
    """
    if not fatos:
        return math.nan
    alvo = _normalizar(resposta)
    achados = 0
    for fato in fatos:
        f = _normalizar(str(fato))
        if re.fullmatch(r"-?\d+(\.\d+)?", f):
            if re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d.,])", alvo):
                achados += 1
        elif f and f in alvo:
            achados += 1
    return achados / len(fatos)


# ─────────────────────────────────────────────
# Estatística
# ─────────────────────────────────────────────

def _validos(vals: list[float]) -> list[float]:
    return [v for v in vals if isinstance(v, (int, float)) and not math.isnan(v)]


def media(vals: list[float]) -> float:
    v = _validos(vals)
    return sum(v) / len(v) if v else math.nan


def bootstrap_ic(vals: list[float], n: int = BOOTSTRAP_N, alfa: float = 0.05) -> tuple[float, float]:
    """IC percentil para a média. Com 70 pontos, a média sozinha engana."""
    v = _validos(vals)
    if len(v) < 2:
        return (math.nan, math.nan)
    rng = random.Random(SEED)
    medias = []
    k = len(v)
    for _ in range(n):
        amostra = [v[rng.randrange(k)] for _ in range(k)]
        medias.append(sum(amostra) / k)
    medias.sort()
    return (medias[int(n * alfa / 2)], medias[int(n * (1 - alfa / 2))])


def teste_permutacao(a: list[float], b: list[float], n: int = BOOTSTRAP_N) -> float:
    """p-valor bicaudal para diferença de médias em amostras PAREADAS.

    Pareado porque os dois modos respondem às MESMAS perguntas: a variação entre
    perguntas é muito maior que entre modos, e ignorar o pareamento mascara o efeito.
    """
    pares = [(x, y) for x, y in zip(a, b)
             if not (math.isnan(x) or math.isnan(y))]
    if len(pares) < 2:
        return math.nan
    difs = [x - y for x, y in pares]
    obs = abs(sum(difs) / len(difs))
    rng = random.Random(SEED)
    extremos = 0
    for _ in range(n):
        troca = [d if rng.random() < 0.5 else -d for d in difs]
        if abs(sum(troca) / len(troca)) >= obs:
            extremos += 1
    return extremos / n


# ─────────────────────────────────────────────
# Avaliação
# ─────────────────────────────────────────────

def avaliar_amostra(r: dict[str, Any], modo: str) -> dict[str, float]:
    pergunta = r["pergunta"]
    gabarito = r["gabarito"]
    fatos = r.get("fatos_chave", [])
    nula = r.get("categoria", "") == "C7_nula"

    resposta = {
        "no_rag": r["resposta_norag"],
        "vector_rag": r["resposta_vectorrag"],
        "graph_rag": r["resposta_graphrag"],
    }[modo]
    contexto = {
        "no_rag": "",
        "vector_rag": r.get("contexto_vectorrag", ""),
        "graph_rag": r.get("contexto_graphrag", ""),
    }[modo]

    scores: dict[str, float] = {
        "faithfulness": faithfulness(resposta, contexto),
        "answer_relevancy": answer_relevancy(pergunta, resposta),
        "answer_correctness": answer_correctness(resposta, gabarito),
        "context_recall": context_recall(contexto, gabarito) if modo != "no_rag" else math.nan,
        "context_precision": context_precision(pergunta, contexto) if modo != "no_rag" else math.nan,
        "cobertura_fatos": cobertura_fatos(resposta, fatos),
    }
    # Em perguntas nulas não existe fato a cobrir; o que importa é não alucinar.
    if nula:
        scores["cobertura_fatos"] = math.nan
        scores["abstencao_correta"] = abstencao_correta(pergunta, resposta)
    return scores


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cache = RESULTS_DIR / "respostas_brutas.json"
    if not cache.exists():
        print("respostas_brutas.json não encontrado. Rode: bun run src/evaluation/run_eval.ts")
        sys.exit(1)

    resultados: list[dict[str, Any]] = json.loads(cache.read_text(encoding="utf-8"))
    total = len(resultados)
    print(f"Avaliando {total} perguntas × {len(MODOS)} modos com {EVAL_MODEL} "
          f"({WORKERS} threads)...\n")

    tarefas = [(i, r, modo) for i, r in enumerate(resultados) for modo in MODOS]
    saidas: dict[tuple[int, str], dict[str, float]] = {}
    feitos = [0]

    def trabalho(t):
        i, r, modo = t
        s = avaliar_amostra(r, modo)
        with _lock:
            feitos[0] += 1
            print(f"  [{feitos[0]:3d}/{len(tarefas)}] {r.get('id', i):>18} {modo:11} "
                  f"faith={s['faithfulness']:.2f} corr={s['answer_correctness']:.2f} "
                  f"cr={s['context_recall']:.2f} cp={s['context_precision']:.2f}"
                  .replace("nan", " — "))
        return (i, modo), s

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for chave, s in pool.map(trabalho, tarefas):
            saidas[chave] = s

    # ── Consolidação ──────────────────────────────────────────────────────────
    por_pergunta: list[dict[str, Any]] = []
    series: dict[str, dict[str, list[float]]] = {
        m: {met: [] for met in METRICAS + ["abstencao_correta"]} for m in MODOS
    }
    series_cat: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: {m: defaultdict(list) for m in MODOS}
    )

    for i, r in enumerate(resultados):
        entrada = {
            "id": r.get("id", f"Q{i+1}"),
            "categoria": r.get("categoria", "legado"),
            "pergunta": r["pergunta"],
        }
        cat = entrada["categoria"]
        for modo in MODOS:
            s = saidas[(i, modo)]
            entrada[modo] = {k: (None if math.isnan(v) else round(v, 4)) for k, v in s.items()}
            for met in METRICAS + ["abstencao_correta"]:
                val = s.get(met, math.nan)
                series[modo][met].append(val)
                series_cat[cat][modo][met].append(val)
        por_pergunta.append(entrada)

    scores_finais: dict[str, Any] = {}
    for modo in MODOS:
        scores_finais[modo] = {}
        for met in METRICAS + ["abstencao_correta"]:
            vals = series[modo][met]
            m = media(vals)
            lo, hi = bootstrap_ic(vals)
            scores_finais[modo][met] = {
                "media": None if math.isnan(m) else round(m, 4),
                "ic95": None if math.isnan(lo) else [round(lo, 4), round(hi, 4)],
                "n": len(_validos(vals)),
            }

    # GraphRAG vs VectorRAG, pareado
    significancia = {}
    for met in METRICAS:
        p = teste_permutacao(series["graph_rag"][met], series["vector_rag"][met])
        dif = media(series["graph_rag"][met]) - media(series["vector_rag"][met])
        significancia[met] = {
            "diferenca_graph_menos_vector": None if math.isnan(dif) else round(dif, 4),
            "p_valor": None if math.isnan(p) else round(p, 4),
        }

    por_categoria: dict[str, Any] = {}
    for cat, modos in sorted(series_cat.items()):
        por_categoria[cat] = {
            "n": len(modos["graph_rag"]["faithfulness"]),
            **{
                modo: {met: (None if math.isnan(media(v)) else round(media(v), 4))
                       for met, v in mets.items()}
                for modo, mets in modos.items()
            },
        }

    saida = {
        "config": {
            "modelo_juiz": EVAL_MODEL, "n_perguntas": total,
            "bootstrap": BOOTSTRAP_N, "seed": SEED,
        },
        "geral": scores_finais,
        "significancia_graph_vs_vector": significancia,
        "por_categoria": por_categoria,
    }
    (RESULTS_DIR / "ragas_scores.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS_DIR / "ragas_scores_por_pergunta.json").write_text(
        json.dumps(por_pergunta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Relatório ─────────────────────────────────────────────────────────────
    def cel(modo: str, met: str) -> str:
        d = scores_finais[modo][met]
        if d["media"] is None:
            return f"{'—':>18}"
        ic = d["ic95"]
        return f"{d['media']:.3f} [{ic[0]:.2f}–{ic[1]:.2f}]".rjust(18)

    print("\n" + "=" * 82)
    print(f"RESULTADOS — {total} perguntas, média [IC 95% bootstrap]")
    print("=" * 82)
    print(f"{'Métrica':<20}{'No RAG':>18}{'VectorRAG':>18}{'GraphRAG':>18}   p")
    print("-" * 82)
    for met in METRICAS:
        p = significancia[met]["p_valor"]
        ptxt = "—" if p is None else (f"{p:.4f}" if p >= 0.0001 else "<0.0001")
        print(f"{met:<20}" + "".join(cel(m, met) for m in MODOS) + f"   {ptxt}")

    absten = scores_finais
    print("-" * 82)
    print(f"{'abstencao_correta':<20}" + "".join(cel(m, "abstencao_correta") for m in MODOS)
          + "   (só C7_nula)")

    print("\n" + "=" * 82)
    print("POR CATEGORIA — answer_correctness (média)")
    print("=" * 82)
    print(f"{'Categoria':<22}{'n':>4}{'No RAG':>12}{'VectorRAG':>12}{'GraphRAG':>12}")
    print("-" * 82)
    for cat, d in por_categoria.items():
        linha = f"{cat:<22}{d['n']:>4}"
        for modo in MODOS:
            v = d[modo].get("answer_correctness")
            linha += f"{'—':>12}" if v is None else f"{v:>12.3f}"
        print(linha)

    print("\n" + "=" * 82)
    print("POR CATEGORIA — context_recall (média)")
    print("=" * 82)
    print(f"{'Categoria':<22}{'n':>4}{'VectorRAG':>12}{'GraphRAG':>12}")
    print("-" * 82)
    for cat, d in por_categoria.items():
        linha = f"{cat:<22}{d['n']:>4}"
        for modo in ["vector_rag", "graph_rag"]:
            v = d[modo].get("context_recall")
            linha += f"{'—':>12}" if v is None else f"{v:>12.3f}"
        print(linha)

    print(f"\nSalvo em: {RESULTS_DIR / 'ragas_scores.json'}")


if __name__ == "__main__":
    main()
