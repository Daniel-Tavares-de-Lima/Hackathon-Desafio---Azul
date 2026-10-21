"""Reclamações do Consumidor.gov.br sobre companhias aéreas (dados abertos ANAC, CC-BY) -> bronze -> silver -> gold.

Fonte: https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Dados%20do%20consumidor.gov/
(conjunto "Voos e operações aéreas - Dados do consumidor.Gov" no dados.gov.br, licença Creative Commons Attribution;
dados da plataforma Consumidor.gov.br, gerida pela Senacon, republicados pela ANAC/GCON). Ver P-18.

Uso: python -I pipelines/ingest_consumidor.py [--force]
Idempotente e offline: ano com CSV final no bronze não toca a rede. Download vai para <arquivo>.part (retomada com
Range só a partir do .part) e só é renomeado quando o tamanho bate com o Content-Length. --force confere o tamanho
remoto e, se mudou (republicação), baixa do zero. Sem rede: segue com o bronze local, avisando; sem bronze, erro.
CONSUMIDOR_URL (com {y}) troca a URL, para teste.
Arquivos baixados são dados não confiáveis: só são lidos como CSV pelo duckdb, nunca executados.
Privacidade: o silver guarda só mês, empresa, problema e desfecho; região, UF, cidade e demais campos do
consumidor são descartados na leitura. A gold é agregada (empresa x tema x mês).
"""
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))  # -I tira o diretório do script do sys.path
from build_gold import checar_contrato  # noqa: E402

URL = os.environ.get("CONSUMIDOR_URL") or ("https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/"
       "Dados%20do%20consumidor.gov/dadosconsumidor{y}.csv")
ANOS = [2024, 2025, 2026]  # 2026 ainda não publicado em 2026-10-20 (404 é tolerado)
MES_INI = "2024-09"  # mesma janela da ANAC (P-01)
BRONZE = ROOT / "data" / "bronze" / "consumidor"
SILVER = ROOT / "data" / "silver" / "consumidor_aereo" / "data.parquet"
GOLD = ROOT / "data" / "gold" / "friction_themes" / "data.parquet"

# Empresa (Nome Fantasia no arquivo) -> sigla ICAO, só as três maiores do doméstico. O resto vira 'OUTRAS'.
EMPRESAS = {"Azul Linhas Aéreas": "AZU", "Gol Linhas Aéreas": "GLO", "Latam Airlines (Tam)": "TAM"}

# De/para "Problema" do arquivo (texto exato, sem espaço nas pontas) -> tema da taxonomia fechada. Um problema por
# reclamação, então o tema é único (sem multirrótulo). Problema fora da lista -> 'outro'. Tabela com volumes em P-18.
PROBLEMA_TEMA = {
    "Cancelamento de voo": "atraso/cancelamento",
    "Atraso de voo": "atraso/cancelamento",
    "Negativa de embarque de passageiro (preterição / overbooking)": "atraso/cancelamento",
    "Falta de acesso a comunicação, alimentação, acomodação e/ou traslado em caso de atraso, cancelamento ou "
    "interrupção de voo": "atraso/cancelamento",
    "Falta de informação sobre atraso, cancelamento ou interrupção de voo": "atraso/cancelamento",
    "Extravio/ avaria de bagagem, carga, correspondência (ressarcimento, indenizações)": "bagagem",
    "Dificuldade para embarque com bagagem de mão": "bagagem",
    "Cobrança indevida por excesso de bagagem": "bagagem",
    "Dificuldade / atraso na devolução de valores pagos / reembolso / retenção de valores": "reembolso",
    "Dificuldade para contratar o serviço (problema operacionais, acesso aos canais de venda etc)": "canais de venda/app",
    "Dificuldades com Programas de Fidelidade / Pontuação (resgate, alteração, transferência etc)": "pontos/resgate",
    "Cobrança indevida / abusiva para alterar ou cancelar o contrato": "preco",
    "Cobrança de tarifas, taxas, valores não previstos / não informados": "preco",
    "Cobrança em duplicidade / Cobrança referente a pagamento já efetuado": "preco",
    "Cobrança por serviço/produto não contratado / não reconhecido / não solicitado": "preco",
    "Cobrança por serviço não fornecido/ em desacordo com a utilização / fora do prazo": "preco",
    "Venda casada": "preco",
    "SAC - Demanda não resolvida / não respondida / respondida após o prazo": "atendimento",
    "SAC - Dificuldade para cancelar o serviço": "atendimento",
    "SAC - Dificuldade de contato / acesso": "atendimento",
    "SAC - Descortesia / despreparo / demora": "atendimento",
    "SAC - Dificuldade em obter protocolo, gravação ou histórico": "atendimento",
    "Dificuldade de contato / acesso a outros canais (exceto SAC)": "atendimento",
    "Dificuldade de contato / demora no atendimento": "atendimento",
    "Má qualidade no atendimento presencial ou outros canais (exceto SAC)": "atendimento",
    "Má qualidade no atendimento (descortesia / despreparo/ constrangimento)": "atendimento",
    "Informações incompletas / inadequadas sobre o serviço": "atendimento",
    "Dificuldade / demora para alterar o contrato de serviço (alteração de voo)": "atendimento",
    "Dificuldade / demora para cancelar o serviço": "atendimento",
    "Dificuldade para alterar ou cancelar o contrato /serviço": "atendimento",
    "Dificuldade / demora para alterar o nome do passageiro": "atendimento",
}
TEMAS = ["atraso/cancelamento", "bagagem", "reembolso", "canais de venda/app", "atendimento", "pontos/resgate",
         "preco", "outro"]


def _para_part(url, part, tamanho, y):
    """Baixa url em part até ter `tamanho` bytes; retoma com Range só do próprio .part."""
    reiniciou = False
    for _ in range(6):  # o servidor da ANAC corta conexões longas
        feito = part.stat().st_size if part.exists() else 0
        if feito > tamanho:
            part.unlink()
            feito = 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={feito}-"} if feito else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if feito and r.status != 206:  # servidor ignorou o Range: recomeça do zero
                    feito = 0
                with open(part, "ab" if feito else "wb") as f:
                    while bloco := r.read(1 << 20):
                        f.write(bloco)
        except urllib.error.HTTPError as e:
            if e.code != 416 or reiniciou:
                raise SystemExit(f"{y}: HTTP {e.code} no download; rode de novo com --force") from e
            part.unlink(missing_ok=True)  # 416: o .part não corresponde ao arquivo remoto
            reiniciou = True
        except OSError as e:  # URLError e queda de conexão
            print(f"{y}: conexão caiu em {part.stat().st_size if part.exists() else 0} bytes ({e}); retomando")
        if part.exists() and part.stat().st_size == tamanho:
            return
    raise SystemExit(f"{y}: download incompleto em {part}; rode de novo (retoma) ou use --force")


def baixar(force=False):
    BRONZE.mkdir(parents=True, exist_ok=True)
    for y in ANOS:
        alvo = BRONZE / f"dadosconsumidor{y}.csv"
        part = alvo.with_name(alvo.name + ".part")
        if alvo.exists() and not force:
            print(f"{y}: bronze local ({alvo.stat().st_size / 1e6:.1f} MB), sem acesso à rede")
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(URL.format(y=y), method="HEAD"), timeout=60) as r:
                tamanho = int(r.headers["Content-Length"])
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            print(f"{y}: não publicado (404)")
            continue
        except OSError as e:  # sem rede
            if not any(BRONZE.glob("dadosconsumidor*.csv")):
                raise SystemExit(f"sem rede ({e}) e sem bronze em {BRONZE}: não há o que processar") from e
            print(f"AVISO {y}: sem rede ({e}); seguindo com o bronze local")
            continue
        if alvo.exists() and alvo.stat().st_size == tamanho:
            print(f"{y}: bronze igual ao remoto ({tamanho / 1e6:.1f} MB)")
            continue
        if alvo.exists() or force:  # republicação ou --force: nunca anexa ao arquivo antigo
            part.unlink(missing_ok=True)
        _para_part(URL.format(y=y), part, tamanho, y)
        part.replace(alvo)
        print(f"{y}: baixado ({tamanho / 1e6:.1f} MB)")


def silver(con):
    arqs = sorted(BRONZE.glob("dadosconsumidor*.csv"))
    assert arqs, "bronze vazio: rode o download"
    lista = ", ".join(f"'{a.as_posix()}'" for a in arqs)
    emp = " ".join(f"WHEN \"Nome Fantasia\" = '{k}' THEN '{v}'" for k, v in EMPRESAS.items())
    con.execute("CREATE OR REPLACE TABLE de_para (problema VARCHAR, tema VARCHAR)")
    con.executemany("INSERT INTO de_para VALUES (?, ?)", list(PROBLEMA_TEMA.items()))
    # 1ª linha do arquivo é "Atualizado em: ..." (skip=1); só colunas sem dado do consumidor são lidas.
    con.execute(f"""
        CREATE OR REPLACE TABLE s AS
        WITH r AS (
          SELECT strftime(CAST("Data Abertura" AS DATE), '%Y-%m') AS ano_mes, "Nome Fantasia",
                 "Grupo Problema" AS grupo_problema, trim("Problema") AS problema, "Respondida" AS respondida,
                 "Avaliação Reclamação" AS avaliacao, TRY_CAST("Nota do Consumidor" AS INTEGER) AS nota,
                 TRY_CAST("Tempo Resposta (em dias)" AS INTEGER) AS tempo_resposta_dias
          FROM read_csv([{lista}], skip=1, header=true, delim=';', quote='"',
                        all_varchar=true, nullstr='null'))
        SELECT ano_mes, CASE {emp} ELSE 'OUTRAS' END AS empresa, grupo_problema, r.problema,
               coalesce(d.tema, 'outro') AS tema, respondida = 'S' AS respondida, avaliacao, nota,
               tempo_resposta_dias
        FROM r LEFT JOIN de_para d USING (problema) WHERE ano_mes >= '{MES_INI}'
        ORDER BY ano_mes, empresa""")
    SILVER.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY s TO '{SILVER.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")


def gold(con):
    con.execute(f"""
        CREATE OR REPLACE TABLE g AS
        SELECT empresa, tema, ano_mes,
               COUNT(*)::BIGINT AS reclamacoes,
               COUNT(nota)::BIGINT AS avaliadas,
               ROUND(AVG(nota), 2)::DECIMAL(4,2) AS nota_media,
               ROUND(100.0 * COUNT(*) FILTER (WHERE avaliacao = 'Resolvida')
                     / NULLIF(COUNT(*) FILTER (WHERE avaliacao IN ('Resolvida', 'Não Resolvida')), 0), 2
                    )::DECIMAL(6,2) AS pct_resolvidas,
               ROUND(100.0 * COUNT(*) FILTER (WHERE nota <= 2) / NULLIF(COUNT(nota), 0), 2)::DECIMAL(6,2)
                   AS pct_insatisfeitos,
               ROUND(100.0 * COUNT(*) FILTER (WHERE respondida) / COUNT(*), 2)::DECIMAL(6,2) AS pct_respondidas,
               ROUND(AVG(tempo_resposta_dias), 2)::DECIMAL(6,2) AS tempo_resposta_medio_dias
        FROM read_parquet('{SILVER.as_posix()}')
        GROUP BY ALL ORDER BY empresa, tema, ano_mes""")
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY g TO '{GOLD.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    dup = con.execute("SELECT COUNT(*) FROM (SELECT 1 FROM g GROUP BY empresa, tema, ano_mes HAVING COUNT(*) > 1)")
    assert dup.fetchone()[0] == 0, "grão duplicado"


def main():
    baixar("--force" in sys.argv)
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    assert set(PROBLEMA_TEMA.values()) < set(TEMAS)
    silver(con)
    gold(con)
    for c in ["silver_consumidor_aereo.yaml", "gold_friction_themes.yaml"]:
        erros = checar_contrato(ROOT / "contracts" / c, con=con)
        assert not erros, f"{c}: {erros}"
    print(con.execute("SELECT MIN(ano_mes), MAX(ano_mes), COUNT(*) FROM s").fetchone())
    print(con.execute("SELECT empresa, tema, SUM(reclamacoes) n FROM g GROUP BY ALL ORDER BY 1, 3 DESC").df()
          .to_string(index=False))


if __name__ == "__main__":
    main()
