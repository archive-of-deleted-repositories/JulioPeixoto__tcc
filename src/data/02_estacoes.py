"""Baixa estações INMET e vincula cada uma ao município mais próximo via KDTree."""

import json
import numpy as np
import pandas as pd
import requests
from pathlib import Path
from scipy.spatial import KDTree

RAW = Path(__file__).parents[2] / "data" / "raw"
PROCESSED = Path(__file__).parents[2] / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

INMET_BASE = "https://apitempo.inmet.gov.br"


def fetch_estacoes(tipo: str) -> list[dict]:
    """tipo: 'T' automáticas, 'M' convencionais."""
    r = requests.get(f"{INMET_BASE}/estacoes/{tipo}", timeout=30)
    r.raise_for_status()
    return r.json()


def link_municipio(estacoes: list[dict], municipios: pd.DataFrame) -> list[dict]:
    mun_validos = municipios.dropna(subset=["lat", "lon"])
    coords = mun_validos[["lat", "lon"]].values
    tree = KDTree(coords)

    est_coords = np.array(
        [[float(e["VL_LATITUDE"]), float(e["VL_LONGITUDE"])] for e in estacoes]
    )
    _, idxs = tree.query(est_coords)

    for e, idx in zip(estacoes, idxs):
        row = mun_validos.iloc[idx]
        e["municipio_id"] = int(row["id"])
        e["municipio_nome"] = row["nome"]
        e["municipio_uf"] = row["uf"]
    return estacoes


if __name__ == "__main__":
    centroides_path = PROCESSED / "municipios_centroides.csv"
    if not centroides_path.exists():
        raise SystemExit("Execute 01_ibge.py primeiro (gera municipios_centroides.csv).")

    municipios = pd.read_csv(centroides_path)

    print("Baixando estações automáticas...")
    auto = fetch_estacoes("T")
    (RAW / "estacoes_automaticas.json").write_text(
        json.dumps(auto, ensure_ascii=False, indent=2)
    )
    print(f"  {len(auto)} estações automáticas")

    print("Baixando estações convencionais...")
    conv = fetch_estacoes("M")
    (RAW / "estacoes_convencionais.json").write_text(
        json.dumps(conv, ensure_ascii=False, indent=2)
    )
    print(f"  {len(conv)} estações convencionais")

    print("Vinculando a municípios...")
    todas = link_municipio(auto + conv, municipios)

    out = PROCESSED / "estacoes_com_municipio.json"
    out.write_text(json.dumps(todas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {len(todas)} estacoes vinculadas -> {out}")
