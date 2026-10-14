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

## P-06 · Base sintética: escopo, janelas e circularidade (2026-10-13)
- Gerador: `pipelines/synthetic/generate.py`, seed fixa `20261017` (`numpy.random.default_rng`), 50.000 clientes. IDs são UUID v4 derivados da seed (reprodutíveis; duas execuções geram Parquet idêntico byte a byte). Execução completa em cerca de 16 s.
- Janelas (índice de mês 0 = 2024-09): **histórico** = voos de 2024-09 a 2026-02 (18 meses, corte em 2026-02-28); **rótulo** = voos de 2026-03 a 2026-08 (6 meses). A janela coincide com a janela real das fontes ANAC (P-01).
- Fontes de calibração (todas públicas, já ingeridas): `silver.anac_tarifas` (empresa AZU), `silver.anac_vra`, `gold.route_disruptions`, `gold.route_exits`, `gold.route_competition`. As gold e as SQL não foram alteradas; o gerador só lê.
- **Circularidade (leia antes de avaliar modelos):** é um sintético por construção. Os efeitos de evasão (P-13), a mistura de arquétipos (P-07) e a taxa de pontos (P-11) são **premissas do gerador**, sem fonte pública que as calibre. Um modelo que "descobre" esses efeitos apenas devolve as regras que o gerador usou; a métrica em holdout temporal mede a capacidade de recuperar as regras sob ruído, não desempenho sobre clientes reais. Só as marginais (tarifa, share por rota, atraso, cancelamento, casa por aeroporto) são calibradas em dado público; ver `docs/VALIDACAO_SINTETICO.md`.
- Proibido e ausente: nome, CPF, e-mail, gênero, raça e idade. Nenhuma coluna das tabelas lidas pelo modelo contém o arquétipo (P-07, P-14).
- Tabelas de saída em `data/silver/synthetic_*` (contratos em `contracts/synthetic_*.yaml`).

## P-07 · Arquétipos latentes e frequência de compra
- Cinco arquétipos em mistura, usados só para gerar comportamento: corporativo frequente 8%, lazer premium 10%, regional dependente 18%, em ascensão 15%, ocasional 49%. **Sem fonte pública**: pesos de produto, escolhidos para dar base com poucos clientes de alto nível (ver P-11) e maioria ocasional.
- Frequência: processo de Poisson sobre **eventos de compra** (cada evento = ida e, com 90%, volta). Taxa individual λ_i ~ Gamma(forma 1,5; escala = média do arquétipo / 1,5), para dar heterogeneidade dentro do arquétipo (assim os arquétipos se sobrepõem). Médias de eventos por mês: corporativo 1,0; lazer premium 0,30; regional 0,50; em ascensão 0,30; ocasional 0,12. **Sem fonte pública** (premissa de produto).
- Em ascensão: multiplicador da taxa 0,5 + 0,08 × (mês da compra), piso 0,1 (a taxa mais que quadruplica de 2024-09 a 2026-08), para o CLV futuro crescer.
- Estadia (dias entre ida e volta) = mínimo + Poisson(média): corporativo 1+1,5; lazer premium 3+5; regional 2+3; ascensão 2+3; ocasional 2+4. Antecedência da compra (dias) = lognormal com mediana 7/45/14/20/25 (mesma ordem) e sigma 0,7/0,6/0,7/0,7/0,8, truncada em 0..330. Premissas de produto.
- Rotas favoritas: cada cliente tem 1 a 3 destinos favoritos (probabilidades de 1/2/3 favoritas: corporativo 0,6/0,3/0,1; lazer 0,2/0,3/0,5; regional 1/0/0; ascensão 0,4/0,4/0,2; ocasional 0,6/0,3/0,1), com pesos 0,6/0,3/0,1 entre elas. Lazer premium sorteia favoritas com peso extra pela tarifa média da rota (expoente 1). Premissas de produto.
- O arquétipo é gravado só em `synthetic_archetypes_validacao`, e nenhuma outra tabela o contém (asserção no gerador). O aeroporto de casa e o consentimento são sorteados independentemente do arquétipo; a distância de variação total entre P(arquétipo | coluna) e P(arquétipo) é de 0,023 (casa) e 0,003 (consentimento), registrada no relatório de validação.

## P-08 · Aeroporto de casa e rotas
- **Casa:** sorteada proporcionalmente aos voos da Azul no VRA (`empresa_icao='AZU'`, `tipo_linha='N'`, `codigo_di='0'`, REALIZADO ou CANCELADO, 2024-09 a 2026-02), restrita aos aeroportos que também têm vendas da Azul em tarifas como origem (107 aeroportos). Hubs aparecem mais (SBKP 17,9%, SBCF 13,7%, SBRF 8,6% dos clientes).
- **Destino:** entre os favoritos do cliente, com peso proporcional ao índice sazonal da rota no mês da compra = assentos da Azul vendidos na rota direcional (casa→destino) naquele mês / média mensal da rota (teto 3). Os favoritos são sorteados pelo total de assentos da Azul na rota direcional (`silver.anac_tarifas`). A taxa de compra do cliente no mês também é multiplicada por esse índice (média ponderada das favoritas), o que reproduz a sazonalidade e a tendência de venda de cada rota.
- **Rota sem oferta da Azul (ex.: saída total):** a Azul não vende nem voa no par a partir de `mes_saida` (menor `mes_saida` de `gold.route_exits` com `saida_total`). Se nenhuma favorita está disponível no mês, a demanda segue a sazonalidade da rede; o evento é remarcado para outro destino da mesma casa com probabilidade 0,60, e perdido caso contrário (2.740 eventos perdidos). Eventos com voo depois da saída ou fora da janela são descartados (voos a partir de 2026-09 não existem na janela).
- **Aquecimento:** como a tarifa da ANAC é indexada pelo mês da **venda**, os eventos são gerados na data da compra e o voo ocorre na compra + antecedência. São simulados 4 meses de compra antes de 2024-09 (usando os pesos e tarifas de 2024-09) para que os voos de set/out de 2024 não fiquem subpopulados. Limitação: compras com antecedência acima de 4 meses antes de 2024-09 não existem.
- **Limitação do share por par:** casa ∝ voos (VRA) e destino ∝ assentos (tarifas) fazem o peso do par diferir do peso público, porque a razão voos/assentos varia por aeroporto (SBKP 1,82, SBCF 1,74, SBBR 0,62, SBPA 0,58). Erros de 14% a 46% no share dos 10 maiores pares estão explicados em `docs/VALIDACAO_SINTETICO.md`; não foram corrigidos para não violar a regra de casa ∝ voos.
- Pares usam `par_rota` (dois aeroportos em ordem alfabética), como nas gold (P-05).

## P-09 · Tarifa e antecedência
- A tarifa de cada trecho é sorteada da **distribuição empírica** de `silver.anac_tarifas` (empresa AZU, par_rota, mês da venda), ponderada por assentos (CDF por par × mês). Rota direcional e par compartilham a mesma distribuição (os dois sentidos somados, como no par das gold). Ida e volta são comprados juntos, no mesmo mês de venda, com sorteios independentes.
- **A antecedência afeta o preço** por cópula gaussiana: z = normal-padrão da posição (ranking) de ln(1 + antecedência); o quantil sorteado da CDF é Φ(ρ·z + √(1 − ρ²)·ε), com **ρ = −0,30** (antecedência maior, tarifa menor). A cópula mantém a marginal exatamente uniforme (a distribuição de tarifa por par × mês fica a da ANAC). O valor ρ é uma premissa de produto: o microdado da ANAC não traz antecedência, então não há fonte pública que o calibre. Antecedência da volta = da ida + estadia.
- Tarifa sem taxas de embarque (como na ANAC).

## P-10 · Atrito: atraso e cancelamento
- Cancelamento ~ Bernoulli(`pct_cancelado`/100) e, se não cancelou, atraso > 30 min ~ Bernoulli(`pct_atraso_30`/100) da rota direcional da Azul no **mês do voo** (`gold.route_disruptions`, empresa AZU). Rota-mês sem dado usa a média da rota; sem rota, a taxa global da Azul no mês.
- Minutos de atraso: quantis da distribuição empírica da Azul no VRA (`tipo_linha='N'`, `codigo_di='0'`, REALIZADO), em duas piscinas (> 30 min e ≤ 30 min, incluindo adiantamentos), 200 quantis entre 0,25% e 99,75% (cauda truncada).
- Voo cancelado: mantém a linha em `synthetic_viagens` (`cancelado = true`, sem atraso), **não conta** para trechos, gasto aéreo, viagem realizada nem CLV (premissa: reembolsado ou remarcado fora do escopo). A taxa do cliente nesta rota-mês independe do perfil do cliente.

## P-11 · Programa de fidelidade: regras de nível
- Regras por **ano calendário**, usando trechos voados (não cancelados), gasto aéreo (soma das tarifas) e pontos qualificáveis (derivados do gasto):
  - Topázio: 6 trechos **ou** 6.000 pontos qualificáveis.
  - Safira: 10 trechos **ou** 10.000 pontos.
  - Diamante: (12 trechos **e** 12.000 pontos) **ou** R$ 25.000 em gastos aéreos.
  - Diamante Unique: (26 trechos **e** 26.000 pontos) **ou** R$ 50.000.
- **Fontes** (localizadas pelo time; não confirmei o conteúdo de cada página para este registro, cada limiar foi usado como informado no pedido): `https://www.serasa.com.br/credito/blog/azul-fidelidade`; `https://www.mercadoeeventos.com.br/noticias/aviacao/azul-muda-o-nome-altera-forma-de-qualificacao-e-reformula-seu-programa-de-fidelidade/`; `https://www.melhorescartoes.com.br/mudancas-azul-fidelidade-qualificacao.html`; `https://passageirodeprimeira.com/mudancas-programa-fidelidade-azul`.
- **O site oficial da Azul não foi confirmado** e as fontes divergem em detalhes. Uma fonte traz Diamante com "2 trechos", tratado como erro de digitação (usado 12). Diamante Unique está em vigor desde 13/01/2026; a mesma regra é aplicada a todos os anos do sintético (2024, 2025 e 2026) como simplificação.
- **Pontos qualificáveis** não existem na fonte pública por viagem. Derivação: `pontos = gasto aéreo × 0,5 × m_cliente × r_ano`, arredondado, com ruído lognormal `m_cliente` (sigma 0,10, fixo por cliente) e `r_ano` (sigma 0,08, por cliente e ano). **Taxa 0,5 ponto por R$**: calibrada na equivalência entre o limiar de pontos e o de gasto nas próprias regras (12.000 pontos ≈ R$ 25.000 para Diamante, razão 0,48; 26.000 ≈ R$ 50.000 para Unique, razão 0,52). Não é taxa oficial; é premissa de produto.
- **Nível alcançado** (`nivel_alcancado`) é o maior nível atingido no ano até `referencia_ate`; **2024** cobre só set a dez (histórico começa em 2024-09, `ano_completo = false`) e **2026** só jan e fev (corte do histórico, nada de mar a ago entra). **Nível vigente** (`nivel_vigente`) = maior entre o alcançado no ano e o do ano anterior. Simplificação nossa (o nível vale até o fim do ano seguinte), não confirmada nas fontes.
- Distâncias: `folga_pct_nivel_alcancado` = quanto o cliente excede o limite do nível alcançado, no caminho mais folgado (0,25 = 25% acima do limite; 0 = no limite; vazio se sem nível); `falta_pct_proximo_nivel` e `faltam_trechos/pontos/gasto_*_proximo` = quanto falta para o próximo nível no caminho mais próximo (vazio no topo, ou no que o caminho não exige). "Perto de perder o nível" = folga < 25% (P-13).

## P-12 · Ameaças (A, B, C) e tabela `synthetic_customer_threats`
- Uma linha = cliente × tipo × mês × par (`par_rota`). Colunas `periodo` (`historico` se o mês <= 2026-02, senão `rotulo`) e `detalhe` (atraso_30, cancelamento, reducao, saida_total, queda_tarifa).
- **A:** cada trecho cancelado ou com atraso de partida > 30 min (sorteio de P-10) gera um evento, na data do voo, com `viagem_id`.
- **B:** `gold.route_exits` por `par_rota` e mês. *Saída total:* o cliente voou o par nos 12 meses até o mês anterior a `mes_saida`; o evento cai em `mes_saida` (um por cliente e par). *Redução:* a flag `reducao` em qualquer sentido do par; o cliente voou o par nos 12 meses até o mês marcado; um evento por episódio (meses consecutivos), no primeiro mês marcado em que o cliente já era exposto.
- **C:** `queda_tarifa` em `gold.route_competition` por par e mês, mesma regra de exposição e episódio da redução (12 meses, um evento por episódio).
- A janela de 12 meses de exposição e o "um evento por episódio" são regras de produto, sem fonte pública.
- **Cobertura, sem inflar:** B e C só existem onde as gold aprovadas marcam (C: 13 pares e 18 pares-mês; saída total só a partir de 2025-11, com `mes_saida` entre 2024-11 e 2026-06; redução a partir de 2025-11). Redução só aparece a partir de 2025-11 e queda de tarifa a partir de 2025-10 (as flags precisam de 12 meses de histórico); saída total tem eventos desde `mes_saida` = 2024-11, mas só pares que as gold marcam (a flag só é visível desde 2025-11). Antes disso a ausência de ameaça B/C é limitação das gold, não do comportamento, e vale também para o sintético. Os números por tipo estão em `docs/VALIDACAO_SINTETICO.md`. O gerador não cria ameaça B ou C fora dessas flags.
- Origem e destino ficam preenchidos só em A (sentido do voo); em B e C a granularidade é o par.

## P-13 · Evasão, rótulos e efeitos (todos com ruído)
- **Rótulo `evasao`** (`synthetic_rotulos`): para quem tem **pelo menos 1 trecho voado (não cancelado) no histórico** (voo de 2024-09-01 a 2026-02-28), `evasao = 1` se **não há nenhum trecho voado entre 2026-03-01 e 2026-08-31**, senão `0`. Quem **nunca voou no histórico** tem `evasao` nulo (sem comportamento para perder; `viajou_no_historico = false`) e continua no `clv_futuro_6m_brl`. O rótulo é observado nos dados: parte dele é acaso de Poisson (cliente ocasional sem trecho em 6 meses) e parte vem do evento oculto abaixo.
- **`clv_futuro_6m_brl`** = soma da tarifa dos trechos voados (não cancelados) de 2026-03 a 2026-08. É receita aérea bruta de 6 meses, não margem nem valor descontado. `trechos_futuros_6m` é a contagem correspondente. Essas duas colunas e a tabela `synthetic_viagens_futuro` são **rótulo/holdout: nunca usar como entrada** (`synthetic_viagens` termina em 2026-02-28 e `synthetic_fidelidade` só usa o histórico, para não haver vazamento).
- **Evento oculto de parada** (não vai para nenhuma tabela): para quem viajou no histórico, `parou ~ Bernoulli(sigmoid(η))`; quem para não tem nenhum trecho a partir de 2026-03-01 (inclusive retornos). O rótulo `evasao` é então função do acaso de Poisson e de `parou`, nunca determinística das tabelas de entrada. Efeitos em `η`:

| Efeito | Valor em η (logit) | Direção | Justificativa / fonte |
|---|---|---|---|
| Intercepto do arquétipo | corporativo −2,6; lazer premium −2,0; regional −2,3; ascensão −2,8; ocasional −1,3 | arquétipo base menos fiel (ocasional) evade mais | Premissa de produto, sem fonte pública |
| Atraso > 30 min nos 6 últimos meses do histórico (2025-09 a 2026-02) | +0,20 por atraso, no máximo 3 | aumenta | Tese ÓRBITA, ameaça A; magnitude de produto. O VRA só dá a taxa, não o efeito |
| Cancelamento nesses 6 meses | +0,35 se houve ao menos 1 | aumenta | Idem |
| Saída total na rota favorita (evento B em 2025-09 a 2026-02) | +0,60 | aumenta | Ameaça B; magnitude de produto |
| Redução de voos na rota favorita (mesmo período) | +0,25 | aumenta | Idem |
| Queda de tarifa de concorrente na rota favorita (mesmo período) | +0,45 | aumenta | Ameaça C; magnitude de produto |
| Perto de perder o nível (nível alcançado em 2025, folga < 25% sobre o limite) | +0,35 | aumenta | Hipótese de produto (pedido do time), sem fonte pública |
| Volume: ln(1 + trechos voados nos 12 meses até o corte) − ln(1 + 8) | +0,10 por unidade | aumenta | **Seguindo o pedido** (volume aumenta a chance de parar). Ambíguo e contraintuitivo: o efeito líquido observado é negativo porque o acaso de Poisson faz quem voa pouco ficar mais tempo sem voar |
| Ruído individual | N(0; 0,6²) | simétrico | Para o modelo não "adivinhar" as regras |

- **Rota favorita** = par com mais trechos voados no histórico do cliente (empate: menor id de par); só ameaças na favorita entram em `η`. Ameaças da tabela em outros pares e no período de rótulo **não** alteram `parou`: o Radar não verá efeito causal de ameaça de mar a ago/2026, só ameaças do histórico.
- Efeito do volume, atraso e nível aparece **mascarado** nas taxas brutas (ver o diagnóstico em `docs/VALIDACAO_SINTETICO.md`): quem sofre atraso ou está perto de perder o nível voa mais, e quem voa mais evade menos por acaso.

## P-14 · Privacidade e LGPD no sintético
- Sem qualquer atributo pessoal. `consentimento_marketing` ~ Bernoulli(0,70), independente de tudo (premissa de produto; serve para exercitar o filtro LGPD no agente, não representa taxa real).
- O arquétipo e o evento oculto de parada nunca saem de `generate.py`, exceto `synthetic_archetypes_validacao` (só validação).
