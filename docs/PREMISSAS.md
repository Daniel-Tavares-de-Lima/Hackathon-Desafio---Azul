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

## P-05 · Regras das tabelas gold de ameaça (registrada em 2026-10-12)
- Rota é direcional (origem→destino); mês é o mês do arquivo ANAC (`ano_mes`), não o da partida.
- **Atraso (A):** partida_real − partida_prevista > 30 min, sobre voos REALIZADOS, só `tipo_linha='N'` e `codigo_di='0'` (P-02, P-03). % de atraso = atrasados / realizados.
- **Saída total (B) (refinada em 2026-10-12):** avaliada no **par** (`par_rota` = os dois aeroportos em ordem alfabética, dois sentidos somados). Marca quando o par teve **≥ 30 voos da Azul nos mesmos 3 meses do ano anterior** (m-14..m-12; descarta rota sazonal e rota de baixa frequência) e **zero em m-2..m**. `mes_saida` = primeiro mês zerado (mês seguinte ao último voo da Azul no par), preenchido só quando `saida_total`. A flag é igual nos dois sentidos e persiste enquanto as duas condições valem, o que na prática limita a saídas dos últimos ~12 meses; use `mes_saida` para separar recente de antiga e conte pares com `COUNT(DISTINCT par_rota)` no último mês da janela. O piso de 30 voos e a exigência do ano anterior vêm do produto, não de fonte pública.
- **Redução (B):** voos em m-2..m ≤ 70% dos voos nos mesmos 3 meses do ano anterior (base > 0). Compara janelas de 3 meses, não o mês isolado, para não marcar sazonalidade de um mês só. Sem piso de volume mínimo: rotas de baixa frequência oscilam; filtrar por `voos_3m_ano_anterior` no consumo.
- **Voo da Azul:** só `empresa_icao='AZU'`; codeshare operado pela Azul conta como voo da Azul; Azul Conecta e outras regionais não entram.
- **Entrada de concorrente (C):** companhia ≠ AZU com venda no mês e nenhuma nos 3 meses anteriores; só avaliável a partir do 4º mês da janela. A base de tarifas da ANAC inclui venda esporádica de regionais; sem piso de assentos.
- **Queda de tarifa (C) (referência anual, 2026-10-12):** compara a tarifa média ponderada do mês com a do **mesmo mês do ano anterior**, no **par_rota** (dois sentidos somados), para o concorrente e para a Azul. Marca o concorrente (≠ AZU) quando a variação anual dele é **< 0** e **≥ 15 pp abaixo** da variação anual da Azul no mesmo par e mês (`diferenca_anual_pp <= -15`). Azul e concorrente caindo juntos é sazonalidade e não marca. Substitui a referência de 3 meses anteriores; `tarifa_media_3m_anteriores` e `variacao_tarifa_pct` (3 meses, por rota direcional) ficam só como informação e não entram na flag. Sem venda da Azul ou do concorrente no mês de um ano atrás não há referência e não marca; por isso a flag só existe a partir de 2025-10 (12 meses de histórico + 1 de persistência).
- **Queda de tarifa (C) (filtros, 2026-10-12):** (1) **materialidade**: concorrente e Azul com ≥ 1.000 assentos no par, no mês e no mesmo mês do ano anterior; (2) **referência estável**: variação anual da Azul entre −30% e +30%; (3) **persistência** no nível do par e do concorrente: marca o mês m se a condição completa valeu em m e em m-1 (meses consecutivos), nunca o 1º mês da sequência. A flag é igual nos dois sentidos do par. `revisar_amostra` usa a mesma lógica, mas com a variação anual da Azul fora de −30%..+30% em m ou m-1; nesse caso não se marca queda. As duas flags nunca são verdadeiras juntas. Limiares 1.000 assentos, 2 meses e ±30% vêm do produto, sem fonte pública.
- **Ranking de concorrência (C) por exposição da Azul:** por par, assentos vendidos pela Azul nos últimos 3 meses da janela (dois sentidos) × maior `-diferenca_anual_pp` entre as quedas marcadas nesses 3 meses, em fração (pp/100). Unidade: assentos "expostos" equivalentes. Entradas de concorrente não entram no ranking.
- Fonte que calibra: ANAC VRA e Tarifas Aéreas Domésticas (URLs em P-01); limiares 30 min, 30%, 15% e 3 meses vêm da especificação de produto do ÓRBITA.
