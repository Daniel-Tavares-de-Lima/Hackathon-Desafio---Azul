-- gold.route_exits (ameaca B): voos realizados do grupo Azul (AZU + ACN Azul Conecta) por rota e mes, com flags de saida.
-- AZU e ACN contam juntos: migracao AZU -> ACN no par nao e saida nem reducao (PREMISSAS P-15).
-- Grade densa: cada rota ja operada pela Azul tem uma linha por mes, do primeiro voo ate o ultimo mes da janela.
-- Colunas direcionais (voos_azul, voos_3m, reducao) olham a rota origem->destino; as de par (voos_par_*, saida_total,
-- mes_saida) somam os dois sentidos do par_rota (aeroportos em ordem alfabetica).
--   saida_total: par com >= 30 voos da Azul nos mesmos 3 meses do ano anterior (m-14..m-12), zero em m-2..m e
--                >= 6 meses ativos (com voo da Azul) antes de mes_saida. Como m-2..m estao zerados, a flag so vale a
--                partir de mes_saida+2 (os tres meses zerados sao mes_saida..mes_saida+2).
--   mes_saida:   primeiro mes zerado (mes seguinte ao ultimo voo da Azul no par); so preenchido quando saida_total.
--   reducao:     rota com queda >= 30% vs mesmos 3 meses do ano anterior (base > 0); exclusiva de saida_total.
-- SQL padrao: roda em DuckDB e Snowflake.
CREATE OR REPLACE TABLE gold.route_exits AS
WITH meses AS (
    SELECT ano_mes, CAST(SUBSTR(ano_mes, 1, 4) AS INTEGER) * 12 + CAST(SUBSTR(ano_mes, 6, 2) AS INTEGER) AS idx
    FROM (SELECT DISTINCT ano_mes FROM silver.anac_vra) m
),
voos AS (
    SELECT v.ano_mes, v.origem_icao, v.destino_icao, COUNT(*) AS voos_azul
    FROM silver.anac_vra v
    WHERE v.empresa_icao IN ('AZU', 'ACN') AND v.tipo_linha = 'N' AND v.codigo_di = '0' AND v.situacao_voo = 'REALIZADO'
    GROUP BY v.ano_mes, v.origem_icao, v.destino_icao
),
voos_par AS (
    SELECT ano_mes, LEAST(origem_icao, destino_icao) || '-' || GREATEST(origem_icao, destino_icao) AS par_rota,
           SUM(voos_azul) AS voos_azul
    FROM voos
    GROUP BY ano_mes, LEAST(origem_icao, destino_icao) || '-' || GREATEST(origem_icao, destino_icao)
),
-- direcional
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
        COUNT(*) OVER (PARTITION BY origem_icao, destino_icao ORDER BY idx
                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS meses_na_janela
    FROM grade g
),
comp AS (
    SELECT j.*, a.voos_3m AS voos_3m_ano_anterior
    FROM jan j
    LEFT JOIN jan a ON a.origem_icao = j.origem_icao AND a.destino_icao = j.destino_icao
                   AND a.idx = j.idx - 12 AND a.meses_na_janela = 3
),
-- par (soma dos dois sentidos)
primeiro_par AS (
    SELECT v.par_rota, MIN(m.idx) AS idx_ini
    FROM voos_par v JOIN meses m ON m.ano_mes = v.ano_mes
    GROUP BY v.par_rota
),
grade_par AS (
    SELECT p.par_rota, m.ano_mes, m.idx, COALESCE(v.voos_azul, 0) AS voos_par
    FROM primeiro_par p
    JOIN meses m ON m.idx >= p.idx_ini
    LEFT JOIN voos_par v ON v.par_rota = p.par_rota AND v.ano_mes = m.ano_mes
),
jan_par AS (
    SELECT g.*,
        SUM(voos_par) OVER (PARTITION BY par_rota ORDER BY idx ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS voos_par_3m,
        COUNT(*) OVER (PARTITION BY par_rota ORDER BY idx ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS meses_na_janela,
        MAX(CASE WHEN voos_par > 0 THEN idx END)
            OVER (PARTITION BY par_rota ORDER BY idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS idx_ultimo_voo,
        -- com m-2..m zerados, os meses ativos ate m sao exatamente os meses ativos antes de mes_saida
        SUM(CASE WHEN voos_par > 0 THEN 1 ELSE 0 END)
            OVER (PARTITION BY par_rota ORDER BY idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS meses_ativos
    FROM grade_par g
),
comp_par AS (
    SELECT j.par_rota, j.ano_mes, j.voos_par_3m, a.voos_par_3m AS voos_par_3m_ano_anterior,
           (j.meses_na_janela = 3 AND j.voos_par_3m = 0 AND COALESCE(a.voos_par_3m, 0) >= 30
            AND j.meses_ativos >= 6) AS saida_total,
           j.idx_ultimo_voo + 1 AS idx_saida
    FROM jan_par j
    LEFT JOIN jan_par a ON a.par_rota = j.par_rota AND a.idx = j.idx - 12 AND a.meses_na_janela = 3
)
SELECT
    c.ano_mes, c.origem_icao, c.destino_icao,
    LEAST(c.origem_icao, c.destino_icao) || '-' || GREATEST(c.origem_icao, c.destino_icao) AS par_rota,
    CAST(c.voos_azul AS BIGINT) AS voos_azul,
    CAST(c.voos_3m AS BIGINT) AS voos_3m,
    CAST(c.voos_3m_ano_anterior AS BIGINT) AS voos_3m_ano_anterior,
    CAST(ROUND(100.0 * (c.voos_3m_ano_anterior - c.voos_3m) / NULLIF(c.voos_3m_ano_anterior, 0), 2) AS DECIMAL(7,2)) AS variacao_pct_queda_3m,
    CAST(p.voos_par_3m AS BIGINT) AS voos_par_3m,
    CAST(p.voos_par_3m_ano_anterior AS BIGINT) AS voos_par_3m_ano_anterior,
    p.saida_total,
    CASE WHEN p.saida_total THEN
        LPAD(CAST(CAST(FLOOR((p.idx_saida - 1) / 12) AS INTEGER) AS VARCHAR), 4, '0') || '-' ||
        LPAD(CAST(MOD(p.idx_saida - 1, 12) + 1 AS VARCHAR), 2, '0')
    END AS mes_saida,
    COALESCE(c.voos_3m > 0 AND c.voos_3m_ano_anterior > 0 AND c.voos_3m <= 0.7 * c.voos_3m_ano_anterior, FALSE) AS reducao
FROM comp c
JOIN comp_par p
  ON p.par_rota = LEAST(c.origem_icao, c.destino_icao) || '-' || GREATEST(c.origem_icao, c.destino_icao)
 AND p.ano_mes = c.ano_mes;
