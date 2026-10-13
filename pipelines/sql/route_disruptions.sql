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
    COUNT(*) AS voos_previstos,
    SUM(CASE WHEN situacao_voo = 'REALIZADO' THEN 1 ELSE 0 END) AS voos_realizados,
    SUM(CASE WHEN situacao_voo = 'CANCELADO' THEN 1 ELSE 0 END) AS voos_cancelados,
    SUM(CASE WHEN situacao_voo = 'REALIZADO' AND atraso_partida_min > 30 THEN 1 ELSE 0 END) AS voos_atraso_30,
    ROUND(100.0 * SUM(CASE WHEN situacao_voo = 'REALIZADO' AND atraso_partida_min > 30 THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN situacao_voo = 'REALIZADO' THEN 1 ELSE 0 END), 0), 2) AS pct_atraso_30,
    ROUND(100.0 * SUM(CASE WHEN situacao_voo = 'CANCELADO' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_cancelado
FROM silver.anac_vra
WHERE tipo_linha = 'N'
  AND codigo_di = '0'
  AND situacao_voo IN ('REALIZADO', 'CANCELADO')
GROUP BY ano_mes, origem_icao, destino_icao, empresa_icao;
