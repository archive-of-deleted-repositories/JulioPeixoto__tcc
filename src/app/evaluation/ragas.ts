/**
 * Estruturas e helpers para avaliação RAGAS.
 *
 * A avaliação em si roda via Python (ragas lib).
 * Este módulo exporta o dataset de perguntas e gera os arquivos
 * necessários para o script Python de avaliação.
 */

import { generateText } from "ai";
import { extrairEntidades } from "../pipeline/entityExtractor.ts";
import { recuperarSubgrafo } from "../pipeline/graphRetriever.ts";
import { construirContexto } from "../pipeline/contextBuilder.ts";
import { consultarVectorRag } from "../baseline/vectorRag.ts";
import { modelos } from "../ai/index.ts";

export interface AmostraRagas {
  question: string;
  answer: string;
  contexts: string[];
  ground_truth: string;
}

export interface ResultadoAvaliacao {
  pergunta: string;
  gabarito: string;
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

export async function gerarDatasetAvaliacao(
  perguntas: Array<{ pergunta: string; gabarito: string }>
): Promise<ResultadoAvaliacao[]> {
  const resultados: ResultadoAvaliacao[] = [];

  for (const { pergunta, gabarito } of perguntas) {
    console.log(`Avaliando: ${pergunta.slice(0, 60)}...`);

    const entidades = await extrairEntidades(pergunta);
    const { subgrafos } = await recuperarSubgrafo(entidades);
    const contexto = construirContexto(subgrafos);

    const [respostaNoRag, respostaVectorRag, { text: respostaGraphrag }] = await Promise.all([
      gerarRespostaNoRag(pergunta),
      consultarVectorRag(pergunta),
      generateText({
        model: modelos.principal,
        system: `Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda usando APENAS as informações do contexto fornecido. Nunca invente dados.`,
        messages: [
          {
            role: "user",
            content: `Contexto do grafo de conhecimento:\n\n${contexto}\n\nPergunta: ${pergunta}`,
          },
        ],
      }),
    ]);

    resultados.push({
      pergunta,
      gabarito,
      resposta_norag: respostaNoRag,
      resposta_vectorrag: respostaVectorRag,
      resposta_graphrag: respostaGraphrag,
      contexto_graphrag: contexto,
      contexto_vectorrag: "",
      entidades: entidades as Record<string, unknown>,
    });
  }

  return resultados;
}

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
