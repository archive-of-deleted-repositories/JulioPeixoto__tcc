import { Neo4jVectorStore } from "@langchain/community/vectorstores/neo4j_vector";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { createStuffDocumentsChain } from "langchain/chains/combine_documents";
import { createRetrievalChain } from "langchain/chains/retrieval";
import { criarEmbeddings, criarLangChainLLM } from "../ai/index.ts";
import { SYSTEM_RAG } from "./prompt.ts";

/**
 * O corpus vetorial vive num label PRÓPRIO (`EventoIndexado`), separado do
 * `Evento` do grafo.
 *
 * Motivo: `Neo4jVectorStore.fromTexts` cria nós novos, não anexa embeddings aos
 * existentes. Enquanto isso apontava para `nodeLabel: "Evento"`, cada
 * reindexação despejava mais uma cópia órfã de cada evento dentro do mesmo
 * label do grafo — nós sem nenhuma aresta, invisíveis para o GraphRAG (que só
 * navega por :SOFREU/:REGISTROU) mas contados por qualquer `MATCH (e:Evento)`.
 * O grafo chegou a 67.531 Eventos para 33.501 eventos reais.
 *
 * Com label separado, os dois baselines continuam vendo os mesmos fatos, mas o
 * corpus do VectorRAG não contamina mais a contagem do grafo.
 */
export const LABEL_INDEXADO = "EventoIndexado";

const NEO4J_CONFIG = {
  url: process.env.NEO4J_URI!,
  username: process.env.NEO4J_USER!,
  password: process.env.NEO4J_PASSWORD!,
  indexName: "eventos_vector",
  nodeLabel: LABEL_INDEXADO,
  textNodeProperty: "descricao",
  embeddingNodeProperty: "embedding",
};

export async function criarVectorStore(): Promise<Neo4jVectorStore> {
  return Neo4jVectorStore.fromExistingIndex(criarEmbeddings(), NEO4J_CONFIG);
}

export async function consultarVectorRag(
  pergunta: string
): Promise<{ resposta: string; contexto: string }> {
  const vectorStore = await criarVectorStore();
  const retriever = vectorStore.asRetriever({ k: 10 });

  // Mesmo prompt do GraphRAG — ver comentário em ./prompt.ts.
  const prompt = ChatPromptTemplate.fromTemplate(
    `${SYSTEM_RAG}\n\nContexto:\n{context}\n\nPergunta: {input}`
  );

  const documentChain = await createStuffDocumentsChain({ llm: criarLangChainLLM(), prompt });
  const chain = await createRetrievalChain({ retriever, combineDocsChain: documentChain });

  const result = await chain.invoke({ input: pergunta });
  const docs = (result.context as Array<{ pageContent: string }>) ?? [];
  const contexto = docs.map((d) => d.pageContent).join("\n");
  return { resposta: result.answer as string, contexto };
}

export async function indexarEventos(
  eventos: Array<{ descricao: string; metadata: Record<string, unknown> }>
): Promise<void> {
  const textos = eventos.map((e) => e.descricao);
  const metadados = eventos.map((e) => e.metadata);
  await Neo4jVectorStore.fromTexts(textos, metadados, criarEmbeddings(), NEO4J_CONFIG);
  console.log(`${eventos.length} eventos indexados no vector store`);
}
