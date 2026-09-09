/**
 * Baseline VectorRAG *forte*: pré-filtragem por metadados + ranqueamento por
 * similaridade.
 *
 * Por que existe
 * ──────────────
 * O baseline ingênuo (`vectorRag.ts`) faz `asRetriever({ k: 10 })` puro: pega os
 * 10 documentos mais similares do corpus inteiro e ignora os metadados que a
 * própria indexação gravou (uf, tipo, ano, município, estação). Comparar
 * GraphRAG contra esse baseline mede, em parte, "recuperação projetada para a
 * tarefa" contra "top-k sem engenharia" — uma crítica legítima ao desenho
 * experimental.
 *
 * Este módulo arma o baseline: usa as MESMAS entidades extraídas que o GraphRAG
 * recebe (mesma chamada de extração, mesmo custo de LLM) para filtrar o corpus
 * antes de ranquear. Se o GraphRAG continuar à frente contra este baseline, o
 * resultado é bem mais forte; se não continuar, isso também é um achado.
 *
 * Filtrar depois de ranquear não serviria: `db.index.vector.queryNodes` devolve
 * o top-k global e o filtro posterior só o esvaziaria. Aqui o filtro entra
 * primeiro e a similaridade é calculada sobre o subconjunto sobrevivente, via
 * `vector.similarity.cosine`. É varredura sobre o conjunto filtrado — exato, e
 * barato porque os subconjuntos são pequenos.
 *
 * O `k` permanece 10, igual ao baseline ingênuo, para isolar o efeito do filtro.
 */

import { generateText } from "ai";
import { runQuery } from "../graph/client.ts";
import { criarEmbeddings, modelos } from "../ai/index.ts";
import { LABEL_INDEXADO } from "./vectorRag.ts";
import { SYSTEM_RAG } from "./prompt.ts";
import type { Entidades } from "../pipeline/entityExtractor.ts";
import { municipiosReais, ufsReais } from "../pipeline/geo.ts";

const K = 10;

/** Monta as cláusulas WHERE a partir das entidades extraídas. */
function construirFiltro(ent: Entidades): { where: string; params: Record<string, unknown> } {
  const clausulas: string[] = [];
  const params: Record<string, unknown> = {};

  if (ent.tipos_evento.length > 0) {
    clausulas.push("n.tipo IN $tipos");
    params.tipos = ent.tipos_evento;
  }

  // Mesma normalização geográfica do GraphRAG (ver pipeline/geo.ts): nomes de
  // estado que o extrator jogou em `municipios` viram UF, em vez de virarem um
  // filtro por município que não casa nada.
  const ufs = ufsReais(ent);
  if (ufs.length > 0) {
    clausulas.push("n.uf IN $ufs");
    params.ufs = ufs;
  }

  const municipios = municipiosReais(ent);
  if (municipios.length > 0) {
    clausulas.push(
      "any(m IN $municipios WHERE toLower(n.municipio) CONTAINS toLower(m))"
    );
    params.municipios = municipios;
  }

  // Anos derivados das janelas — cobre tanto intervalo contínuo quanto
  // épocas contrastadas, do mesmo modo que o retriever do grafo.
  const anos = new Set<number>();
  for (const p of ent.periodos) {
    const a1 = Number(p.inicio.slice(0, 4));
    const a2 = Number(p.fim.slice(0, 4));
    for (let a = a1; a <= a2; a++) anos.add(a);
  }
  if (anos.size > 0) {
    clausulas.push("n.ano IN $anos");
    params.anos = [...anos];
  }

  return {
    where: clausulas.length > 0 ? `WHERE ${clausulas.join("\n      AND ")}` : "",
    params,
  };
}

export interface ResultadoVetorial {
  resposta: string;
  contexto: string;
  filtroAplicado: boolean;
  candidatos: number;
}

export async function consultarVectorRagFiltrado(
  pergunta: string,
  entidades: Entidades
): Promise<ResultadoVetorial> {
  const { where, params } = construirFiltro(entidades);
  const embedding = await criarEmbeddings().embedQuery(pergunta);

  const cypher = `
    MATCH (n:${LABEL_INDEXADO})
    ${where}
    WITH n, vector.similarity.cosine(n.embedding, $embedding) AS score
    RETURN n.descricao AS descricao, score
    ORDER BY score DESC
    LIMIT ${K}
  `;

  let docs = await runQuery(cypher, { ...params, embedding });

  // Filtro vazio significa que nenhum documento satisfaz a combinação pedida.
  // Em vez de devolver contexto vazio (o que empurraria o gerador a inventar),
  // relaxamos para busca sem filtro — o comportamento do baseline ingênuo.
  let filtroAplicado = true;
  if (docs.length === 0 && where !== "") {
    filtroAplicado = false;
    docs = await runQuery(
      `MATCH (n:${LABEL_INDEXADO})
       WITH n, vector.similarity.cosine(n.embedding, $embedding) AS score
       RETURN n.descricao AS descricao, score
       ORDER BY score DESC LIMIT ${K}`,
      { embedding }
    );
  }

  const contexto = docs.map((d) => String(d.descricao)).join("\n");

  const { text } = await generateText({
    model: modelos.principal,
    system: SYSTEM_RAG,
    messages: [
      { role: "user", content: `Contexto:\n\n${contexto}\n\nPergunta: ${pergunta}` },
    ],
  });

  return { resposta: text, contexto, filtroAplicado, candidatos: docs.length };
}
