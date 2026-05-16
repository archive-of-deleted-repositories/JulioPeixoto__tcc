/**
 * Estruturas e helpers para avaliação RAGAS.
 *
 * A avaliação em si roda via Python (ragas lib).
 * Este módulo exporta o dataset de perguntas e gera os arquivos
 * necessários para o script Python de avaliação.
 */

import { extrairEntidades } from "../pipeline/entityExtractor.ts";
import { recuperarSubgrafo } from "../pipeline/graphRetriever.ts";
import { construirContexto } from "../pipeline/contextBuilder.ts";
import { consultarVectorRag } from "../baseline/vectorRag.ts";

export interface AmostraRagas {
  question: string;
  answer: string;
  contexts: string[];
  ground_truth: string;
}

export interface ResultadoAvaliacao {
  pergunta: string;
  resposta_graphrag: string;
  resposta_vectorrag: string;
  contexto_graphrag: string;
  entidades: Record<string, unknown>;
}

export async function gerarDatasetAvaliacao(
  perguntas: Array<{ pergunta: string; gabarito: string }>
): Promise<ResultadoAvaliacao[]> {
  const resultados: ResultadoAvaliacao[] = [];

  for (const { pergunta, gabarito } of perguntas) {
    console.log(`Avaliando: ${pergunta.slice(0, 60)}...`);

    const entidades = await extrairEntidades(pergunta);
    const subgrafos = await recuperarSubgrafo(entidades);
    const contexto = construirContexto(subgrafos);

    // GraphRAG: coleta resposta completa (sem streaming para avaliação)
    const { generateText } = await import("ai");
    const { createAnthropic } = await import("@ai-sdk/anthropic");
    const anthropic = createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

    const { text: respostaGraphrag } = await generateText({
      model: anthropic("claude-sonnet-4-6"),
      messages: [
        {
          role: "user",
          content: `Contexto:\n${contexto}\n\nPergunta: ${pergunta}`,
        },
      ],
    });

    // Vector RAG baseline
    const respostaVectorRag = await consultarVectorRag(pergunta);

    resultados.push({
      pergunta,
      resposta_graphrag: respostaGraphrag,
      resposta_vectorrag: respostaVectorRag,
      contexto_graphrag: contexto,
      entidades: entidades as Record<string, unknown>,
    });
  }

  return resultados;
}

// Perguntas de avaliação com gabaritos baseados nos dados reais
export const PERGUNTAS_AVALIACAO = [
  {
    pergunta: "Quais municípios do Rio Grande do Sul tiveram mais enchentes entre 2020 e 2024?",
    gabarito: "Resposta deve listar municípios gaúchos com maior frequência de eventos de enchente.",
  },
  {
    pergunta: "Houve eventos de calor extremo em Mato Grosso em 2023?",
    gabarito: "Resposta deve mencionar municípios do MT com TEM_MAX > 40°C em 2023.",
  },
  {
    pergunta: "Quais estados brasileiros registraram mais deslizamentos nos últimos 5 anos?",
    gabarito: "Deve incluir SP, RJ, SC como estados com histórico relevante de deslizamentos.",
  },
  {
    pergunta: "Em quais meses o fenômeno de geada é mais frequente no Sul do Brasil?",
    gabarito: "Deve mencionar inverno (junho-agosto) e estados RS, SC, PR.",
  },
  {
    pergunta: "Qual foi a precipitação mais extrema registrada em São Paulo nos últimos 10 anos?",
    gabarito: "Deve mencionar evento com CHUVA > 100mm/dia em município de SP.",
  },
] as const;
