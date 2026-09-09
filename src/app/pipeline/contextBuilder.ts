import type { SubgrafoResult } from "./graphRetriever.ts";

/**
 * Rótulos das seções. O nome da query sozinho ("comparativoTemporalMunicipio")
 * não diz ao gerador o que a seção significa; um cabeçalho em português evita
 * que ele trate uma contagem agregada como se fosse uma lista de eventos.
 */
const TITULOS: Record<string, string> = {
  comparativoTemporalMunicipio: "CONTAGEM POR ANO (município) — use estes números para comparar épocas",
  comparativoTemporalEstado: "CONTAGEM POR ANO (estado) — use estes números para comparar épocas",
  coberturaEstacoesPorAno: "COBERTURA DE ESTAÇÕES POR ANO — se o número de estações mudou, a variação pode ser de cobertura e não do fenômeno",
  contagemPorMunicipio: "TOTAIS POR TIPO (município)",
  contagemPorEstado: "TOTAIS POR TIPO (estado)",
  sazonalidadePorEstado: "DISTRIBUIÇÃO POR MÊS",
  extremoPorEstado: "VALORES MAIS EXTREMOS (estação e município de registro)",
  municipiosMaisEventosPorEstado: "RANKING DE MUNICÍPIOS",
  municipiosComMaisEventos: "RANKING NACIONAL DE MUNICÍPIOS",
  eventosPorMunicipio: "EVENTOS INDIVIDUAIS (município)",
  eventosPorEstado: "EVENTOS INDIVIDUAIS (estado)",
};

const MESES = [
  "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

/** Ordem de exibição das colunas; o resto entra depois, na ordem original. */
const ORDEM = [
  "ano", "mes", "municipio", "uf", "estacao", "estacao_nome", "tipo", "fenomeno",
  "total", "n_municipios", "n_estacoes", "valor", "valor_medio", "valor_max", "data",
];

const NOMES: Record<string, string> = {
  ano: "ano", mes: "mês", municipio: "município", uf: "UF",
  estacao: "estação", estacao_nome: "nome da estação", tipo: "tipo",
  fenomeno: "fenômeno", total: "total de registros", n_municipios: "municípios",
  n_estacoes: "estações", valor: "valor", valor_medio: "valor médio",
  valor_max: "valor máximo", data: "data", estacoes: "estações", descricao: "descrição",
  fonte: "fonte",
};

function formatarValor(chave: string, valor: unknown): string {
  if (valor == null) return "";
  if (chave === "mes" && typeof valor === "number") return MESES[valor] ?? String(valor);
  if (Array.isArray(valor)) return valor.join(", ");
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}

function formatarRegistro(record: Record<string, unknown>): string {
  const chaves = [
    ...ORDEM.filter((k) => k in record),
    ...Object.keys(record).filter((k) => !ORDEM.includes(k)),
  ];
  return chaves
    .map((k) => [k, formatarValor(k, record[k])] as const)
    .filter(([, v]) => v !== "")
    .map(([k, v]) => `${NOMES[k] ?? k}: ${v}`)
    .join(" | ");
}

export function construirContexto(subgrafos: SubgrafoResult[]): string {
  if (subgrafos.length === 0) {
    return (
      "Nenhum dado encontrado no grafo para os critérios fornecidos. " +
      "Isso significa que a base não contém registros para essa combinação de " +
      "local, fenômeno e período — responda declarando a ausência de dados, " +
      "sem estimar números."
    );
  }

  return subgrafos
    .map((sg) => {
      const titulo = TITULOS[sg.queryUsada] ?? sg.queryUsada;
      const linhas = sg.records.map(formatarRegistro).filter(Boolean);
      return `[${titulo}]\n${linhas.join("\n")}`;
    })
    .join("\n\n");
}
