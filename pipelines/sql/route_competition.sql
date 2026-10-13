-- gold.route_competition (ameaca C): por rota, mes e companhia, assentos vendidos, share e tarifa media ponderada.
-- Escopo: rotas onde a Azul vendeu alguma vez na janela. Grade densa por (rota, companhia) para olhar os 3 meses anteriores.
--   entrada_concorrente: companhia != AZU vende no mes e nao vendeu nos 3 meses anteriores (exige 3 meses anteriores na janela).
--   queda_tarifa: concorrente com venda nos 3 meses anteriores, tarifa em queda (variacao < 0) e variacao
--     >= 15 pontos percentuais abaixo da variacao da tarifa da Azul no mesmo par_rota e mes (os dois sentidos somados).
--     Azul e concorrente caindo juntos = sazonalidade, nao marca. Azul sem venda no mes ou nos 3 anteriores = nao marca.
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
),
-- referencia da Azul por par (os dois sentidos somados), mesma definicao de variacao
azul_par AS (
    SELECT LEAST(origem_icao, destino_icao) || '-' || GREATEST(origem_icao, destino_icao) AS par_rota,
           idx, ano_mes, SUM(assentos_vendidos) AS assentos, SUM(receita) AS receita,
           SUM(assentos_3m_ant) AS assentos_ant, SUM(receita_3m_ant) AS receita_ant
    FROM jan
    WHERE empresa_icao = 'AZU'
    GROUP BY LEAST(origem_icao, destino_icao) || '-' || GREATEST(origem_icao, destino_icao), idx, ano_mes
),
azul_var AS (
    SELECT par_rota, ano_mes, assentos AS assentos_azul_par,
           CASE WHEN assentos > 0 AND assentos_ant > 0
                THEN 100.0 * (receita / assentos) / (receita_ant / assentos_ant) - 100.0 END AS variacao_azul
    FROM azul_par
),
calc AS (
    SELECT j.*,
        LEAST(j.origem_icao, j.destino_icao) || '-' || GREATEST(j.origem_icao, j.destino_icao) AS par_rota,
        100.0 * (j.receita / j.assentos_vendidos) / NULLIF(j.receita_3m_ant / NULLIF(j.assentos_3m_ant, 0), 0) - 100.0 AS variacao_conc
    FROM jan j
    WHERE j.assentos_vendidos > 0
)
SELECT
    c.ano_mes, c.origem_icao, c.destino_icao, c.par_rota, c.empresa_icao,
    c.assentos_vendidos,
    ROUND(100.0 * c.assentos_vendidos / c.assentos_rota, 2) AS participacao_assentos_pct,
    ROUND(c.receita / c.assentos_vendidos, 2) AS tarifa_media_ponderada,
    ROUND(c.receita_3m_ant / NULLIF(c.assentos_3m_ant, 0), 2) AS tarifa_media_3m_anteriores,
    ROUND(c.variacao_conc, 2) AS variacao_tarifa_pct,
    ROUND(a.variacao_azul, 2) AS variacao_tarifa_azul_pct,
    CASE WHEN c.empresa_icao <> 'AZU' THEN ROUND(c.variacao_conc - a.variacao_azul, 2) END AS diferenca_queda_pp,
    (c.empresa_icao <> 'AZU' AND c.meses_ant = 3 AND c.assentos_3m_ant = 0) AS entrada_concorrente,
    (c.empresa_icao <> 'AZU' AND c.meses_ant_com_venda = 3 AND c.variacao_conc < 0
        AND a.variacao_azul IS NOT NULL AND c.variacao_conc - a.variacao_azul <= -15) AS queda_tarifa
FROM calc c
LEFT JOIN azul_var a ON a.par_rota = c.par_rota AND a.ano_mes = c.ano_mes;
