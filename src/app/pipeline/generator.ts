import { streamText } from "ai";
import { modelos } from "../ai/index.ts";

const SYSTEM = `Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda perguntas em linguagem acessível usando APENAS as informações do contexto fornecido.
Cite os municípios, tipos de evento e datas quando disponíveis.
Se o contexto não contiver informações suficientes para responder, diga explicitamente.
Nunca invente dados que não estejam no contexto.`;

export function gerarResposta(pergunta: string, contexto: string) {
  return streamText({
    model: modelos.principal,
    system: SYSTEM,
    messages: [
      {
        role: "user",
        content: `Contexto do grafo de conhecimento climático:\n\n${contexto}\n\nPergunta: ${pergunta}`,
      },
    ],
  });
}
