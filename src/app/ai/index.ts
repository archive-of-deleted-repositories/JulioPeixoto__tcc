import { createOpenAI } from "@ai-sdk/openai";
import { ChatOpenAI } from "@langchain/openai";
import { OpenAIEmbeddings } from "@langchain/openai";

const client = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });

const MODELO_RAPIDO     = process.env.MODELO_RAPIDO     ?? "gpt-4o-mini";
const MODELO_PRINCIPAL  = process.env.MODELO_PRINCIPAL  ?? "gpt-4o";
const MODELO_EMBEDDINGS = process.env.MODELO_EMBEDDINGS ?? "text-embedding-3-small";

// Modelos Vercel AI SDK — use em generateObject / generateText / streamText
export const modelos = {
  rapido:    client(MODELO_RAPIDO),
  principal: client(MODELO_PRINCIPAL),
} as const;

// Embeddings OpenAI — use em vector stores LangChain
export function criarEmbeddings(): OpenAIEmbeddings {
  return new OpenAIEmbeddings({
    apiKey: process.env.OPENAI_API_KEY!,
    model: MODELO_EMBEDDINGS,
  });
}

// LLM LangChain — use em chains (RetrievalChain, etc.)
export function criarLangChainLLM(): ChatOpenAI {
  return new ChatOpenAI({
    apiKey: process.env.OPENAI_API_KEY,
    model: MODELO_PRINCIPAL,
  });
}
