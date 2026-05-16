export const QUERIES = {
  eventosPorMunicipio: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE toLower(m.nome) CONTAINS toLower($nome)
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
    RETURN m.nome AS municipio, m.uf AS uf, count(e) AS total
    ORDER BY total DESC LIMIT 15
  `,

  estacoesPorEstado: `
    MATCH (s:Estacao)-[:PERTENCE_A]->(m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    RETURN s.codigo AS codigo, s.nome AS nome, s.lat AS lat, s.lon AS lon,
           m.nome AS municipio
  `,

  fenomenosFrequentes: `
    MATCH (e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE ($data_inicio IS NULL OR e.data >= date($data_inicio))
    RETURN f.nome AS fenomeno, count(e) AS total
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
