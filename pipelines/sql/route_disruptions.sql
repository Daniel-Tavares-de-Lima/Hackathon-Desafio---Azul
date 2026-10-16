-- gold.route_disruptions (ameaca A): voos previstos/realizados/cancelados e % com atraso > 30 min,
-- por rota (origem->destino), companhia e mes. SQL padrao: roda em DuckDB e Snowflake.
-- Filtros (PREMISSAS P-02/P-03): so passageiro (tipo_linha = 'N') e voo programado (codigo_di = '0').
-- Atraso = partida_real - partida_prevista > 30 min, calculado sobre os voos realizados.
CREATE OR REPLACE TABLE gold.route_disruptions AS
SELECT
    ano_mes,
    origem_icao,
    destino_icao,
    empresa_icao,
    CAST(COUNT(*) AS BIGINT) AS voos_previstos,
    CAST(SUM(CASE WHEN situacao_voo = 'REALIZADO' THEN 1 ELSE 0 END) AS BIGINT) AS voos_realizados,
    CAST(SUM(CASE WHEN situacao_voo = 'CANCELADO' THEN 1 ELSE 0 END) AS BIGINT) AS voos_cancelados,
    CAST(SUM(CASE WHEN situacao_voo = 'REALIZADO' AND atraso_partida_min > 30 THEN 1 ELSE 0 END) AS BIGINT) AS voos_atraso_30,
    CAST(ROUND(100.0 * SUM(CASE WHEN situacao_voo = 'REALIZADO' AND atraso_partida_min > 30 THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN situacao_voo = 'REALIZADO' THEN 1 ELSE 0 END), 0), 2) AS DECIMAL(6,2)) AS pct_atraso_30,
    CAST(ROUND(100.0 * SUM(CASE WHEN situacao_voo = 'CANCELADO' THEN 1 ELSE 0 END) / COUNT(*), 2) AS DECIMAL(6,2)) AS pct_cancelado
FROM silver.anac_vra
WHERE tipo_linha = 'N'
  AND codigo_di = '0'
  AND situacao_voo IN ('REALIZADO', 'CANCELADO')
GROUP BY ano_mes, origem_icao, destino_icao, empresa_icao;
