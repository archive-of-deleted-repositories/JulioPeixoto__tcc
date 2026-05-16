/**
 * Baseline RAG vetorial usando Neo4jVectorStore do LangChain.
 * Usado para comparação com o GraphRAG via RAGAS.
 */

import { Neo4jVectorStore } from "@langchain/community/vectorstores/neo4j_vector";
import { ChatAnthropic } from "@langchain/anthropic";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { createStuffDocumentsChain } from "langchain/chains/combine_documents";
import { createRetrievalChain } from "langchain/chains/retrieval";
import { AnthropicEmbeddings } from "@langchain/anthropic";

const NEO4J_CONFIG = {
  url: process.env.NEO4J_URI!,
  username: process.env.NEO4J_USER!,
  password: process.env.NEO4J_PASSWORD!,
  indexName: "eventos_vector",
  nodeLabel: "Evento",
  textNodeProperty: "descricao",
  embeddingNodeProperty: "embedding",
};

export async function criarVectorStore(): Promise<Neo4jVectorStore> {
  const embeddings = new AnthropicEmbeddings({
    apiKey: process.env.ANTHROPIC_API_KEY,
    model: "voyage-3",
  });
  return Neo4jVectorStore.fromExistingIndex(embeddings, NEO4J_CONFIG);
}

export async function consultarVectorRag(pergunta: string): Promise<string> {
  const vectorStore = await criarVectorStore();
  const retriever = vectorStore.asRetriever({ k: 10 });

  const llm = new ChatAnthropic({
    apiKey: process.env.ANTHROPIC_API_KEY,
    model: "claude-sonnet-4-6",
  });

  const prompt = ChatPromptTemplate.fromTemplate(`
Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda usando APENAS as informações do contexto abaixo.

Contexto:
{context}

Pergunta: {input}
  `);

  const documentChain = await createStuffDocumentsChain({ llm, prompt });
  const chain = await createRetrievalChain({ retriever, combineDocsChain: documentChain });

  const result = await chain.invoke({ input: pergunta });
  return result.answer as string;
}

export async function indexarEventos(
  eventos: Array<{ descricao: string; metadata: Record<string, unknown> }>
): Promise<void> {
  const embeddings = new AnthropicEmbeddings({
    apiKey: process.env.ANTHROPIC_API_KEY,
    model: "voyage-3",
  });
  const textos = eventos.map((e) => e.descricao);
  const metadados = eventos.map((e) => e.metadata);
  await Neo4jVectorStore.fromTexts(textos, metadados, embeddings, NEO4J_CONFIG);
  console.log(`${eventos.length} eventos indexados no vector store`);
}
