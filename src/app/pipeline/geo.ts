/**
 * Normalização geográfica compartilhada entre os modos de recuperação.
 *
 * O extrator de entidades frequentemente devolve o nome de um estado dentro de
 * `municipios` — "São Paulo", "Bahia", "Mato Grosso" — mesmo quando a pergunta
 * é sobre o estado. Sem tratar isso, um filtro por município casa a CIDADE de
 * São Paulo numa pergunta sobre o ESTADO, ou não casa nada (não existe
 * município chamado "Bahia") e a recuperação volta vazia.
 *
 * Este módulo vive fora de `graph/` porque os DOIS baselines precisam dele: o
 * retriever do grafo e o retriever vetorial com pré-filtragem. Aplicar a
 * normalização só ao GraphRAG penalizaria o baseline por um defeito da extração
 * de entidades, e não por sua arquitetura de recuperação — exatamente o tipo de
 * assimetria que invalida uma comparação.
 */

import type { Entidades } from "./entityExtractor.ts";

export const NOME_ESTADO_PARA_UF: Record<string, string> = {
  acre: "AC", alagoas: "AL", amapa: "AP", amazonas: "AM", bahia: "BA", ceara: "CE",
  "distrito federal": "DF", "espirito santo": "ES", goias: "GO", maranhao: "MA",
  "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG", para: "PA",
  paraiba: "PB", parana: "PR", pernambuco: "PE", piaui: "PI", "rio de janeiro": "RJ",
  "rio grande do norte": "RN", "rio grande do sul": "RS", rondonia: "RO", roraima: "RR",
  "santa catarina": "SC", "sao paulo": "SP", sergipe: "SE", tocantins: "TO",
};

export function semAcento(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/**
 * Municípios de `ent` que não são, na verdade, nomes de estados já cobertos por
 * `ent.estados`.
 */
export function municipiosReais(ent: Entidades): string[] {
  const ufs = new Set(ent.estados.map((s) => s.toUpperCase()));
  return ent.municipios.filter((m) => {
    const uf = NOME_ESTADO_PARA_UF[semAcento(m)];
    return !(uf && ufs.has(uf));
  });
}

/**
 * UFs de `ent`, acrescidas das que aparecem em `municipios` como nome de estado
 * sem que a sigla tenha sido extraída (ex.: municipios=["Bahia"], estados=[]).
 */
export function ufsReais(ent: Entidades): string[] {
  const ufs = new Set(ent.estados.map((s) => s.toUpperCase()));
  for (const m of ent.municipios) {
    const uf = NOME_ESTADO_PARA_UF[semAcento(m)];
    if (uf) ufs.add(uf);
  }
  return [...ufs];
}
