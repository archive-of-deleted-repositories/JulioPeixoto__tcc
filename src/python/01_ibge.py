"""Baixa municípios e estados do IBGE e salva em data/raw/."""

import json
import requests
from pathlib import Path

RAW = Path(__file__).parents[2] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"


def fetch_estados() -> list[dict]:
    r = requests.get(f"{BASE}/estados?orderBy=nome", timeout=30)
    r.raise_for_status()
    estados = [
        {"id": e["id"], "sigla": e["sigla"], "nome": e["nome"]}
        for e in r.json()
    ]
    path = RAW / "ibge_estados.json"
    path.write_text(json.dumps(estados, ensure_ascii=False, indent=2))
    print(f"Estados: {len(estados)} → {path}")
    return estados


def fetch_municipios() -> list[dict]:
    r = requests.get(f"{BASE}/municipios?orderBy=nome", timeout=60)
    r.raise_for_status()
    municipios = [
        {
            "id": m["id"],
            "nome": m["nome"],
            "uf": m["microrregiao"]["mesorregiao"]["UF"]["sigla"],
            "uf_id": m["microrregiao"]["mesorregiao"]["UF"]["id"],
        }
        for m in r.json()
    ]
    path = RAW / "ibge_municipios.json"
    path.write_text(json.dumps(municipios, ensure_ascii=False, indent=2))
    print(f"Municípios: {len(municipios)} → {path}")
    return municipios


def fetch_municipios_centroides() -> list[dict]:
    """Busca centróides via API de malhas do IBGE (v3)."""
    r = requests.get(
        "https://servicodados.ibge.gov.br/api/v3/malhas/municipios"
        "?formato=application/json&qualidade=minima",
        timeout=120,
    )
    r.raise_for_status()
    features = r.json()["features"]
    centroides = []
    for f in features:
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        # Centróide simples: média dos pontos do polígono externo
        if f["geometry"]["type"] == "Polygon":
            pts = coords[0]
        else:  # MultiPolygon
            pts = coords[0][0]
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        centroides.append({"id": props["codarea"], "lat": lat, "lon": lon})

    import pandas as pd
    df_mun = pd.read_json(RAW / "ibge_municipios.json")
    df_cent = pd.DataFrame(centroides)
    df_cent["id"] = df_cent["id"].astype(str).str[:7].astype(int)
    df = df_mun.merge(df_cent, on="id", how="left")

    proc = Path(__file__).parents[2] / "data" / "processed"
    proc.mkdir(exist_ok=True)
    out = proc / "municipios_centroides.csv"
    df.to_csv(out, index=False)
    print(f"Centróides: {len(df)} → {out}")
    return df.to_dict("records")


if __name__ == "__main__":
    fetch_estados()
    fetch_municipios()
    fetch_municipios_centroides()
