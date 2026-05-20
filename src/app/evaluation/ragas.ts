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

    const [respostaNoRag, vectorResult, { text: respostaGraphrag }] = await Promise.all([
      gerarRespostaNoRag(pergunta),
      consultarVectorRag(pergunta).catch((err) => {
        console.warn(`VectorRAG falhou: ${err?.message ?? err}`);
        return { resposta: "[VectorRAG indisponível — índice vetorial não criado]", contexto: "" };
      }),
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
    const respostaVectorRag = vectorResult.resposta;
    const contextoVectorRag = vectorResult.contexto;

    resultados.push({
      pergunta,
      gabarito,
      resposta_norag: respostaNoRag,
      resposta_vectorrag: respostaVectorRag,
      resposta_graphrag: respostaGraphrag,
      contexto_graphrag: contexto,
      contexto_vectorrag: contextoVectorRag,
      entidades: entidades as Record<string, unknown>,
    });
  }

  return resultados;
}

export const PERGUNTAS_AVALIACAO = [
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
] as const;
