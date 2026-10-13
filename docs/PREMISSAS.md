# Premissas

## P-01 · Janela temporal das fontes ANAC (registrada em 2026-10-09)
- Janela alvo: 2024-10 a 2026-09 (24 meses até a data do projeto).
- Janela real ingerida: **2024-09 a 2026-08** (24 meses) para as duas fontes. Em 2026-10-09 o mês 2026-09 ainda
  não estava publicado (HTTP 404 em tarifas e VRA). A janela termina no último mês publicado <= `ANAC_END_MONTH`
  (`.env`) e volta 24 meses (`ANAC_MONTHS`).
- Meses faltantes dentro da janela: **nenhum**.
- Fonte: listagens oficiais `https://sas.anac.gov.br/sas/tarifadomestica/{ano}/` e
  `https://siros.anac.gov.br/siros/registros/diversos/vra/{ano}/`.

## P-02 · Regra de rota doméstica
- Rota doméstica = origem **e** destino com prefixo ICAO brasileiro: `SB`, `SD`, `SI`, `SJ`, `SN`, `SS`, `SW`.
- Aplicada na conversão bronze -> silver das duas fontes. Bronze fica bruto (inclui voos internacionais do VRA).
- Tarifas: o arquivo já é só doméstico; o filtro não removeu nenhuma linha.
- VRA: removidas 370.017 etapas (18,3% do bronze) com ao menos uma ponta fora do Brasil.
- O silver VRA ainda contém `tipo_linha` C (cargueiro, 30.954), G (4.128) e I (2.289 etapas domésticas de linhas
  internacionais). Os modelos gold de passageiro devem filtrar `tipo_linha = 'N'` (único código de passageiro doméstico presente na janela; 243 linhas têm tipo nulo).

## P-03 · Atraso e voos não programados no VRA
- `atraso_*_min` = real - previsto, em minutos, como publicado (sem ajuste de fuso).
- 35.030 etapas REALIZADO têm `partida_prevista` nula: são etapas não programadas (`codigo_di` diferente de 0:
  extras, retornos, alternados). Na origem já vêm sem horário previsto; ficam com atraso nulo. A taxa de atraso
  > 30 min deve usar só `codigo_di = '0'`.
- Cancelado = `situacao_voo = 'CANCELADO'` (35.620 etapas no silver).

## P-04 · Layout variável das tarifas ANAC
- 2024-10 a 2025-02 publicados com cabeçalho `ANO;MES;EMPRESA;ORIGEM;DESTINO;TARIFA;ASSENTOS`; demais meses com
  `nr_ano_referencia;...;nr_assentos`. Os dois mapeiam para o mesmo schema silver.
- Decimal varia (`750,00`, `600.0`): com vírgula, a vírgula é o decimal e o ponto é o separador de milhar; sem
  vírgula, o ponto é o decimal. Nenhuma tarifa ficou nula na conversão.
- O arquivo de 2026-05 foi publicado como `202605 (1).csv`; a descoberta é feita pela listagem do diretório.
- Silver mantém todas as empresas (TAM, AZU, GLO + regionais ABJ, CQB, PTB); o recorte AZU/GLO/TAM é feito na gold.
