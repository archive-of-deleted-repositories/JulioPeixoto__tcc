"""
OBSOLETO — mantido apenas para reprodutibilidade dos resultados antigos (5 perguntas).

Use `src/evaluation/build_benchmark.py`, que gera 70 perguntas em 7 categorias.

Por que foi substituído: este script deriva os gabaritos executando Cypher no
MESMO Neo4j que o pipeline GraphRAG consulta. O gabarito passa a ser, por
construção, aquilo que o GraphRAG recupera — o que infla `context_recall` desse
modo e não mede capacidade real. O benchmark novo deriva o ground truth do JSONL
de origem (data/processed/eventos_extremos_inmet.jsonl), independente do motor de
recuperação avaliado. Ver BENCHMARK.md, seção 1.1.

────────────────────────────────────────────────────────────────────────────────

Deriva gabaritos corretos a partir dos dados reais no Neo4j.

Executa as mesmas queries usadas pelo pipeline GraphRAG e formata os resultados
como ground truth para a avaliação RAGAS. Salva em derive_gabaritos.json.

Uso:
    python src/evaluation/derive_gabaritos.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).parents[2] / ".env")

URI      = os.environ["NEO4J_URI"]
USER     = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

RESULTS_DIR = Path(__file__).parents[2] / "data" / "evaluation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run(cypher: str, params: dict | None = None) -> list[dict]:
    with driver.session() as session:
        result = session.run(cypher, params or {})
        return [dict(r) for r in result]


# ─── Q1: RS — precipitação extrema 2020-2024 ──────────────────────────────────
print("Q1: Ranking RS precipitação extrema 2020-2024...")
q1_ranking = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: 'RS'})
    MATCH (m)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE e.tipo = 'precipitacao_extrema'
      AND e.data >= date('2020-01-01')
      AND e.data <= date('2024-12-31')
    RETURN m.nome AS municipio, count(e) AS total
    ORDER BY total DESC LIMIT 10
""")
q1_linhas = [f"{r['municipio']} ({r['total']} episódios)" for r in q1_ranking]
q1_gabarito = (
    "Os municípios do Rio Grande do Sul com mais episódios de precipitação extrema "
    f"(precipitação diária ≥ 50 mm) entre 2020 e 2024 são: {', '.join(q1_linhas)}. "
    "Nota: cobertura baseada nas estações INMET das regiões Sul, Sudeste e Centro-Oeste."
)

# ─── Q2: MT — calor extremo 2023 ──────────────────────────────────────────────
print("Q2: MT calor extremo 2023...")
q2_records = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: 'MT'})
    MATCH (m)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE e.tipo = 'calor_extremo'
      AND e.data >= date('2023-01-01')
      AND e.data <= date('2023-12-31')
    RETURN m.nome AS municipio, e.data AS data, e.valor AS valor
    ORDER BY e.valor DESC LIMIT 5
""")
q2_count = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: 'MT'})
    MATCH (m)-[:SOFREU]->(e:Evento)
    WHERE e.tipo = 'calor_extremo'
      AND e.data >= date('2023-01-01')
      AND e.data <= date('2023-12-31')
    RETURN count(e) AS total
""")[0]["total"]
q2_municipios = list({r["municipio"] for r in q2_records})
q2_max = max(q2_records, key=lambda r: r["valor"]) if q2_records else None
q2_gabarito = (
    f"Sim. Foram registrados {q2_count} episódios de calor extremo (temperatura máxima ≥ 40°C) "
    f"em Mato Grosso em 2023, com pico em {q2_max['municipio']} ({q2_max['valor']}°C em {q2_max['data']}). "
    f"Municípios afetados incluem: {', '.join(q2_municipios[:5])}. "
    "Os registros concentram-se entre outubro e dezembro, período de seca no cerrado."
    if q2_records else
    "Não foram encontrados registros de calor extremo em MT em 2023 na base INMET."
)

# ─── Q3: SP — chuva muito forte 2022 ──────────────────────────────────────────
print("Q3: SP chuva muito forte 2022...")
q3_records = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: 'SP'})
    MATCH (m)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE e.tipo = 'chuva_muito_forte'
      AND e.data >= date('2022-01-01')
      AND e.data <= date('2022-12-31')
    RETURN m.nome AS municipio, e.data AS data, e.valor AS valor
    ORDER BY e.valor DESC LIMIT 10
""")
q3_count = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: 'SP'})
    MATCH (m)-[:SOFREU]->(e:Evento)
    WHERE e.tipo = 'chuva_muito_forte'
      AND e.data >= date('2022-01-01')
      AND e.data <= date('2022-12-31')
    RETURN count(e) AS total
""")[0]["total"]
q3_linhas = [f"{r['municipio']} ({r['valor']} mm em {r['data']})" for r in q3_records[:5]]
q3_gabarito = (
    f"Foram registrados {q3_count} episódios de chuva muito forte (≥ 100 mm/dia) "
    f"em São Paulo em 2022. Os maiores volumes foram: {', '.join(q3_linhas)}. "
    "Os eventos concentram-se no verão (janeiro) e primavera (outubro-dezembro)."
    if q3_records else
    "Não foram encontrados registros de chuva muito forte em SP em 2022 na base INMET."
)

# ─── Q4: Sul — frio extremo (meses com mais eventos) ─────────────────────────
print("Q4: Sul frio extremo por mês...")
hoje = date.today()
inicio_padrao = (hoje - timedelta(days=730)).isoformat()

q4_records = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado)
    WHERE est.sigla IN ['RS', 'SC', 'PR']
    MATCH (m)-[:SOFREU]->(e:Evento)
    WHERE e.tipo = 'frio_extremo'
      AND e.data >= date($inicio)
    RETURN e.data.month AS mes, count(e) AS total
    ORDER BY total DESC LIMIT 6
""", {"inicio": inicio_padrao})

MESES = {1:"janeiro",2:"fevereiro",3:"março",4:"abril",5:"maio",6:"junho",
         7:"julho",8:"agosto",9:"setembro",10:"outubro",11:"novembro",12:"dezembro"}
q4_linhas = [f"{MESES[r['mes']]} ({r['total']} registros)" for r in q4_records]

q4_municipios = run("""
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado)
    WHERE est.sigla IN ['RS', 'SC', 'PR']
    MATCH (m)-[:SOFREU]->(e:Evento)
    WHERE e.tipo = 'frio_extremo'
      AND e.data >= date($inicio)
    RETURN m.nome AS municipio, count(e) AS total
    ORDER BY total DESC LIMIT 5
""", {"inicio": inicio_padrao})
q4_nomes = [r["municipio"] for r in q4_municipios]

q4_gabarito = (
    f"Os registros de frio extremo (temperatura mínima < 0°C) no Sul do Brasil "
    f"concentram-se principalmente em: {', '.join(q4_linhas[:3])}. "
    f"Os municípios com maior frequência incluem: {', '.join(q4_nomes)}. "
    "O fenômeno é mais intenso em municípios serranos de RS, SC e PR durante o inverno austral."
    if q4_records else
    "Registros de frio extremo no Sul concentram-se entre junho e agosto."
)

# ─── Q5: Brasil — baixa umidade crítica nos últimos 3 anos ────────────────────
print("Q5: Brasil baixa umidade últimos 3 anos...")
inicio_3anos = (hoje - timedelta(days=3*365)).isoformat()

q5_records = run("""
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE e.tipo = 'baixa_umidade'
      AND e.data >= date($inicio)
    RETURN m.nome AS municipio, m.uf AS uf, count(e) AS total
    ORDER BY total DESC LIMIT 10
""", {"inicio": inicio_3anos})

q5_estados: dict[str, int] = {}
for r in q5_records:
    q5_estados[r["uf"]] = q5_estados.get(r["uf"], 0) + r["total"]
q5_top_estados = sorted(q5_estados.items(), key=lambda x: x[1], reverse=True)[:5]
q5_linhas_muni = [f"{r['municipio']} ({r['uf']}, {r['total']} eventos)" for r in q5_records[:5]]
q5_linhas_est  = [f"{uf} ({total} eventos)" for uf, total in q5_top_estados]

q5_gabarito = (
    "Os municípios com mais registros de baixa umidade crítica (< 12%) nos últimos 3 anos são: "
    f"{', '.join(q5_linhas_muni)}. "
    f"Por estado, os mais afetados são: {', '.join(q5_linhas_est)}. "
    "O fenômeno ocorre principalmente no período de estiagem (maio a outubro)."
    if q5_records else
    "Não foram encontrados registros de baixa umidade crítica no período."
)

# ─── Saída ────────────────────────────────────────────────────────────────────
gabaritos = [
    {"pergunta": "Quais municípios do Rio Grande do Sul registraram mais episódios de precipitação extrema entre 2020 e 2024?",
     "gabarito": q1_gabarito},
    {"pergunta": "Houve registros de calor extremo (temperatura máxima acima de 40°C) em Mato Grosso em 2023?",
     "gabarito": q2_gabarito},
    {"pergunta": "Quais municípios de São Paulo tiveram chuva muito forte (acima de 100 mm em um dia) em 2022?",
     "gabarito": q3_gabarito},
    {"pergunta": "Em quais meses ocorrem mais registros de frio extremo (temperatura mínima abaixo de 0°C) no Sul do Brasil?",
     "gabarito": q4_gabarito},
    {"pergunta": "Quais estados brasileiros registraram mais eventos de baixa umidade crítica (abaixo de 12%) nos últimos 3 anos?",
     "gabarito": q5_gabarito},
]

out = RESULTS_DIR / "gabaritos_derivados.json"
out.write_text(json.dumps(gabaritos, ensure_ascii=False, indent=2), encoding="utf-8")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print("\n" + "=" * 70)
print("GABARITOS DERIVADOS DOS DADOS REAIS:")
print("=" * 70)
for i, g in enumerate(gabaritos, 1):
    print(f"\nQ{i}: {g['pergunta'][:60]}...")
    print(f"     {g['gabarito'][:200]}...")

print(f"\nSalvo em: {out}")
driver.close()
