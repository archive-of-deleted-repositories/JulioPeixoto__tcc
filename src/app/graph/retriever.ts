import { runQuery } from "./client.ts";
import { QUERIES } from "./queries.ts";
import type { Entidades } from "../pipeline/entityExtractor.ts";

export interface SubgrafoResult {
  records: Record<string, unknown>[];
  queryUsada: string;
}

export interface BuscarSubgrafoResult {
  subgrafos: SubgrafoResult[];
  entidadesEfetivas: Entidades;
}

export interface Janela {
  inicio: string;
  fim: string;
  rotulo: string;
}

/**
 * Janela padrão quando a pergunta não traz recorte temporal.
 *
 * Antes isto era `hoje - 2 anos`, ancorado em `new Date()`. Como a base termina
 * em 2024-12-31, qualquer pergunta sem data caía numa faixa quase vazia à medida
 * que o relógio avançava — os eventos recuperados ficavam presos aos últimos
 * meses de 2024. Agora a janela é derivada da própria extensão dos dados.
 */
let coberturaCache: { inicio: string; fim: string } | null = null;

async function coberturaDoGrafo(): Promise<{ inicio: string; fim: string }> {
  if (coberturaCache) return coberturaCache;
  try {
    const [row] = await runQuery(
      `MATCH (e:Evento) WHERE e.data IS NOT NULL
       RETURN toString(min(e.data)) AS inicio, toString(max(e.data)) AS fim`,
      {}
    );
    const inicio = (row?.inicio as string) ?? "2015-01-01";
    const fim = (row?.fim as string) ?? "2024-12-31";
    coberturaCache = { inicio, fim };
  } catch {
    coberturaCache = { inicio: "2015-01-01", fim: "2024-12-31" };
  }
  return coberturaCache;
}

async function resolverJanelas(entidades: Entidades): Promise<Janela[]> {
  if (entidades.periodos.length > 0) return entidades.periodos;
  const { inicio, fim } = await coberturaDoGrafo();
  return [{ inicio, fim, rotulo: "toda a série" }];
}

function anosDe(janelas: Janela[]): number[] {
  const anos = new Set<number>();
  for (const j of janelas) {
    const a1 = Number(j.inicio.slice(0, 4));
    const a2 = Number(j.fim.slice(0, 4));
    for (let a = a1; a <= a2; a++) anos.add(a);
  }
  return [...anos].sort((x, y) => x - y);
}

function push(destino: SubgrafoResult[], queryUsada: string, records: Record<string, unknown>[]) {
  if (records.length > 0) destino.push({ records, queryUsada });
}

/**
 * Insere linhas com total 0 para os anos sem nenhum registro.
 *
 * Um `count` no Cypher só devolve linha onde existe evento: perguntando
 * "2020 ou 2022?" para um município que teve 227 em 2020 e nada em 2022, o
 * contexto vinha só com 2020. O gerador não tem como afirmar "zero em 2022" a
 * partir de uma linha ausente — a ausência precisa ser dita.
 */
function completarAnosVazios(
  records: Record<string, unknown>[],
  anos: number[],
  chaves: string[]
): Record<string, unknown>[] {
  if (records.length === 0) return records;

  const chaveDe = (r: Record<string, unknown>) =>
    chaves.map((k) => String(r[k] ?? "")).join("|");

  // Um "modelo" por combinação (município, tipo) — dele saem as linhas zeradas.
  const modelos = new Map(records.map((r) => [chaveDe(r), r]));

  const completos = [...records];
  for (const modelo of modelos.values()) {
    for (const ano of anos) {
      const existe = records.some((r) => r.ano === ano && chaveDe(r) === chaveDe(modelo));
      if (existe) continue;
      const vazio: Record<string, unknown> = { ...modelo, ano, total: 0 };
      delete vazio.valor_medio;
      delete vazio.valor_max;
      completos.push(vazio);
    }
  }

  return completos.sort((a, b) =>
    chaveDe(a) === chaveDe(b)
      ? Number(a.ano) - Number(b.ano)
      : chaveDe(a).localeCompare(chaveDe(b))
  );
}

const NOME_ESTADO_PARA_UF: Record<string, string> = {
  acre: "AC", alagoas: "AL", amapa: "AP", amazonas: "AM", bahia: "BA", ceara: "CE",
  "distrito federal": "DF", "espirito santo": "ES", goias: "GO", maranhao: "MA",
  "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG", para: "PA",
  paraiba: "PB", parana: "PR", pernambuco: "PE", piaui: "PI", "rio de janeiro": "RJ",
  "rio grande do norte": "RN", "rio grande do sul": "RS", rondonia: "RO", roraima: "RR",
  "santa catarina": "SC", "sao paulo": "SP", sergipe: "SE", tocantins: "TO",
};

function semAcento(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/**
 * Descarta de `municipios` os nomes que na verdade são estados já cobertos por
 * `estados`. O extrator às vezes devolve "São Paulo" ou "Bahia" como município;
 * sem esse filtro a busca casaria a CIDADE de São Paulo e o contexto traria os
 * dados errados para uma pergunta sobre o ESTADO.
 */
function municipiosReais(ent: Entidades): string[] {
  const ufs = new Set(ent.estados.map((s) => s.toUpperCase()));
  return ent.municipios.filter((m) => {
    const uf = NOME_ESTADO_PARA_UF[semAcento(m)];
    return !(uf && ufs.has(uf));
  });
}

export async function buscarSubgrafo(entidades: Entidades): Promise<BuscarSubgrafoResult> {
  const resultados: SubgrafoResult[] = [];
  const janelas = await resolverJanelas(entidades);
  const ent: Entidades = { ...entidades, periodos: janelas };

  const tipo = ent.tipos_evento[0] ?? null;
  const anos = anosDe(janelas);
  const comparaEpocas = ent.comparativa || janelas.length > 1 || ent.intencao === "comp_temporal";

  // Recorte temporal agregado para as queries de janela única: da menor data à maior.
  const janelaAmpla = {
    data_inicio: janelas.reduce((a, j) => (j.inicio < a ? j.inicio : a), janelas[0]!.inicio),
    data_fim: janelas.reduce((a, j) => (j.fim > a ? j.fim : a), janelas[0]!.fim),
  };

  // ── Municípios mencionados ────────────────────────────────────────────────
  for (const municipio of municipiosReais(ent)) {
    if (comparaEpocas) {
      // Uma linha por (município, tipo, ano): o contraste fica explícito no
      // contexto, sem depender de o LLM recontar eventos individuais.
      const [comparativo, cobertura] = await Promise.all([
        runQuery(QUERIES.comparativoTemporalMunicipio, { nome: municipio, tipo, anos }),
        runQuery(QUERIES.coberturaEstacoesPorAno, { nome: municipio, anos }),
      ]);
      push(
        resultados,
        "comparativoTemporalMunicipio",
        completarAnosVazios(comparativo, anos, ["municipio", "tipo"])
      );
      push(resultados, "coberturaEstacoesPorAno", cobertura);
    } else {
      const [eventos, contagem] = await Promise.all([
        runQuery(QUERIES.eventosPorMunicipio, { nome: municipio, tipo, ...janelaAmpla }),
        runQuery(QUERIES.contagemPorMunicipio, { nome: municipio, tipo, ...janelaAmpla }),
      ]);
      push(resultados, "contagemPorMunicipio", contagem);
      push(resultados, "eventosPorMunicipio", eventos);
    }
  }

  // Quando a pergunta é sobre um município, a UF costuma ser só qualificador
  // ("em Bom Jesus (PI)"). Puxar também todos os eventos do estado inchava o
  // contexto — 13 mil caracteres para uma pergunta de sim/não — e derrubava a
  // precisão. Se o município já respondeu, o estado não entra.
  const municipioResolvido = resultados.length > 0;

  // ── Estados mencionados ───────────────────────────────────────────────────
  for (const sigla of municipioResolvido ? [] : ent.estados) {
    const uf = sigla.toUpperCase();
    const params = { sigla: uf, tipo, ...janelaAmpla };

    if (comparaEpocas) {
      const comparativo = await runQuery(QUERIES.comparativoTemporalEstado, {
        sigla: uf, tipo, anos,
      });
      push(
        resultados,
        "comparativoTemporalEstado",
        completarAnosVazios(comparativo, anos, ["uf", "tipo"])
      );
      continue;
    }

    // As agregações pequenas entram SEMPRE (≈35 linhas somadas), sem depender
    // de `intencao`. A classificação por LLM se mostrou instável — a mesma
    // pergunta de "qual estação registrou o extremo" foi rotulada ora "extremo"
    // ora "factual", e no segundo caso o contexto saía sem a seção que continha
    // a resposta. Recuperar as quatro agregações é barato e remove a
    // dependência de um classificador que erra.
    const [contagem, ranking, extremos, meses] = await Promise.all([
      runQuery(QUERIES.contagemPorEstado, params),
      runQuery(QUERIES.municipiosMaisEventosPorEstado, params),
      runQuery(QUERIES.extremoPorEstado, params),
      runQuery(QUERIES.sazonalidadePorEstado, params),
    ]);
    push(resultados, "contagemPorEstado", contagem);
    push(resultados, "municipiosMaisEventosPorEstado", ranking);
    push(resultados, "extremoPorEstado", extremos);
    push(resultados, "sazonalidadePorEstado", meses.slice(0, 12));

    // A lista de eventos individuais é o que realmente inchava o contexto
    // (50 linhas, ~5 KB). Só entra quando a pergunta pede a listagem.
    if (ent.intencao === "listagem") {
      push(resultados, "eventosPorEstado", await runQuery(QUERIES.eventosPorEstado, params));
    }
  }

  // ── Fallback: ranking nacional ────────────────────────────────────────────
  // Só quando a pergunta NÃO nomeou lugar nenhum. Se o usuário perguntou sobre
  // o Amazonas e não há registros, a resposta é a ausência — devolver o ranking
  // de outros estados responde a uma pergunta que ninguém fez e ainda convida à
  // alucinação.
  const nomeouLugar = ent.estados.length > 0 || municipiosReais(ent).length > 0;
  if (resultados.length === 0 && !nomeouLugar && ent.tipos_evento.length > 0) {
    push(
      resultados,
      "municipiosComMaisEventos",
      await runQuery(QUERIES.municipiosComMaisEventos, {
        fenomeno: ent.tipos_evento[0],
        ...janelaAmpla,
      })
    );
  }

  return { subgrafos: resultados, entidadesEfetivas: ent };
}
