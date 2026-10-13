-- gold.route_competition (ameaca C): por rota, mes e companhia, assentos vendidos, share e tarifa media ponderada.
-- Escopo: rotas onde a Azul vendeu alguma vez na janela. Grade densa por (rota, companhia) para olhar os 3 meses anteriores.
--   entrada_concorrente: companhia != AZU vende no mes e nao vendeu nos 3 meses anteriores (exige 3 meses anteriores na janela).
--   queda_tarifa: tarifa media do concorrente <= 85% da tarifa media ponderada dos 3 meses anteriores (todos com venda).
-- SQL padrao: roda em DuckDB e Snowflake.
CREATE OR REPLACE TABLE gold.route_competition AS
WITH meses AS (
    SELECT ano_mes, CAST(SUBSTR(ano_mes, 1, 4) AS INTEGER) * 12 + CAST(SUBSTR(ano_mes, 6, 2) AS INTEGER) AS idx
    FROM (SELECT DISTINCT ano_mes FROM silver.anac_tarifas) m
),
rotas_azul AS (
    SELECT DISTINCT origem_icao, destino_icao FROM silver.anac_tarifas WHERE empresa_icao = 'AZU'
),
venda AS (
    SELECT t.ano_mes, t.origem_icao, t.destino_icao, t.empresa_icao,
           SUM(t.assentos) AS assentos_vendidos,
           SUM(t.tarifa * t.assentos) AS receita
    FROM silver.anac_tarifas t
    JOIN rotas_azul r ON r.origem_icao = t.origem_icao AND r.destino_icao = t.destino_icao
    WHERE t.assentos > 0 AND t.tarifa > 0
    GROUP BY t.ano_mes, t.origem_icao, t.destino_icao, t.empresa_icao
),
pares AS (
    SELECT DISTINCT origem_icao, destino_icao, empresa_icao FROM venda
),
grade AS (
    SELECT p.origem_icao, p.destino_icao, p.empresa_icao, m.ano_mes, m.idx,
           COALESCE(v.assentos_vendidos, 0) AS assentos_vendidos,
           COALESCE(v.receita, 0) AS receita
    FROM pares p
    CROSS JOIN meses m
    LEFT JOIN venda v ON v.origem_icao = p.origem_icao AND v.destino_icao = p.destino_icao
                     AND v.empresa_icao = p.empresa_icao AND v.ano_mes = m.ano_mes
),
jan AS (
    SELECT g.*,
        SUM(assentos_vendidos) OVER (PARTITION BY origem_icao, destino_icao, empresa_icao ORDER BY idx
                                     ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS assentos_3m_ant,
        SUM(receita) OVER (PARTITION BY origem_icao, destino_icao, empresa_icao ORDER BY idx
                           ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS receita_3m_ant,
        COUNT(*) OVER (PARTITION BY origem_icao, destino_icao, empresa_icao ORDER BY idx
                       ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS meses_ant,
        SUM(CASE WHEN assentos_vendidos > 0 THEN 1 ELSE 0 END)
            OVER (PARTITION BY origem_icao, destino_icao, empresa_icao ORDER BY idx
                  ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS meses_ant_com_venda,
        SUM(assentos_vendidos) OVER (PARTITION BY origem_icao, destino_icao, ano_mes) AS assentos_rota
    FROM grade g
)
SELECT
    ano_mes, origem_icao, destino_icao, empresa_icao,
    assentos_vendidos,
    ROUND(100.0 * assentos_vendidos / assentos_rota, 2) AS participacao_assentos_pct,
    ROUND(receita / assentos_vendidos, 2) AS tarifa_media_ponderada,
    ROUND(receita_3m_ant / NULLIF(assentos_3m_ant, 0), 2) AS tarifa_media_3m_anteriores,
    ROUND(100.0 * (receita / assentos_vendidos) / (receita_3m_ant / NULLIF(assentos_3m_ant, 0)) - 100.0, 2) AS variacao_tarifa_pct,
    (empresa_icao <> 'AZU' AND meses_ant = 3 AND assentos_3m_ant = 0) AS entrada_concorrente,
    (empresa_icao <> 'AZU' AND meses_ant_com_venda = 3
        AND receita / assentos_vendidos <= 0.85 * (receita_3m_ant / assentos_3m_ant)) AS queda_tarifa
FROM jan
WHERE assentos_vendidos > 0;
