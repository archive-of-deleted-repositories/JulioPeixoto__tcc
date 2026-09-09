/**
 * Estruturas e helpers para avaliação RAGAS.
 *
 * A avaliação em si roda via Python (ragas lib).
 * Este módulo exporta o dataset de perguntas e gera os arquivos
 * necessários para o script Python de avaliação.
 *
 * Gabaritos: carregados de data/evaluation/gabaritos_derivados.json se existir
 * (gerado por src/evaluation/derive_gabaritos.py), senão usa os padrões hardcoded.
 */

import { existsSync, readFileSync } from "node:fs";
import { generateText } from "ai";
import { extrairEntidades } from "../pipeline/entityExtractor.ts";
import { recuperarSubgrafo } from "../pipeline/graphRetriever.ts";
import { construirContexto } from "../pipeline/contextBuilder.ts";
import { consultarVectorRag } from "../baseline/vectorRag.ts";
import { SYSTEM_RAG } from "../baseline/prompt.ts";
import { modelos } from "../ai/index.ts";

export interface AmostraRagas {
  question: string;
  answer: string;
  contexts: string[];
  ground_truth: string;
}

export interface PerguntaBenchmark {
  id?: string;
  categoria?: string;
  pergunta: string;
  gabarito: string;
  fatos_chave?: string[];
}

export interface ResultadoAvaliacao {
  id: string;
  categoria: string;
  pergunta: string;
  gabarito: string;
  fatos_chave: string[];
  resposta_norag: string;
  resposta_vectorrag: string;
  resposta_graphrag: string;
  contexto_graphrag: string;
  contexto_vectorrag: string;
  entidades: Record<string, unknown>;
}

const SYSTEM_NO_RAG = `Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda com base no seu conhecimento geral. Se não tiver certeza, diga explicitamente.`;

async function gerarRespostaNoRag(pergunta: string): Promise<string> {
  const { text } = await generateText({
    model: modelos.principal,
    system: SYSTEM_NO_RAG,
    messages: [{ role: "user", content: pergunta }],
  });
  return text;
}

// Mesmo prompt usado pelo VectorRAG, para que a única diferença entre os dois
// modos seja a recuperação. Ver src/app/baseline/prompt.ts.
const SYSTEM_COM_CONTEXTO = SYSTEM_RAG;

/**
 * Backoff exponencial começando em 2s (2, 4, 8, 16, 32s).
 *
 * Com 1s de base e 3 tentativas, duas gerações da primeira rodada estouraram o
 * rate limit da OpenAI e entraram no dataset como "[falha na geração]" — o que
 * contamina as métricas com uma falha de infraestrutura em vez de medir o
 * pipeline. Uma resposta faltando é pior que uma rodada mais lenta.
 */
async function comRetry<T>(rotulo: string, fn: () => Promise<T>, fallback: T, tentativas = 5): Promise<T> {
  for (let i = 1; i <= tentativas; i++) {
    try {
      return await fn();
    } catch (err) {
      const msg = (err as Error)?.message ?? String(err);
      if (i === tentativas) {
        console.warn(`  ${rotulo} falhou após ${tentativas} tentativas: ${msg}`);
        return fallback;
      }
      await new Promise((r) => setTimeout(r, 2000 * 2 ** (i - 1)));
    }
  }
  return fallback;
}

async function avaliarUma(q: PerguntaBenchmark, idx: number, total: number): Promise<ResultadoAvaliacao> {
  const { pergunta, gabarito } = q;
  console.log(`[${idx}/${total}] ${q.id ?? ""} ${pergunta.slice(0, 70)}...`);

  const entidades = await comRetry("extração", () => extrairEntidades(pergunta), {
    municipios: [], estados: [], tipos_evento: [], periodos: [], comparativa: false, intencao: "factual",
  } as Awaited<ReturnType<typeof extrairEntidades>>);

  const { subgrafos } = await comRetry("grafo", () => recuperarSubgrafo(entidades), { subgrafos: [], entidadesEfetivas: entidades });
  const contexto = construirContexto(subgrafos);

  const [respostaNoRag, vectorResult, respostaGraphrag] = await Promise.all([
    comRetry("no-rag", () => gerarRespostaNoRag(pergunta), "[falha na geração]"),
    comRetry(
      "vector-rag",
      () => consultarVectorRag(pergunta),
      { resposta: "[VectorRAG indisponível — índice vetorial não criado]", contexto: "" }
    ),
    comRetry(
      "graph-rag",
      async () =>
        (
          await generateText({
            model: modelos.principal,
            system: SYSTEM_COM_CONTEXTO,
            messages: [
              {
                role: "user",
                content: `Contexto do grafo de conhecimento:\n\n${contexto}\n\nPergunta: ${pergunta}`,
              },
            ],
          })
        ).text,
      "[falha na geração]"
    ),
  ]);

  return {
    id: q.id ?? `Q${idx}`,
    categoria: q.categoria ?? "legado",
    pergunta,
    gabarito,
    fatos_chave: q.fatos_chave ?? [],
    resposta_norag: respostaNoRag,
    resposta_vectorrag: vectorResult.resposta,
    resposta_graphrag: respostaGraphrag,
    contexto_graphrag: contexto,
    contexto_vectorrag: vectorResult.contexto,
    entidades: entidades as unknown as Record<string, unknown>,
  };
}

/** Quantas perguntas rodam em paralelo. Cada uma dispara 3 gerações simultâneas. */
const CONCORRENCIA = 3;

export async function gerarDatasetAvaliacao(
  perguntas: PerguntaBenchmark[]
): Promise<ResultadoAvaliacao[]> {
  const resultados: ResultadoAvaliacao[] = new Array(perguntas.length);
  let proximo = 0;

  async function worker() {
    while (proximo < perguntas.length) {
      const i = proximo++;
      resultados[i] = await avaliarUma(perguntas[i]!, i + 1, perguntas.length);
    }
  }

  await Promise.all(Array.from({ length: Math.min(CONCORRENCIA, perguntas.length) }, worker));
  return resultados;
}

const PERGUNTAS_PADRAO = [
  {
    pergunta: "Quais municípios do Rio Grande do Sul registraram mais episódios de precipitação extrema entre 2020 e 2024?",
    gabarito: "A resposta deve listar municípios gaúchos com maior frequência de precipitação diária acima de 50 mm no período. Municípios da Serra Gaúcha e litoral costumam liderar esses rankings.",
  },
  {
    pergunta: "Houve registros de calor extremo (temperatura máxima acima de 40°C) em Mato Grosso em 2023?",
    gabarito: "Sim. Estações meteorológicas do Mato Grosso registraram temperaturas máximas acima de 40°C em 2023, especialmente no segundo semestre (agosto a novembro), período de seca e baixa umidade no cerrado.",
  },
  {
    pergunta: "Quais municípios de São Paulo tiveram chuva muito forte (acima de 100 mm em um dia) em 2022?",
    gabarito: "Municípios do litoral paulista (Baixada Santista, Vale do Ribeira) e da Serra da Mantiqueira registram historicamente os maiores volumes diários de precipitação no estado de SP.",
  },
  {
    pergunta: "Em quais meses ocorrem mais registros de frio extremo (temperatura mínima abaixo de 0°C) no Sul do Brasil?",
    gabarito: "Os registros de frio extremo e geada concentram-se entre junho e agosto, especialmente em municípios serranos do Rio Grande do Sul e Santa Catarina, durante o inverno austral.",
  },
  {
    pergunta: "Quais estados brasileiros registraram mais eventos de baixa umidade crítica (abaixo de 12%) nos últimos 3 anos?",
    gabarito: "Estados do Centro-Oeste e Sudeste (Mato Grosso, Goiás, Minas Gerais, São Paulo) costumam registrar os maiores índices de baixa umidade relativa no período de estiagem (maio a outubro).",
  },
];

function caminhoDados(arquivo: string): string {
  return new URL(`../../../data/evaluation/${arquivo}`, import.meta.url).pathname.replace(
    /^\/([A-Za-z]:)/,
    "$1"
  );
}

/**
 * Ordem de preferência:
 *   1. benchmark.json          — 70 perguntas em 7 categorias, gabaritos derivados
 *                                do JSONL de origem (src/evaluation/build_benchmark.py)
 *   2. gabaritos_derivados.json — conjunto legado de 5 perguntas, derivado do Neo4j
 *   3. PERGUNTAS_PADRAO         — gabaritos escritos à mão
 */
function carregarPerguntas(): PerguntaBenchmark[] {
  const bench = caminhoDados("benchmark.json");
  if (existsSync(bench)) {
    const itens = JSON.parse(readFileSync(bench, "utf-8")) as PerguntaBenchmark[];
    console.log(`Benchmark carregado: ${itens.length} perguntas de benchmark.json`);
    return itens;
  }
  const legado = caminhoDados("gabaritos_derivados.json");
  if (existsSync(legado)) {
    console.log("benchmark.json ausente — usando gabaritos_derivados.json (5 perguntas)");
    return JSON.parse(readFileSync(legado, "utf-8")) as PerguntaBenchmark[];
  }
  console.log("Usando gabaritos padrão (rode src/evaluation/build_benchmark.py)");
  return PERGUNTAS_PADRAO;
}

export const PERGUNTAS_AVALIACAO = carregarPerguntas();
