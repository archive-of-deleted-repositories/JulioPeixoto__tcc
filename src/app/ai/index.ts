import { createAnthropic } from "@ai-sdk/anthropic";
import { ChatAnthropic } from "@langchain/anthropic";
import { VoyageEmbeddings } from "@langchain/community/embeddings/voyage";

const client = createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const MODELO_RAPIDO     = process.env.MODELO_RAPIDO     ?? "claude-haiku-4-5-20251001";
const MODELO_PRINCIPAL  = process.env.MODELO_PRINCIPAL  ?? "claude-sonnet-4-6";
const MODELO_EMBEDDINGS = process.env.MODELO_EMBEDDINGS ?? "voyage-3";

// Modelos Vercel AI SDK — use em generateObject / generateText / streamText
export const modelos = {
  rapido:    client(MODELO_RAPIDO),
  principal: client(MODELO_PRINCIPAL),
} as const;

// Embeddings Voyage AI — use em vector stores LangChain
export function criarEmbeddings(): VoyageEmbeddings {
  return new VoyageEmbeddings({
    apiKey: process.env.VOYAGE_API_KEY ?? process.env.ANTHROPIC_API_KEY!,
    modelName: MODELO_EMBEDDINGS,
  });
}

// LLM LangChain — use em chains (RetrievalChain, etc.)
export function criarLangChainLLM(): ChatAnthropic {
  return new ChatAnthropic({
    apiKey: process.env.ANTHROPIC_API_KEY,
    model: MODELO_PRINCIPAL,
  });
}
