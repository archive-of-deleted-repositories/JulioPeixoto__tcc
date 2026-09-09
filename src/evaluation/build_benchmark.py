"""
Gera o benchmark de avaliação a partir dos DADOS DE ORIGEM (JSONL do INMET).

Motivação metodológica
──────────────────────
A versão anterior (derive_gabaritos.py) derivava os gabaritos executando Cypher
no mesmo Neo4j que o pipeline GraphRAG consulta. Isso introduz circularidade: o
gabarito passa a ser, por construção, aquilo que o GraphRAG recupera, o que infla
context_recall do GraphRAG e não mede capacidade real.

Aqui o ground truth é calculado direto de:
    data/processed/eventos_extremos_inmet.jsonl
    data/processed/estacoes_com_municipio.json

ou seja, de forma independente do motor de recuperação avaliado. Qualquer um dos
três modos (No RAG, VectorRAG, GraphRAG) é julgado contra a mesma verdade externa.

Taxonomia de perguntas
──────────────────────
Adaptada de MultiHop-RAG (Tang & Yang, 2024) e de "RAG vs. GraphRAG: A Systematic
Evaluation" (Han et al., 2025), acrescida das categorias agregativas que
caracterizam o domínio climático:

    C1 factual         — lookup de fato único (single-hop)
    C2 agregacao       — ranking/contagem sobre muitos registros
    C3 comp_temporal   — mesma região, épocas diferentes
    C4 comp_geografica — mesma época, regiões diferentes
    C5 sazonalidade    — distribuição temporal intra-anual
    C6 multi_hop       — travessia estação → município → estado → fenômeno
    C7 nula            — sem resposta na base (mede alucinação)

Cada item carrega `fatos_chave`: valores numéricos/entidades que uma resposta
correta precisa conter. Isso permite uma métrica determinística (cobertura de
fatos), independente de juiz LLM.

Uso:
    .venv/Scripts/python.exe src/evaluation/build_benchmark.py
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).parents[2]
PROCESSED = RAIZ / "data" / "processed"
RESULTS_DIR = RAIZ / "data" / "evaluation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SEED = 42
random.seed(SEED)

MESES = {1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
         7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"}

# Rótulo legível + limiar, espelhando THRESHOLDS de src/data/03_historico_inmet.py
FENOMENOS = {
    "precipitacao_extrema": ("precipitação extrema", "precipitação diária acima de 50 mm"),
    "chuva_muito_forte":    ("chuva muito forte", "precipitação diária acima de 100 mm"),
    "calor_extremo":        ("calor extremo", "temperatura máxima acima de 40 °C"),
    "frio_extremo":         ("frio extremo", "temperatura mínima abaixo de 0 °C"),
    "baixa_umidade":        ("baixa umidade crítica", "umidade relativa mínima abaixo de 12%"),
}

# Fenômenos previstos no schema do grafo mas SEM nenhum evento carregado
# (dependem do CEMADEN, que não foi processado). Base para perguntas nulas.
FENOMENOS_AUSENTES = {
    "enchente": "enchentes",
    "deslizamento": "deslizamentos",
    "seca": "eventos de seca",
    "granizo": "episódios de granizo",
    "vendaval": "vendavais",
}

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}


# ─────────────────────────────────────────────
# Carga dos fatos
# ─────────────────────────────────────────────

def carregar_eventos() -> list[dict[str, Any]]:
    estacoes = json.loads((PROCESSED / "estacoes_com_municipio.json").read_text(encoding="utf-8"))
    mapa = {
        e["CD_ESTACAO"]: {
            "municipio": e.get("municipio_nome"),
            "uf": e.get("municipio_uf"),
            "estacao_nome": e.get("DC_NOME"),
        }
        for e in estacoes
        if e.get("municipio_nome")
    }

    eventos: list[dict[str, Any]] = []
    with (PROCESSED / "eventos_extremos_inmet.jsonl").open(encoding="utf-8") as fh:
        for linha in fh:
            ev = json.loads(linha)
            geo = mapa.get(ev["estacao"])
            if geo is None:
                continue  # estação sem município mapeado — fora do escopo do grafo
            ev.update(geo)
            ev["ano"] = int(ev["data"][:4])
            ev["mes"] = int(ev["data"][5:7])
            eventos.append(ev)
    return eventos


class Fatos:
    """Índices agregados sobre os eventos, para montar perguntas e gabaritos exatos."""

    def __init__(self, eventos: list[dict[str, Any]]):
        self.eventos = eventos
        self.por_uf_tipo_ano: Counter = Counter()
        self.por_mun_tipo_ano: Counter = Counter()
        self.por_uf_tipo_mes: Counter = Counter()
        self.mun_uf: dict[str, str] = {}
        self.estacoes_mun_ano: dict[tuple[str, str, int], set[str]] = defaultdict(set)

        for e in eventos:
            uf, mun, tipo, ano, mes = e["uf"], e["municipio"], e["tipo"], e["ano"], e["mes"]
            self.por_uf_tipo_ano[(uf, tipo, ano)] += 1
            self.por_mun_tipo_ano[(mun, uf, tipo, ano)] += 1
            self.por_uf_tipo_mes[(uf, tipo, mes)] += 1
            self.mun_uf[mun] = uf
            self.estacoes_mun_ano[(mun, uf, ano)].add(e["estacao"])

    # -- consultas auxiliares -------------------------------------------------

    def total_mun(self, mun: str, uf: str, tipo: str | None, anos: range | list[int]) -> int:
        anos = list(anos)
        if tipo:
            return sum(self.por_mun_tipo_ano[(mun, uf, tipo, a)] for a in anos)
        return sum(
            self.por_mun_tipo_ano[(mun, uf, t, a)] for t in FENOMENOS for a in anos
        )

    def total_uf(self, uf: str, tipo: str | None, anos: range | list[int]) -> int:
        anos = list(anos)
        if tipo:
            return sum(self.por_uf_tipo_ano[(uf, tipo, a)] for a in anos)
        return sum(self.por_uf_tipo_ano[(uf, t, a)] for t in FENOMENOS for a in anos)

    def ranking_municipios(self, uf: str, tipo: str, anos: list[int], n: int = 5) -> list[tuple[str, int]]:
        c: Counter = Counter()
        for (mun, m_uf, t, a), v in self.por_mun_tipo_ano.items():
            if m_uf == uf and t == tipo and a in anos:
                c[mun] += v
        return c.most_common(n)

    def eventos_de(self, **filtros: Any) -> list[dict[str, Any]]:
        return [
            e for e in self.eventos
            if all(e.get(k) == v for k, v in filtros.items())
        ]


# ─────────────────────────────────────────────
# Formatação
# ─────────────────────────────────────────────

def rotulo(tipo: str) -> str:
    return FENOMENOS[tipo][0]


def criterio(tipo: str) -> str:
    return FENOMENOS[tipo][1]


def item(
    idx: int, categoria: str, pergunta: str, gabarito: str,
    fatos_chave: list[str], meta: dict[str, Any], nota: str = "",
) -> dict[str, Any]:
    return {
        "id": f"{categoria}-{idx:02d}",
        "categoria": categoria,
        "pergunta": pergunta,
        "gabarito": gabarito.strip(),
        "nota": nota.strip(),
        "fatos_chave": fatos_chave,
        "metadados": meta,
    }


# Procedência e ressalvas metodológicas ficam FORA do gabarito.
#
# Na primeira rodada esse texto era concatenado a cada gabarito. Como o juiz
# decompõe o gabarito em afirmações e verifica cada uma na resposta, a nota de
# procedência entrava como 1–2 afirmações que nenhuma resposta produziria —
# rebaixando answer_correctness de TODOS os modos e, pior, de forma desigual
# entre categorias (as nulas, cujo gabarito é curto, apanhavam mais). O campo
# `nota` preserva a informação para leitura humana sem entrar na avaliação.
NOTA_BASE = (
    "Base de referência: eventos extremos derivados das séries horárias das estações "
    "automáticas do INMET (2015–2024)."
)


# ─────────────────────────────────────────────
# Geradores por categoria
# ─────────────────────────────────────────────

def gerar_c1_factual(f: Fatos, n: int = 10) -> list[dict[str, Any]]:
    """Lookup single-hop: houve fenômeno X em município Y no ano Z?

    Metade dos itens com resposta afirmativa, metade negativa — evita que o
    sistema acerte sempre respondendo 'sim'.
    """
    positivos = [
        (mun, uf, tipo, ano, total)
        for (mun, uf, tipo, ano), total in f.por_mun_tipo_ano.items()
        if total >= 5
    ]
    positivos.sort(key=lambda x: (-x[4], x[0]))
    escolhidos_pos = random.sample(positivos[:200], n // 2)

    # Negativos: par (município, tipo, ano) sem nenhum registro, mas em município
    # que TEM estação (ou seja, ausência real, não falta de cobertura total).
    municipios = sorted(f.mun_uf.items())
    negativos = []
    tentativas = 0
    while len(negativos) < n - n // 2 and tentativas < 20000:
        tentativas += 1
        mun, uf = random.choice(municipios)
        tipo = random.choice(list(FENOMENOS))
        ano = random.randint(2015, 2024)
        if f.por_mun_tipo_ano[(mun, uf, tipo, ano)] == 0 and f.estacoes_mun_ano.get((mun, uf, ano)):
            negativos.append((mun, uf, tipo, ano, 0))

    itens = []
    for i, (mun, uf, tipo, ano, total) in enumerate(escolhidos_pos + negativos, 1):
        pergunta = (
            f"Houve registros de {rotulo(tipo)} ({criterio(tipo)}) "
            f"em {mun} ({uf}) em {ano}?"
        )
        if total > 0:
            evs = [e for e in f.eventos_de(municipio=mun, uf=uf, tipo=tipo, ano=ano)]
            pico = max(evs, key=lambda e: abs(e["valor"]))
            gabarito = (
                f"Sim. Foram registrados {total} dias com {rotulo(tipo)} em {mun} ({uf}) "
                f"em {ano}. O valor mais extremo foi {pico['valor']} {pico['unidade']} "
                f"em {pico['data']}."
            )
            fatos = [str(total), mun, str(ano)]
        else:
            gabarito = (
                f"Não. Não há nenhum registro de {rotulo(tipo)} em {mun} ({uf}) em {ano} "
                f"na base. O município possui estação com dados nesse ano, portanto trata-se "
                f"de ausência do fenômeno e não de falta de cobertura."
            )
            fatos = ["não", mun, str(ano)]
        itens.append(item(i, "C1_factual", pergunta, gabarito, fatos,
                          {"municipio": mun, "uf": uf, "tipo": tipo, "ano": ano, "total": total}, nota=NOTA_BASE))
    return itens


def gerar_c2_agregacao(f: Fatos, n: int = 10) -> list[dict[str, Any]]:
    """Ranking de municípios — exige contagem sobre muitos registros."""
    combos = []
    for uf in UF_NOME:
        for tipo in FENOMENOS:
            anos = list(range(2020, 2025))
            total = f.total_uf(uf, tipo, anos)
            if total >= 60:
                combos.append((uf, tipo, anos, total))
    combos.sort(key=lambda x: -x[3])
    escolhidos = random.sample(combos[:60], min(n, len(combos[:60])))

    itens = []
    for i, (uf, tipo, anos, total) in enumerate(escolhidos, 1):
        rank = f.ranking_municipios(uf, tipo, anos, n=5)
        pergunta = (
            f"Quais foram os 5 municípios de {UF_NOME[uf]} ({uf}) com mais registros de "
            f"{rotulo(tipo)} entre {anos[0]} e {anos[-1]}?"
        )
        linhas = ", ".join(f"{m} ({c} registros)" for m, c in rank)
        gabarito = (
            f"Os 5 municípios de {UF_NOME[uf]} com mais registros de {rotulo(tipo)} "
            f"({criterio(tipo)}) entre {anos[0]} e {anos[-1]} são: {linhas}. "
            f"O estado somou {total} registros do fenômeno no período."
        )
        fatos = [m for m, _ in rank] + [str(rank[0][1])]
        itens.append(item(i, "C2_agregacao", pergunta, gabarito, fatos,
                          {"uf": uf, "tipo": tipo, "anos": anos, "ranking": rank, "total_uf": total}, nota=NOTA_BASE))
    return itens


def gerar_c3_comp_temporal(f: Fatos, n: int = 12) -> list[dict[str, Any]]:
    """Mesma região, épocas diferentes — a capacidade nova sendo testada.

    Só gera o par (ano1, ano2) quando o conjunto de estações do município com
    registros é o MESMO nos dois anos. Sem isso, a diferença mediria disponibilidade
    de sensor em vez do fenômeno (ver ANALISE_COMPARACAO_TEMPORAL.md, seção 4).
    """
    candidatos = []
    for (mun, uf, tipo, ano), total in f.por_mun_tipo_ano.items():
        for outro in range(2015, 2025):
            if outro <= ano:
                continue
            t2 = f.por_mun_tipo_ano[(mun, uf, tipo, outro)]
            est1 = f.estacoes_mun_ano.get((mun, uf, ano), set())
            est2 = f.estacoes_mun_ano.get((mun, uf, outro), set())
            # cobertura estável e contraste mínimo para a pergunta ser interessante
            if est1 and est1 == est2 and total + t2 >= 15 and abs(total - t2) >= 5:
                candidatos.append((mun, uf, tipo, ano, outro, total, t2))
    candidatos.sort(key=lambda x: (-(abs(x[5] - x[6])), x[0]))
    vistos: set[tuple[str, str]] = set()
    escolhidos = []
    for c in candidatos:
        chave = (c[0], c[2])
        if chave in vistos:
            continue
        vistos.add(chave)
        escolhidos.append(c)
        if len(escolhidos) >= n:
            break

    itens = []
    for i, (mun, uf, tipo, a1, a2, t1, t2) in enumerate(escolhidos, 1):
        pergunta = (
            f"Em {mun} ({uf}), houve mais registros de {rotulo(tipo)} em {a1} ou em {a2}? "
            f"Informe a quantidade em cada ano."
        )
        maior, menor = (a1, a2) if t1 > t2 else (a2, a1)
        vmaior, vmenor = (t1, t2) if t1 > t2 else (t2, t1)
        gabarito = (
            f"Em {mun} ({uf}), {maior} teve mais registros de {rotulo(tipo)} "
            f"({criterio(tipo)}): {vmaior} registros em {maior} contra {vmenor} em {menor}, "
            f"diferença de {vmaior - vmenor}."
        )
        fatos = [str(t1), str(t2), str(maior), mun]
        itens.append(item(i, "C3_comp_temporal", pergunta, gabarito, fatos,
                          {"municipio": mun, "uf": uf, "tipo": tipo,
                           "ano_1": a1, "total_1": t1, "ano_2": a2, "total_2": t2,
                           "estacoes": sorted(f.estacoes_mun_ano[(mun, uf, a1)])},
                          nota=(
                              f"As mesmas estações ({', '.join(sorted(f.estacoes_mun_ano[(mun, uf, a1)]))}) "
                              f"reportaram nos dois anos, então a variação não é efeito de mudança "
                              f"de cobertura. {NOTA_BASE}"
                          )))
    return itens


def gerar_c4_comp_geografica(f: Fatos, n: int = 10) -> list[dict[str, Any]]:
    """Mesma época, regiões diferentes."""
    candidatos = []
    for tipo in FENOMENOS:
        for ano in range(2015, 2025):
            ufs = [(uf, f.por_uf_tipo_ano[(uf, tipo, ano)]) for uf in UF_NOME]
            ufs = [(u, v) for u, v in ufs if v >= 10]
            for j in range(len(ufs)):
                for k in range(j + 1, len(ufs)):
                    u1, v1 = ufs[j]
                    u2, v2 = ufs[k]
                    if abs(v1 - v2) >= 10:
                        candidatos.append((tipo, ano, u1, v1, u2, v2))
    escolhidos = random.sample(candidatos, min(n, len(candidatos)))

    itens = []
    for i, (tipo, ano, u1, v1, u2, v2) in enumerate(escolhidos, 1):
        pergunta = (
            f"Em {ano}, qual estado registrou mais dias de {rotulo(tipo)}: "
            f"{UF_NOME[u1]} ({u1}) ou {UF_NOME[u2]} ({u2})? Informe os números."
        )
        vencedor, vv, perdedor, vp = (u1, v1, u2, v2) if v1 > v2 else (u2, v2, u1, v1)
        gabarito = (
            f"{UF_NOME[vencedor]} ({vencedor}) registrou mais dias de {rotulo(tipo)} "
            f"({criterio(tipo)}) em {ano}: {vv} registros, contra {vp} de "
            f"{UF_NOME[perdedor]} ({perdedor})."
        )
        fatos = [str(v1), str(v2), vencedor]
        itens.append(item(i, "C4_comp_geografica", pergunta, gabarito, fatos,
                          {"tipo": tipo, "ano": ano, "uf_1": u1, "total_1": v1,
                           "uf_2": u2, "total_2": v2}, nota=NOTA_BASE))
    return itens


def gerar_c5_sazonalidade(f: Fatos, n: int = 10) -> list[dict[str, Any]]:
    """Distribuição intra-anual — exige agregação por mês sobre a série toda."""
    combos = []
    for uf in UF_NOME:
        for tipo in FENOMENOS:
            total = sum(f.por_uf_tipo_mes[(uf, tipo, m)] for m in range(1, 13))
            if total >= 80:
                combos.append((uf, tipo, total))
    combos.sort(key=lambda x: -x[2])
    escolhidos = random.sample(combos[:50], min(n, len(combos[:50])))

    itens = []
    for i, (uf, tipo, total) in enumerate(escolhidos, 1):
        meses = sorted(
            ((m, f.por_uf_tipo_mes[(uf, tipo, m)]) for m in range(1, 13)),
            key=lambda x: -x[1],
        )[:3]
        pergunta = (
            f"Em quais meses do ano se concentram os registros de {rotulo(tipo)} "
            f"em {UF_NOME[uf]} ({uf})? Considere toda a série 2015–2024."
        )
        linhas = ", ".join(f"{MESES[m]} ({c} registros)" for m, c in meses)
        gabarito = (
            f"Os registros de {rotulo(tipo)} ({criterio(tipo)}) em {UF_NOME[uf]} "
            f"concentram-se em: {linhas}. O estado acumula {total} registros do fenômeno "
            f"em 2015–2024."
        )
        fatos = [MESES[m] for m, _ in meses] + [str(meses[0][1])]
        itens.append(item(i, "C5_sazonalidade", pergunta, gabarito, fatos,
                          {"uf": uf, "tipo": tipo, "top_meses": meses, "total": total}, nota=NOTA_BASE))
    return itens


def gerar_c6_multi_hop(f: Fatos, n: int = 10) -> list[dict[str, Any]]:
    """Travessia estação → município → estado, com agregação de extremo.

    Responder exige ligar o valor máximo à estação que o registrou E ao município
    onde ela fica — dois saltos relacionais.
    """
    combos = []
    for uf in UF_NOME:
        for tipo in FENOMENOS:
            for ano in range(2015, 2025):
                if f.por_uf_tipo_ano[(uf, tipo, ano)] >= 15:
                    combos.append((uf, tipo, ano))
    escolhidos = random.sample(combos, min(n, len(combos)))

    itens = []
    for i, (uf, tipo, ano) in enumerate(escolhidos, 1):
        evs = [e for e in f.eventos if e["uf"] == uf and e["tipo"] == tipo and e["ano"] == ano]
        pico = max(evs, key=lambda e: abs(e["valor"]))
        n_estacoes = len({e["estacao"] for e in evs})
        pergunta = (
            f"Qual estação do INMET registrou o valor mais extremo de {rotulo(tipo)} "
            f"em {UF_NOME[uf]} ({uf}) em {ano}, em que município ela fica e qual foi o valor?"
        )
        gabarito = (
            f"A estação {pico['estacao']} ({pico['estacao_nome']}), no município de "
            f"{pico['municipio']} ({uf}), registrou o valor mais extremo de {rotulo(tipo)} "
            f"em {ano}: {pico['valor']} {pico['unidade']} em {pico['data']}. "
            f"No total, {n_estacoes} estações do estado registraram o fenômeno nesse ano "
            f"({len(evs)} registros)."
        )
        fatos = [pico["estacao"], pico["municipio"], str(pico["valor"])]
        itens.append(item(i, "C6_multi_hop", pergunta, gabarito, fatos,
                          {"uf": uf, "tipo": tipo, "ano": ano, "estacao": pico["estacao"],
                           "municipio": pico["municipio"], "valor": pico["valor"],
                           "data": pico["data"], "n_estacoes": n_estacoes}, nota=NOTA_BASE))
    return itens


def gerar_c7_nula(f: Fatos, n: int = 8) -> list[dict[str, Any]]:
    """Perguntas sem resposta na base — medem propensão a alucinar.

    Duas fontes de nulidade:
      (a) fenômenos previstos no schema mas sem nenhum evento carregado
          (enchente, deslizamento, seca, granizo, vendaval — dependem do CEMADEN);
      (b) combinações (UF, fenômeno, ano) com zero registros.
    A resposta correta é declarar a ausência, não produzir números.
    """
    itens = []
    idx = 1

    municipios_grandes = [m for m, uf in f.mun_uf.items()][:400]
    for tipo, rot in list(FENOMENOS_AUSENTES.items())[:5]:
        mun = random.choice(municipios_grandes)
        uf = f.mun_uf[mun]
        ano = random.randint(2015, 2024)
        pergunta = f"Quantos registros de {rot} constam na base para {mun} ({uf}) em {ano}?"
        # O gabarito contém APENAS o que uma resposta correta afirmaria. A
        # explicação de por que o dado falta é procedência, e vai em `nota` —
        # se entrasse aqui, o juiz a cobraria da resposta e puniria quem
        # respondeu certo. Ver BENCHMARK.md §5.
        gabarito = f"Nenhum. A base não contém nenhum registro de {rot}."
        itens.append(item(idx, "C7_nula", pergunta, gabarito,
                          ["não há", "nenhum registro"],
                          {"tipo_ausente": tipo, "municipio": mun, "uf": uf, "ano": ano},
                          nota=(
                              f"O tipo '{tipo}' existe no esquema do grafo, mas nenhum evento "
                              f"desse tipo foi carregado: a fonte que os forneceria (CEMADEN) "
                              f"não foi processada. {NOTA_BASE}"
                          )))
        idx += 1

    vazios = [
        (uf, tipo, ano)
        for uf in UF_NOME for tipo in FENOMENOS for ano in range(2015, 2025)
        if f.por_uf_tipo_ano[(uf, tipo, ano)] == 0 and f.total_uf(uf, None, [ano]) > 0
    ]
    for uf, tipo, ano in random.sample(vazios, min(n - len(itens), len(vazios))):
        pergunta = (
            f"Quantos dias com {rotulo(tipo)} ({criterio(tipo)}) constam na base "
            f"para {UF_NOME[uf]} ({uf}) em {ano}?"
        )
        gabarito = (
            f"Nenhum. Não há registro de {rotulo(tipo)} em {UF_NOME[uf]} ({uf}) em {ano} "
            f"na base."
        )
        itens.append(item(idx, "C7_nula", pergunta, gabarito,
                          ["nenhum", "não há"],
                          {"uf": uf, "tipo": tipo, "ano": ano, "total": 0},
                          nota=(
                              f"O estado tem registros de outros fenômenos em {ano}, ou seja, "
                              f"há cobertura de estação — o fenômeno é que não ocorreu acima "
                              f"do limiar. {NOTA_BASE}"
                          )))
        idx += 1

    return itens


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main() -> None:
    print("Carregando eventos de origem...")
    eventos = carregar_eventos()
    f = Fatos(eventos)
    print(f"  {len(eventos)} eventos com município mapeado")
    print(f"  {len(f.mun_uf)} municípios, {len({e['uf'] for e in eventos})} UFs\n")

    benchmark: list[dict[str, Any]] = []
    for nome, gerador, qtd in [
        ("C1_factual",         gerar_c1_factual,      10),
        ("C2_agregacao",       gerar_c2_agregacao,    10),
        ("C3_comp_temporal",   gerar_c3_comp_temporal, 12),
        ("C4_comp_geografica", gerar_c4_comp_geografica, 10),
        ("C5_sazonalidade",    gerar_c5_sazonalidade, 10),
        ("C6_multi_hop",       gerar_c6_multi_hop,    10),
        ("C7_nula",            gerar_c7_nula,          8),
    ]:
        itens = gerador(f, qtd)
        benchmark.extend(itens)
        print(f"  {nome:22} {len(itens):3d} perguntas")

    out = RESULTS_DIR / "benchmark.json"
    out.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nTotal: {len(benchmark)} perguntas -> {out}")
    print(f"Seed: {SEED} (reprodutível)")

    print("\nAmostra:")
    for cat in ["C1_factual", "C3_comp_temporal", "C6_multi_hop", "C7_nula"]:
        ex = next(b for b in benchmark if b["categoria"] == cat)
        print(f"\n[{cat}] {ex['pergunta']}")
        print(f"  -> {ex['gabarito'][:190]}...")


if __name__ == "__main__":
    main()
