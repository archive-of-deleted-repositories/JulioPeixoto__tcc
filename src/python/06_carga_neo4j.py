"""
Carrega todos os dados processados no Neo4j.

Nós criados : Estado, Municipio, Estacao, Fenomeno, Evento
Arestas     : PERTENCE_A, REGISTROU, SOFREU, CAUSADO_POR, AFETOU
"""

import json
import os
from pathlib import Path

from neo4j import GraphDatabase
from tqdm import tqdm

PROCESSED = Path(__file__).parents[2] / "data" / "processed"
RAW = Path(__file__).parents[2] / "data" / "raw"

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "senha")

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def run(tx, cypher: str, params: dict = None):
    tx.run(cypher, params or {})


# ──────────────────────────────────────────────
# Índices e constraints
# ──────────────────────────────────────────────

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Estado) REQUIRE e.sigla IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Municipio) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Estacao) REQUIRE s.codigo IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Fenomeno) REQUIRE f.nome IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (ev:Evento) REQUIRE ev.id IS UNIQUE",
]


def criar_indices():
    with driver.session() as s:
        for c in CONSTRAINTS:
            s.run(c)
    print("Constraints criadas")


# ──────────────────────────────────────────────
# Carga de nós
# ──────────────────────────────────────────────

def carregar_estados():
    estados = json.loads((RAW / "ibge_estados.json").read_text())
    with driver.session() as s:
        for e in tqdm(estados, desc="Estados"):
            s.execute_write(
                run,
                "MERGE (e:Estado {sigla: $sigla}) SET e.nome = $nome, e.id = $id",
                {"sigla": e["sigla"], "nome": e["nome"], "id": e["id"]},
            )
    print(f"  {len(estados)} estados")


def carregar_municipios():
    import pandas as pd
    df = pd.read_csv(PROCESSED / "municipios_centroides.csv")
    with driver.session() as s:
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Municípios"):
            s.execute_write(
                run,
                """
                MERGE (m:Municipio {id: $id})
                SET m.nome = $nome, m.uf = $uf, m.lat = $lat, m.lon = $lon
                WITH m
                MATCH (e:Estado {sigla: $uf})
                MERGE (m)-[:PERTENCE_A]->(e)
                """,
                {
                    "id": int(row["id"]),
                    "nome": row["nome"],
                    "uf": row["uf"],
                    "lat": float(row["lat"]) if row["lat"] == row["lat"] else None,
                    "lon": float(row["lon"]) if row["lon"] == row["lon"] else None,
                },
            )
    print(f"  {len(df)} municípios")


def carregar_estacoes():
    estacoes = json.loads((PROCESSED / "estacoes_com_municipio.json").read_text())
    with driver.session() as s:
        for e in tqdm(estacoes, desc="Estações"):
            codigo = e.get("CD_ESTACAO") or e.get("codigo", "")
            s.execute_write(
                run,
                """
                MERGE (s:Estacao {codigo: $codigo})
                SET s.nome = $nome, s.lat = $lat, s.lon = $lon, s.tipo = $tipo
                WITH s
                MATCH (m:Municipio {id: $mun_id})
                MERGE (s)-[:PERTENCE_A]->(m)
                """,
                {
                    "codigo": codigo,
                    "nome": e.get("DC_NOME", ""),
                    "lat": float(e.get("VL_LATITUDE", 0) or 0),
                    "lon": float(e.get("VL_LONGITUDE", 0) or 0),
                    "tipo": e.get("TP_ESTACAO", ""),
                    "mun_id": e.get("municipio_id"),
                },
            )
    print(f"  {len(estacoes)} estações")


# ──────────────────────────────────────────────
# Carga de eventos
# ──────────────────────────────────────────────

FENOMENOS = {
    "precipitacao_extrema": "Precipitação Extrema",
    "chuva_muito_forte": "Chuva Muito Forte",
    "calor_extremo": "Calor Extremo",
    "frio_extremo": "Frio Extremo / Geada",
    "baixa_umidade": "Baixa Umidade Crítica",
    "enchente": "Enchente",
    "deslizamento": "Deslizamento",
    "seca": "Seca",
    "granizo": "Granizo",
    "vendaval": "Vendaval",
    "onda_de_calor": "Onda de Calor",
    "geada": "Geada",
    "outro": "Outro",
}


def garantir_fenomenos():
    with driver.session() as s:
        for chave, nome in FENOMENOS.items():
            s.execute_write(
                run,
                "MERGE (f:Fenomeno {nome: $nome}) SET f.chave = $chave",
                {"nome": nome, "chave": chave},
            )


def carregar_eventos_inmet():
    path = PROCESSED / "eventos_extremos_inmet.jsonl"
    if not path.exists():
        print("  eventos_extremos_inmet.jsonl não encontrado, pulando")
        return
    linhas = path.read_text().splitlines()
    with driver.session() as s:
        for i, linha in enumerate(tqdm(linhas, desc="Eventos INMET")):
            ev = json.loads(linha)
            ev_id = f"INMET_{ev['estacao']}_{ev['data']}_{ev['tipo']}"
            fenomeno_nome = FENOMENOS.get(ev["tipo"], "Outro")
            s.execute_write(
                run,
                """
                MERGE (evento:Evento {id: $id})
                SET evento.data = date($data),
                    evento.tipo = $tipo,
                    evento.valor = $valor,
                    evento.fonte = 'INMET'
                WITH evento
                MATCH (f:Fenomeno {nome: $fenomeno})
                MERGE (evento)-[:CAUSADO_POR]->(f)
                WITH evento
                MATCH (s:Estacao {codigo: $estacao})
                MERGE (s)-[:REGISTROU]->(evento)
                WITH evento, s
                MATCH (s)-[:PERTENCE_A]->(m:Municipio)
                MERGE (m)-[:SOFREU]->(evento)
                """,
                {
                    "id": ev_id,
                    "data": ev["data"],
                    "tipo": ev["tipo"],
                    "valor": ev["valor"],
                    "fenomeno": fenomeno_nome,
                    "estacao": ev["estacao"],
                },
            )
    print(f"  {len(linhas)} eventos INMET")


def carregar_eventos_cemaden():
    path = PROCESSED / "eventos_cemaden.jsonl"
    if not path.exists():
        print("  eventos_cemaden.jsonl não encontrado, pulando")
        return
    linhas = path.read_text().splitlines()
    with driver.session() as s:
        for i, linha in enumerate(tqdm(linhas, desc="Eventos CEMADEN")):
            ev = json.loads(linha)
            ev_id = f"CEMADEN_{ev.get('municipio', '')}_{ev.get('data', '')}_{i}"
            fenomeno_nome = FENOMENOS.get(ev.get("tipo", "outro"), "Outro")
            s.execute_write(
                run,
                """
                MERGE (evento:Evento {id: $id})
                SET evento.data = date($data),
                    evento.tipo = $tipo,
                    evento.descricao = $descricao,
                    evento.mortos = $mortos,
                    evento.afetados = $afetados,
                    evento.fonte = 'CEMADEN'
                WITH evento
                MATCH (f:Fenomeno {nome: $fenomeno})
                MERGE (evento)-[:CAUSADO_POR]->(f)
                WITH evento
                MATCH (m:Municipio {nome: $municipio})
                WHERE m.uf = $uf OR $uf IS NULL
                WITH evento, m LIMIT 1
                MERGE (m)-[:SOFREU]->(evento)
                """,
                {
                    "id": ev_id,
                    "data": ev.get("data") or "1900-01-01",
                    "tipo": ev.get("tipo", "outro"),
                    "descricao": ev.get("descricao", ""),
                    "mortos": ev.get("mortos") or 0,
                    "afetados": ev.get("afetados") or 0,
                    "fenomeno": fenomeno_nome,
                    "municipio": ev.get("municipio", ""),
                    "uf": ev.get("uf"),
                },
            )
    print(f"  {len(linhas)} eventos CEMADEN")


def carregar_alertas():
    path = PROCESSED / "alertas_inmet.jsonl"
    if not path.exists():
        print("  alertas_inmet.jsonl não encontrado, pulando")
        return
    linhas = path.read_text().splitlines()
    with driver.session() as s:
        for linha in tqdm(linhas, desc="Alertas RSS"):
            alerta = json.loads(linha)
            ev_id = f"ALERTA_{alerta['id']}"
            s.execute_write(
                run,
                """
                MERGE (evento:Evento {id: $id})
                SET evento.titulo = $titulo,
                    evento.publicado = $publicado,
                    evento.link = $link,
                    evento.fonte = 'INMET_RSS'
                WITH evento
                UNWIND $municipios AS mun
                MATCH (m:Municipio {id: mun.id})
                MERGE (m)-[:SOFREU]->(evento)
                """,
                {
                    "id": ev_id,
                    "titulo": alerta.get("titulo", ""),
                    "publicado": alerta.get("publicado", ""),
                    "link": alerta.get("link", ""),
                    "municipios": alerta.get("municipios", []),
                },
            )
    print(f"  {len(linhas)} alertas")


if __name__ == "__main__":
    print("Criando constraints...")
    criar_indices()

    print("\nCarregando nós base...")
    carregar_estados()
    carregar_municipios()
    carregar_estacoes()

    print("\nCarregando fenômenos...")
    garantir_fenomenos()

    print("\nCarregando eventos...")
    carregar_eventos_inmet()
    carregar_eventos_cemaden()
    carregar_alertas()

    driver.close()
    print("\nCarga concluída.")
