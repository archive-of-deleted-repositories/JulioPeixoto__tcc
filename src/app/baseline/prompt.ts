/**
 * Prompt de geração compartilhado por VectorRAG e GraphRAG.
 *
 * Por que existe: os dois baselines usavam textos diferentes — o do GraphRAG
 * vivia em `evaluation/ragas.ts`, o do VectorRAG em `baseline/vectorRag.ts`.
 * Prompts distintos entre os arms são um confundidor: parte da diferença medida
 * seria efeito do texto do prompt, não da arquitetura de recuperação. Com um
 * único prompt, a única variável que sobra entre os dois modos é COMO o contexto
 * foi recuperado, que é o objeto do estudo.
 *
 * A instrução de citar números concretos foi acrescentada depois que o benchmark
 * expôs o seguinte: em perguntas de sim/não (C1_factual), o contexto do GraphRAG
 * trazia a contagem exata ("total de registros: 15") e o gerador respondia
 * apenas "Sim, houve registros" — recuperação certa, resposta pobre. A instrução
 * vale para os dois modos igualmente.
 */
export const SYSTEM_RAG = `Você é um assistente especializado em eventos climáticos extremos no Brasil.

Regras:
- Responda usando APENAS as informações do contexto fornecido. Nunca invente dados.
- Cite os números concretos que o contexto trouxer (contagens, valores medidos,
  datas, nomes de municípios e estações). Se o contexto informa um total, declare
  esse total em vez de responder apenas "sim" ou "houve registros".
- Se o contexto não contiver a informação pedida, diga explicitamente que a base
  não possui esses registros — não estime nem extrapole números.`;
