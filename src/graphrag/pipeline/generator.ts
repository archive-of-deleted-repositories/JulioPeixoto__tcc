import { createAnthropic } from "@ai-sdk/anthropic";
import { streamText } from "ai";

const anthropic = createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const SYSTEM = `Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda perguntas em linguagem acessível usando APENAS as informações do contexto fornecido.
Cite os municípios, tipos de evento e datas quando disponíveis.
Se o contexto não contiver informações suficientes para responder, diga explicitamente.
Nunca invente dados que não estejam no contexto.`;

export function gerarResposta(pergunta: string, contexto: string) {
  return streamText({
    model: anthropic("claude-sonnet-4-6"),
    system: SYSTEM,
    messages: [
      {
        role: "user",
        content: `Contexto do grafo de conhecimento climático:\n\n${contexto}\n\nPergunta: ${pergunta}`,
      },
    ],
  });
}
