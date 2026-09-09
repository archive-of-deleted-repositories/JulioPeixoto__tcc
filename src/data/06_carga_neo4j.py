"""
Carrega todos os dados processados no Neo4j.

Nós criados : Estado, Municipio, Estacao, Fenomeno, Evento
Arestas     : PERTENCE_A, REGISTROU, SOFREU, CAUSADO_POR, AFETOU
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from tqdm import tqdm

load_dotenv(Path(__file__).parents[2] / ".env")

PROCESSED = Path(__file__).parents[2] / "data" / "processed"
RAW = Path(__file__).parents[2] / "data" / "raw"

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "senha12345")

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def run(tx, cypher: str, params: dict = None):
    tx.run(cypher, params or {})


BATCH = 1000


def carregar_em_lotes(cypher: str, itens: list[dict], desc: str) -> None:
    """Executa `cypher` com UNWIND sobre lotes de `itens`.

    A versão anterior abria uma transação por registro — 33 mil round-trips só
    para os eventos, o que tornava a recarga do grafo inviável na prática. Com
    UNWIND em lotes de 1000 a carga inteira cai para poucos minutos.
    O `cypher` recebe a lista no parâmetro $lote.
    """
    for i in tqdm(range(0, len(itens), BATCH), desc=desc):
        lote = itens[i : i + BATCH]
        with driver.session() as s:
            s.execute_write(run, cypher, {"lote": lote})


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
    estados = json.loads((RAW / "ibge_estados.json").read_text(encoding="utf-8"))
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
    itens = [
        {
            "id": int(row["id"]),
            "nome": row["nome"],
            "uf": row["uf"],
            "lat": float(row["lat"]) if row["lat"] == row["lat"] else None,
            "lon": float(row["lon"]) if row["lon"] == row["lon"] else None,
        }
        for _, row in df.iterrows()
    ]
    carregar_em_lotes(
        """
        UNWIND $lote AS item
        MERGE (m:Municipio {id: item.id})
        SET m.nome = item.nome, m.uf = item.uf, m.lat = item.lat, m.lon = item.lon
        WITH m, item
        MATCH (e:Estado {sigla: item.uf})
        MERGE (m)-[:PERTENCE_A]->(e)
        """,
        itens,
        "Municípios",
    )
    print(f"  {len(itens)} municípios")


def carregar_estacoes():
    estacoes = json.loads((PROCESSED / "estacoes_com_municipio.json").read_text(encoding="utf-8"))
    itens = [
        {
            "codigo": e.get("CD_ESTACAO") or e.get("codigo", ""),
            "nome": e.get("DC_NOME", ""),
            "lat": float(e.get("VL_LATITUDE", 0) or 0),
            "lon": float(e.get("VL_LONGITUDE", 0) or 0),
            "tipo": e.get("TP_ESTACAO", ""),
            "mun_id": e.get("municipio_id"),
        }
        for e in estacoes
    ]
    carregar_em_lotes(
        """
        UNWIND $lote AS item
        MERGE (s:Estacao {codigo: item.codigo})
        SET s.nome = item.nome, s.lat = item.lat, s.lon = item.lon, s.tipo = item.tipo
        WITH s, item
        MATCH (m:Municipio {id: item.mun_id})
        MERGE (s)-[:PERTENCE_A]->(m)
        """,
        itens,
        "Estações",
    )
    print(f"  {len(itens)} estações")


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
    linhas = path.read_text(encoding="utf-8").splitlines()
    itens = []
    for linha in linhas:
        ev = json.loads(linha)
        itens.append({
            "id": f"INMET_{ev['estacao']}_{ev['data']}_{ev['tipo']}",
            "data": ev["data"],
            "tipo": ev["tipo"],
            "valor": ev["valor"],
            "fenomeno": FENOMENOS.get(ev["tipo"], "Outro"),
            "estacao": ev["estacao"],
        })
    carregar_em_lotes(
        """
        UNWIND $lote AS item
        MERGE (evento:Evento {id: item.id})
        SET evento.data  = date(item.data),
            evento.tipo  = item.tipo,
            evento.valor = item.valor,
            evento.fonte = 'INMET'
        WITH evento, item
        MATCH (f:Fenomeno {nome: item.fenomeno})
        MERGE (evento)-[:CAUSADO_POR]->(f)
        WITH evento, item
        MATCH (s:Estacao {codigo: item.estacao})
        MERGE (s)-[:REGISTROU]->(evento)
        WITH evento, s
        MATCH (s)-[:PERTENCE_A]->(m:Municipio)
        MERGE (m)-[:SOFREU]->(evento)
        """,
        itens,
        "Eventos INMET",
    )
    print(f"  {len(itens)} eventos INMET")


def carregar_eventos_cemaden():
    path = PROCESSED / "eventos_cemaden.jsonl"
    if not path.exists():
        print("  eventos_cemaden.jsonl não encontrado, pulando")
        return
    linhas = path.read_text(encoding="utf-8").splitlines()
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
    linhas = path.read_text(encoding="utf-8").splitlines()
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
