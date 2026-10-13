-- gold.route_competition (ameaca C): por rota, mes e companhia, assentos vendidos, share e tarifa media ponderada.
-- Escopo: rotas onde a Azul vendeu alguma vez na janela. Grade densa por (rota, companhia) para olhar os 3 meses anteriores.
--   entrada_concorrente: companhia != AZU vende no mes e nao vendeu nos 3 meses anteriores (exige 3 meses anteriores na janela).
--   queda_tarifa: concorrente (!= AZU) com venda nos 3 meses anteriores, variacao propria < 0 e variacao >= 15 pontos
--     percentuais abaixo da variacao da Azul no mesmo par_rota e mes (dois sentidos somados), alem de:
--       materialidade: concorrente e Azul com >= 1.000 assentos no par no mes (dois sentidos somados);
--       referencia estavel: variacao da Azul entre -30% e +30%;
--       persistencia: condicao completa valendo no mes e no mes imediatamente anterior, mesma rota e mesmo concorrente.
--     Azul e concorrente caindo juntos = sazonalidade, nao marca. Azul sem venda no mes ou nos 3 anteriores = nao marca.
--   revisar_amostra: tudo acima vale (materialidade e persistencia incluidas) menos a referencia estavel da Azul
--     (variacao da Azul fora de -30%..+30% em algum dos 2 meses): nao marca queda, pede revisao manual.
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
),
base AS (
    SELECT c.*, a.variacao_azul, a.assentos_azul_par,
        SUM(c.assentos_vendidos) OVER (PARTITION BY c.par_rota, c.empresa_icao, c.ano_mes) AS assentos_conc_par
    FROM calc c
    LEFT JOIN azul_var a ON a.par_rota = c.par_rota AND a.ano_mes = c.ano_mes
),
cond AS (
    SELECT b.*,
        -- regras do mes, sem referencia estavel nem persistencia
        COALESCE(b.empresa_icao <> 'AZU' AND b.meses_ant_com_venda = 3 AND b.variacao_conc < 0
         AND b.variacao_azul IS NOT NULL AND b.variacao_conc - b.variacao_azul <= -15
         AND b.assentos_conc_par >= 1000 AND b.assentos_azul_par >= 1000, FALSE) AS cond_nucleo,
        COALESCE(b.variacao_azul BETWEEN -30 AND 30, FALSE) AS azul_estavel
    FROM base b
),
persist AS (
    SELECT d.*,
        LAG(d.idx) OVER w AS idx_ant,
        LAG(d.cond_nucleo) OVER w AS nucleo_ant,
        LAG(d.azul_estavel) OVER w AS estavel_ant
    FROM cond d
    WINDOW w AS (PARTITION BY d.origem_icao, d.destino_icao, d.empresa_icao ORDER BY d.idx)
)
SELECT
    ano_mes, origem_icao, destino_icao, par_rota, empresa_icao,
    assentos_vendidos,
    ROUND(100.0 * assentos_vendidos / assentos_rota, 2) AS participacao_assentos_pct,
    ROUND(receita / assentos_vendidos, 2) AS tarifa_media_ponderada,
    ROUND(receita_3m_ant / NULLIF(assentos_3m_ant, 0), 2) AS tarifa_media_3m_anteriores,
    ROUND(variacao_conc, 2) AS variacao_tarifa_pct,
    ROUND(variacao_azul, 2) AS variacao_tarifa_azul_pct,
    CASE WHEN empresa_icao <> 'AZU' THEN ROUND(variacao_conc - variacao_azul, 2) END AS diferenca_queda_pp,
    (empresa_icao <> 'AZU' AND meses_ant = 3 AND assentos_3m_ant = 0) AS entrada_concorrente,
    COALESCE(cond_nucleo AND azul_estavel AND idx_ant = idx - 1 AND nucleo_ant AND estavel_ant, FALSE) AS queda_tarifa,
    COALESCE(cond_nucleo AND idx_ant = idx - 1 AND nucleo_ant AND NOT (azul_estavel AND estavel_ant), FALSE) AS revisar_amostra
FROM persist;
