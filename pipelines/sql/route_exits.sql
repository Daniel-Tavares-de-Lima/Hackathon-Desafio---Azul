-- gold.route_exits (ameaca B): voos realizados da Azul (AZU) por rota e mes, com flags de saida.
-- Grade densa: cada rota ja operada pela Azul tem uma linha por mes, do primeiro voo ate o ultimo mes da janela.
-- Janela movel de 3 meses (m-2..m) contra os mesmos 3 meses do ano anterior (m-14..m-12).
--   saida_total: voos > 0 antes da janela de 3 meses e zero nos ultimos 3 meses.
--   reducao:     queda >= 30% vs mesmos meses do ano anterior (base > 0); exclusiva de saida_total.
-- SQL padrao: roda em DuckDB e Snowflake.
CREATE OR REPLACE TABLE gold.route_exits AS
WITH meses AS (
    SELECT ano_mes, CAST(SUBSTR(ano_mes, 1, 4) AS INTEGER) * 12 + CAST(SUBSTR(ano_mes, 6, 2) AS INTEGER) AS idx
    FROM (SELECT DISTINCT ano_mes FROM silver.anac_vra) m
),
voos AS (
    SELECT v.ano_mes, v.origem_icao, v.destino_icao, COUNT(*) AS voos_azul
    FROM silver.anac_vra v
    WHERE v.empresa_icao = 'AZU' AND v.tipo_linha = 'N' AND v.codigo_di = '0' AND v.situacao_voo = 'REALIZADO'
    GROUP BY v.ano_mes, v.origem_icao, v.destino_icao
),
primeiro AS (
    SELECT v.origem_icao, v.destino_icao, MIN(m.idx) AS idx_ini
    FROM voos v JOIN meses m ON m.ano_mes = v.ano_mes
    GROUP BY v.origem_icao, v.destino_icao
),
grade AS (
    SELECT p.origem_icao, p.destino_icao, m.ano_mes, m.idx, COALESCE(v.voos_azul, 0) AS voos_azul
    FROM primeiro p
    JOIN meses m ON m.idx >= p.idx_ini
    LEFT JOIN voos v ON v.origem_icao = p.origem_icao AND v.destino_icao = p.destino_icao AND v.ano_mes = m.ano_mes
),
jan AS (
    SELECT g.*,
        SUM(voos_azul) OVER (PARTITION BY origem_icao, destino_icao ORDER BY idx
                             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS voos_3m,
        SUM(voos_azul) OVER (PARTITION BY origem_icao, destino_icao ORDER BY idx
                             ROWS BETWEEN UNBOUNDED PRECEDING AND 3 PRECEDING) AS voos_antes_3m,
        COUNT(*) OVER (PARTITION BY origem_icao, destino_icao ORDER BY idx
                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS meses_na_janela
    FROM grade g
),
comp AS (
    SELECT j.*, a.voos_3m AS voos_3m_ano_anterior
    FROM jan j
    LEFT JOIN jan a ON a.origem_icao = j.origem_icao AND a.destino_icao = j.destino_icao
                   AND a.idx = j.idx - 12 AND a.meses_na_janela = 3
)
SELECT
    ano_mes, origem_icao, destino_icao, voos_azul, voos_3m, voos_3m_ano_anterior,
    ROUND(100.0 * (voos_3m_ano_anterior - voos_3m) / NULLIF(voos_3m_ano_anterior, 0), 2) AS variacao_pct_queda_3m,
    (meses_na_janela = 3 AND voos_3m = 0 AND COALESCE(voos_antes_3m, 0) > 0) AS saida_total,
    (voos_3m > 0 AND voos_3m_ano_anterior > 0 AND voos_3m <= 0.7 * voos_3m_ano_anterior) AS reducao
FROM comp;
