"""
Consome o RSS de alertas do INMET e vincula cada alerta a municípios via fuzzy match.

RSS: https://apitempo.inmet.gov.br/alerts-rss
"""

import json
import re
from pathlib import Path

import feedparser
from bs4 import BeautifulSoup
from rapidfuzz import process, fuzz

RAW = Path(__file__).parents[2] / "data" / "raw"
PROCESSED = Path(__file__).parents[2] / "data" / "processed"

RSS_URL = "https://apitempo.inmet.gov.br/alerts-rss"
SCORE_MIN = 85  # threshold fuzzy match


def load_municipios() -> list[dict]:
    path = RAW / "ibge_municipios.json"
    if not path.exists():
        raise SystemExit("Execute 01_ibge.py primeiro.")
    return json.loads(path.read_text())


def extrair_municipios_do_texto(texto: str, nomes_mun: list[str]) -> list[str]:
    """Extrai nomes de municípios mencionados no texto via fuzzy match."""
    # Tokeniza por vírgula, 'e', ponto-e-vírgula
    tokens = re.split(r"[,;/\n]| e ", texto)
    tokens = [t.strip() for t in tokens if len(t.strip()) > 3]
    encontrados = []
    for token in tokens:
        match = process.extractOne(
            token, nomes_mun, scorer=fuzz.token_sort_ratio, score_cutoff=SCORE_MIN
        )
        if match:
            encontrados.append(match[0])
    return list(set(encontrados))


def parse_rss() -> list[dict]:
    feed = feedparser.parse(RSS_URL)
    alertas = []
    for entry in feed.entries:
        soup = BeautifulSoup(entry.get("summary", ""), "html.parser")
        texto = soup.get_text(separator=" ")
        alertas.append({
            "id": entry.get("id", ""),
            "titulo": entry.get("title", ""),
            "publicado": entry.get("published", ""),
            "texto": texto,
            "link": entry.get("link", ""),
        })
    return alertas


if __name__ == "__main__":
    municipios = load_municipios()
    nomes = [m["nome"] for m in municipios]
    mun_index = {m["nome"]: m for m in municipios}

    print("Consumindo RSS INMET...")
    alertas = parse_rss()
    print(f"  {len(alertas)} alertas encontrados")

    resultado = []
    for alerta in alertas:
        municips = extrair_municipios_do_texto(alerta["texto"], nomes)
        resultado.append({
            **alerta,
            "municipios": [
                {"nome": n, "uf": mun_index[n]["uf"], "id": mun_index[n]["id"]}
                for n in municips
                if n in mun_index
            ],
        })

    out = PROCESSED / "alertas_inmet.jsonl"
    with out.open("w") as f:
        for item in resultado:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  {len(resultado)} alertas com municípios → {out}")
