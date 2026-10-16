-- gold.route_competition (ameaca C): por rota, mes e companhia, assentos vendidos, share e tarifa media ponderada.
-- Grupo Azul = AZU + ACN (Azul Conecta, PREMISSAS P-15): ACN nunca e concorrente. Concorrente = companhia fora do grupo.
-- Escopo: rotas onde o grupo Azul vendeu alguma vez na janela. Grade densa por (rota, companhia) para a tarifa dos 3 meses anteriores.
--   queda_tarifa: referencia ANUAL, no par_rota (dois sentidos somados): tarifa media ponderada do mes vs mesmo mes do ano
--     anterior, para o concorrente e para a Azul. Marca quando, no concorrente (fora do grupo Azul):
--       variacao anual do concorrente < 0 e >= 15 pontos percentuais abaixo da variacao anual da Azul;
--       materialidade: concorrente e Azul com >= 1.000 assentos no par no mes e no mesmo mes do ano anterior;
--       referencia estavel: variacao anual da Azul entre -30% e +30%;
--       persistencia: condicao completa valendo em m e em m-1 (mesmo par e mesmo concorrente).
--   revisar_amostra: mesma logica, mas a variacao anual da Azul fora de -30%..+30% em m ou m-1; nao marca queda.
-- SQL padrao: roda em DuckDB e Snowflake.
CREATE OR REPLACE TABLE gold.route_competition AS
WITH meses AS (
    SELECT ano_mes, CAST(SUBSTR(ano_mes, 1, 4) AS INTEGER) * 12 + CAST(SUBSTR(ano_mes, 6, 2) AS INTEGER) AS idx
    FROM (SELECT DISTINCT ano_mes FROM silver.anac_tarifas) m
),
rotas_azul AS (
    SELECT DISTINCT origem_icao, destino_icao FROM silver.anac_tarifas WHERE empresa_icao IN ('AZU', 'ACN')
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
        SUM(assentos_vendidos) OVER (PARTITION BY origem_icao, destino_icao, ano_mes) AS assentos_rota
    FROM grade g
),
calc AS (
    SELECT j.*,
        LEAST(j.origem_icao, j.destino_icao) || '-' || GREATEST(j.origem_icao, j.destino_icao) AS par_rota,
        100.0 * (j.receita / j.assentos_vendidos) / NULLIF(j.receita_3m_ant / NULLIF(j.assentos_3m_ant, 0), 0) - 100.0 AS variacao_conc
    FROM jan j
    WHERE j.assentos_vendidos > 0
),
-- nivel do par: companhia x par_rota x mes (dois sentidos somados) e o mesmo mes do ano anterior
pv AS (
    SELECT par_rota, empresa_icao, ano_mes, idx, SUM(assentos_vendidos) AS assentos, SUM(receita) AS receita
    FROM calc
    GROUP BY par_rota, empresa_icao, ano_mes, idx
),
pv_anual AS (
    SELECT c.par_rota, c.empresa_icao, c.ano_mes, c.idx, c.assentos, a.assentos AS assentos_ano_ant,
           100.0 * ((c.receita / c.assentos) / (a.receita / a.assentos) - 1) AS variacao_anual
    FROM pv c
    LEFT JOIN pv a ON a.par_rota = c.par_rota AND a.empresa_icao = c.empresa_icao AND a.idx = c.idx - 12
),
par_cond AS (
    SELECT p.par_rota, p.empresa_icao, p.ano_mes, p.idx,
           p.variacao_anual AS variacao_anual_conc, z.variacao_anual AS variacao_anual_azul,
           -- regras do mes, sem referencia estavel nem persistencia
           COALESCE(p.empresa_icao NOT IN ('AZU', 'ACN')
                    AND p.variacao_anual < 0 AND z.variacao_anual IS NOT NULL
                    AND p.variacao_anual - z.variacao_anual <= -15
                    AND p.assentos >= 1000 AND p.assentos_ano_ant >= 1000
                    AND z.assentos >= 1000 AND z.assentos_ano_ant >= 1000, FALSE) AS cond_nucleo,
           COALESCE(z.variacao_anual BETWEEN -30 AND 30, FALSE) AS azul_estavel
    FROM pv_anual p
    -- ponytail: referencia so com AZU; a ANAC tarifas nao tem linha ACN na janela. Se aparecer, somar AZU + ACN aqui.
    LEFT JOIN pv_anual z ON z.par_rota = p.par_rota AND z.empresa_icao = 'AZU' AND z.ano_mes = p.ano_mes
),
persist AS (
    SELECT d.*,
        LAG(d.idx) OVER w AS idx_ant,
        LAG(d.cond_nucleo) OVER w AS nucleo_ant,
        LAG(d.azul_estavel) OVER w AS estavel_ant
    FROM par_cond d
    WINDOW w AS (PARTITION BY d.par_rota, d.empresa_icao ORDER BY d.idx)
)
SELECT
    c.ano_mes, c.origem_icao, c.destino_icao, c.par_rota, c.empresa_icao,
    CAST(c.assentos_vendidos AS BIGINT) AS assentos_vendidos,
    CAST(ROUND(100.0 * c.assentos_vendidos / c.assentos_rota, 2) AS DECIMAL(6,2)) AS participacao_assentos_pct,
    CAST(ROUND(c.receita / c.assentos_vendidos, 2) AS DECIMAL(12,2)) AS tarifa_media_ponderada,
    CAST(ROUND(c.receita_3m_ant / NULLIF(c.assentos_3m_ant, 0), 2) AS DECIMAL(12,2)) AS tarifa_media_3m_anteriores,
    CAST(ROUND(c.variacao_conc, 2) AS DECIMAL(8,2)) AS variacao_tarifa_pct,
    CAST(ROUND(p.variacao_anual_conc, 2) AS DECIMAL(8,2)) AS variacao_anual_pct,
    CAST(ROUND(p.variacao_anual_azul, 2) AS DECIMAL(8,2)) AS variacao_anual_azul_pct,
    CASE WHEN c.empresa_icao NOT IN ('AZU', 'ACN')
         THEN CAST(ROUND(p.variacao_anual_conc - p.variacao_anual_azul, 2) AS DECIMAL(8,2)) END AS diferenca_anual_pp,
    COALESCE(p.cond_nucleo AND p.azul_estavel AND p.idx_ant = p.idx - 1 AND p.nucleo_ant AND p.estavel_ant, FALSE) AS queda_tarifa,
    COALESCE(p.cond_nucleo AND p.idx_ant = p.idx - 1 AND p.nucleo_ant
             AND NOT (p.azul_estavel AND p.estavel_ant), FALSE) AS revisar_amostra
FROM calc c
JOIN persist p ON p.par_rota = c.par_rota AND p.empresa_icao = c.empresa_icao AND p.ano_mes = c.ano_mes;
