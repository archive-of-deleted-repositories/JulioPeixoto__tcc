"""Baixa municípios e estados do IBGE e salva em data/raw/."""

import json
import sys
import requests
import pandas as pd
from pathlib import Path

RAW = Path(__file__).parents[2] / "data" / "raw"
PROCESSED = Path(__file__).parents[2] / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"


def fetch_estados() -> list[dict]:
    r = requests.get(f"{BASE}/estados?orderBy=nome", timeout=30)
    r.raise_for_status()
    estados = [
        {"id": e["id"], "sigla": e["sigla"], "nome": e["nome"]}
        for e in r.json()
    ]
    path = RAW / "ibge_estados.json"
    path.write_text(json.dumps(estados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Estados: {len(estados)} -> {path}")
    return estados


def _uf_de_municipio(m: dict) -> tuple[str, int] | tuple[None, None]:
    """Extrai sigla e id de UF navegando pela hierarquia do IBGE."""
    try:
        uf = m["microrregiao"]["mesorregiao"]["UF"]
        return uf["sigla"], uf["id"]
    except (TypeError, KeyError):
        pass
    # Fallback: campo "regiao-imediata" presente em algumas versoes da API
    try:
        uf = m["regiao-imediata"]["regiao-intermediaria"]["UF"]
        return uf["sigla"], uf["id"]
    except (TypeError, KeyError):
        return None, None


def fetch_municipios() -> list[dict]:
    r = requests.get(f"{BASE}/municipios?orderBy=nome", timeout=60)
    r.raise_for_status()
    municipios = []
    ignorados = 0
    for m in r.json():
        sigla, uf_id = _uf_de_municipio(m)
        if sigla is None:
            ignorados += 1
            continue
        municipios.append({
            "id": m["id"],
            "nome": m["nome"],
            "uf": sigla,
            "uf_id": uf_id,
        })
    if ignorados:
        print(f"  aviso: {ignorados} entradas sem UF ignoradas", file=sys.stderr)
    path = RAW / "ibge_municipios.json"
    path.write_text(json.dumps(municipios, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Municipios: {len(municipios)} -> {path}")
    return municipios


def fetch_municipios_centroides() -> list[dict]:
    """Baixa centroides de municipios brasileiros (kelvins/municipios-brasileiros)."""
    # Dataset público com lat/lon de todos os 5571 municípios
    url = (
        "https://raw.githubusercontent.com/kelvins/"
        "municipios-brasileiros/main/csv/municipios.csv"
    )
    print(f"Baixando centroides de: {url}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()

    import io
    df_cent = pd.read_csv(io.StringIO(r.text))
    # Colunas: codigo_ibge, nome, latitude, longitude, capital, codigo_uf, uf, ...
    df_cent = df_cent.rename(columns={
        "codigo_ibge": "id",
        "latitude": "lat",
        "longitude": "lon",
    })[["id", "lat", "lon"]]

    df_mun = pd.read_json(RAW / "ibge_municipios.json")
    df = df_mun.merge(df_cent, on="id", how="left")

    out = PROCESSED / "municipios_centroides.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"Centroides: {len(df)} ({df['lat'].notna().sum()} com coords) -> {out}")
    return df.to_dict("records")


if __name__ == "__main__":
    fetch_estados()
    fetch_municipios()
    fetch_municipios_centroides()
