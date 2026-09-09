export const QUERIES = {
  eventosPorMunicipio: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE toLower(m.nome) CONTAINS toLower($nome)
      AND ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN m.nome AS municipio, m.uf AS uf,
           e.tipo AS tipo, e.data AS data,
           e.descricao AS descricao, e.valor AS valor,
           f.nome AS fenomeno, e.fonte AS fonte
    ORDER BY e.data DESC LIMIT 30
  `,

  eventosPorEstado: `
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    MATCH (m)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN m.nome AS municipio, e.tipo AS tipo, e.data AS data,
           e.valor AS valor, f.nome AS fenomeno
    ORDER BY e.data DESC LIMIT 50
  `,

  municipiosComMaisEventos: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE ($fenomeno IS NULL OR f.chave = $fenomeno)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN m.nome AS municipio, m.uf AS uf, f.nome AS fenomeno, count(e) AS total
    ORDER BY total DESC LIMIT 15
  `,

  estacoesPorEstado: `
    MATCH (s:Estacao)-[:PERTENCE_A]->(m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    RETURN s.codigo AS codigo, s.nome AS nome, s.lat AS lat, s.lon AS lon,
           m.nome AS municipio
  `,

  municipiosMaisEventosPorEstado: `
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    MATCH (m)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN m.nome AS municipio, m.uf AS uf, f.nome AS fenomeno, count(e) AS total
    ORDER BY total DESC LIMIT 15
  `,

  fenomenosFrequentes: `
    MATCH (e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE ($data_inicio IS NULL OR e.data >= date($data_inicio))
    RETURN f.nome AS fenomeno, count(e) AS total
    ORDER BY total DESC
  `,

  // ── Agregações temporais ──────────────────────────────────────────────────
  // Contam registros por ano em vez de listar eventos individuais. É o que
  // permite responder "houve mais X em 2018 ou em 2020?" sem que o LLM precise
  // recontar linha a linha — e o que a recuperação por similaridade não alcança.

  comparativoTemporalMunicipio: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE toLower(m.nome) CONTAINS toLower($nome)
      AND ($tipo IS NULL OR e.tipo = $tipo)
      AND e.data.year IN $anos
    RETURN m.nome AS municipio, m.uf AS uf, e.data.year AS ano,
           f.nome AS fenomeno, e.tipo AS tipo,
           count(e) AS total,
           round(avg(e.valor), 2) AS valor_medio,
           max(e.valor) AS valor_max
    ORDER BY municipio, tipo, ano
  `,

  comparativoTemporalEstado: `
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    MATCH (m)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE ($tipo IS NULL OR e.tipo = $tipo)
      AND e.data.year IN $anos
    RETURN est.sigla AS uf, e.data.year AS ano,
           f.nome AS fenomeno, e.tipo AS tipo,
           count(e) AS total,
           round(avg(e.valor), 2) AS valor_medio,
           max(e.valor) AS valor_max
    ORDER BY tipo, ano
  `,

  // Estações que reportaram em TODOS os anos comparados. Serve para checar se a
  // variação entre épocas é real ou apenas mudança de cobertura de sensores
  // (ver ANALISE_COMPARACAO_TEMPORAL.md, seção 4).
  coberturaEstacoesPorAno: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)<-[:REGISTROU]-(s:Estacao)
    WHERE toLower(m.nome) CONTAINS toLower($nome)
      AND e.data.year IN $anos
    WITH e.data.year AS ano, collect(DISTINCT s.codigo) AS estacoes
    RETURN ano, size(estacoes) AS n_estacoes, estacoes
    ORDER BY ano
  `,

  sazonalidadePorEstado: `
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    MATCH (m)-[:SOFREU]->(e:Evento)
    WHERE ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN e.data.month AS mes, e.tipo AS tipo, count(e) AS total
    ORDER BY total DESC
  `,

  // Maior valor registrado + estação + município: travessia de dois saltos.
  extremoPorEstado: `
    MATCH (s:Estacao)-[:REGISTROU]->(e:Evento)
    MATCH (s)-[:PERTENCE_A]->(m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    WHERE ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN s.codigo AS estacao, s.nome AS estacao_nome, m.nome AS municipio,
           e.tipo AS tipo, e.valor AS valor, e.data AS data
    ORDER BY abs(e.valor) DESC LIMIT 5
  `,

  contagemPorEstado: `
    MATCH (m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    MATCH (m)-[:SOFREU]->(e:Evento)
    WHERE ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN e.tipo AS tipo, count(e) AS total,
           count(DISTINCT m) AS n_municipios
    ORDER BY total DESC
  `,

  contagemPorMunicipio: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)
    WHERE toLower(m.nome) CONTAINS toLower($nome)
      AND ($tipo IS NULL OR e.tipo = $tipo)
      AND ($data_inicio IS NULL OR e.data >= date($data_inicio))
      AND ($data_fim IS NULL OR e.data <= date($data_fim))
    RETURN m.nome AS municipio, m.uf AS uf, e.tipo AS tipo, count(e) AS total
    ORDER BY total DESC
  `,

  eventosPorTipoEPeriodo: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE e.tipo = $tipo
      AND e.data >= date($data_inicio)
      AND e.data <= date($data_fim)
    RETURN m.nome AS municipio, m.uf AS uf, e.data AS data,
           e.valor AS valor, e.descricao AS descricao
    ORDER BY e.data DESC LIMIT 50
  `,
} as const;
