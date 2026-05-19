import { Neo4jVectorStore } from "@langchain/community/vectorstores/neo4j_vector";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { createStuffDocumentsChain } from "langchain/chains/combine_documents";
import { createRetrievalChain } from "langchain/chains/retrieval";
import { criarEmbeddings, criarLangChainLLM } from "../ai/index.ts";

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
  return Neo4jVectorStore.fromExistingIndex(criarEmbeddings(), NEO4J_CONFIG);
}

export async function consultarVectorRag(pergunta: string): Promise<string> {
  const vectorStore = await criarVectorStore();
  const retriever = vectorStore.asRetriever({ k: 10 });

  const prompt = ChatPromptTemplate.fromTemplate(`
Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda usando APENAS as informações do contexto abaixo.

Contexto:
{context}

Pergunta: {input}
  `);

  const documentChain = await createStuffDocumentsChain({ llm: criarLangChainLLM(), prompt });
  const chain = await createRetrievalChain({ retriever, combineDocsChain: documentChain });

  const result = await chain.invoke({ input: pergunta });
  return result.answer as string;
}

export async function indexarEventos(
  eventos: Array<{ descricao: string; metadata: Record<string, unknown> }>
): Promise<void> {
  const textos = eventos.map((e) => e.descricao);
  const metadados = eventos.map((e) => e.metadata);
  await Neo4jVectorStore.fromTexts(textos, metadados, criarEmbeddings(), NEO4J_CONFIG);
  console.log(`${eventos.length} eventos indexados no vector store`);
}
