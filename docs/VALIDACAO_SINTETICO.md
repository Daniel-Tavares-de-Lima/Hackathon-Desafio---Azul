# Validação do sintético contra fontes públicas

Gerado por `pipelines/synthetic/generate.py` (seed 20261017). Erro % = 100 × (sintético − público) / público.
Comparação sobre os 10 maiores pares (`par_rota`, dois sentidos somados) por assentos vendidos pela Azul (silver.anac_tarifas, AZU), janela 2024-09 a 2026-08.
O sintético usa 50.000 clientes e todas as viagens geradas (histórico + rótulo). Ver premissas P-06 a P-14 e a circularidade (P-06).

| Par | Tarifa pública (R$) | Tarifa sint. (R$) | Erro % | Share do par no total Azul (pub.) | Share sint. | Erro % | Azul no par (assentos Azul / mercado, pub.) | Atraso>30 pub. | Atraso>30 sint. | Erro % | Trechos sint. | Atraso esperado no mix sint. | Erro % vs esperado (ruído amostral) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SBRJ-SBSP | 470.85 | 470.35 | -0.1% | 2.88% | 2.31% | -19.6% | 23.3% | 8.50% | 9.11% | +7.2% | 15980 | 8.69% | +4.8% |
| SBGR-SBRF | 629.32 | 619.53 | -1.6% | 2.79% | 2.25% | -19.2% | 50.3% | 7.03% | 7.33% | +4.3% | 15575 | 7.24% | +1.2% |
| SBGR-SBPA | 411.82 | 409.84 | -0.5% | 1.93% | 1.05% | -45.7% | 50.7% | 6.79% | 7.14% | +5.1% | 7261 | 7.05% | +1.3% |
| SBRF-SBSP | 689.82 | 682.08 | -1.1% | 1.91% | 1.61% | -15.8% | 42.7% | 8.79% | 9.23% | +5.0% | 11133 | 9.12% | +1.2% |
| SBCF-SBSP | 441.61 | 433.43 | -1.9% | 1.69% | 1.93% | +14.3% | 28.1% | 10.31% | 10.75% | +4.3% | 13337 | 10.29% | +4.5% |
| SBPA-SBSP | 402.94 | 392.06 | -2.7% | 1.68% | 0.96% | -43.0% | 27.3% | 7.46% | 7.68% | +3.0% | 6621 | 7.82% | -1.9% |
| SBBR-SBSP | 420.24 | 403.01 | -4.1% | 1.65% | 1.06% | -36.0% | 22.2% | 8.45% | 8.44% | -0.0% | 7297 | 8.61% | -1.9% |
| SBGL-SBRF | 666.45 | 654.03 | -1.9% | 1.63% | 1.29% | -21.1% | 48.3% | 8.12% | 7.42% | -8.6% | 8910 | 7.46% | -0.5% |
| SBCT-SBPA | 397.65 | 405.62 | +2.0% | 1.36% | 0.91% | -32.9% | 67.7% | 8.11% | 8.39% | +3.4% | 6282 | 8.13% | +3.1% |
| SBBR-SBKP | 465.70 | 472.86 | +1.5% | 1.28% | 1.50% | +17.1% | 59.2% | 8.61% | 8.17% | -5.1% | 10347 | 8.53% | -4.2% |

- Tarifa média global: público R$ 694.40; sintético R$ 705.56 (+1.6%).
- Atraso > 30 min global (voos realizados): público 8.20%; sintético 8.21% (+0.2%).
- Cancelamento global: público 2.04%; sintético 1.78% (-12.8%).

**Erros acima de 5% e causas:** (1) *Share do par* (-46% a +17%): casa sorteada por voos do VRA e destino por assentos de tarifas; a razão voos/assentos por aeroporto (tabela abaixo) faz hubs (SBKP, SBCF) pesarem mais e SBSP, SBGR, SBBR, SBGL e SBPA menos que no público. Efeito pedido (hubs aparecem mais), não corrigido. (2) *Atraso > 30 min* (até ±8,6%): mistura de dois efeitos medidos nas duas últimas colunas; o mix rota-mês do sintético segue as vendas (mês da compra), não os voos, e o sorteio tem ruído binomial (cerca de 2,5% a 3,6% relativo, 1 desvio-padrão, nos pares com 7 a 16 mil trechos). O erro contra o esperado no mix fica em ±4,8%. (3) *Cancelamento global* (-12,8%): a taxa pública é ponderada por voos; o sintético pondera por passageiros, que se concentram em rotas de maior frequência e menor cancelamento. A tarifa média dos 10 pares fica dentro de ±5% (maior erro -4,1%).

**Sobre a coluna 'Azul no par':** é a participação da Azul entre as companhias do par (público). O sintético tem só clientes da Azul e nenhum concorrente, então ela não é reproduzível por construção e vai apenas como contexto. O que o sintético reproduz é o peso do par no total de trechos da Azul, comparado ao peso do par no total de assentos da Azul (coluna 'Share do par').

## Aeroporto de casa x voos da Azul no VRA (histórico)

| Aeroporto | Share de voos Azul (VRA, tipo N, DI 0, 2024-09 a 2026-02) | Share de clientes (casa) |
|---|---|---|
| SBKP | 17.72% | 17.90% |
| SBCF | 13.78% | 13.72% |
| SBRF | 8.70% | 8.57% |
| SBSP | 4.87% | 4.86% |
| SBCT | 4.05% | 4.08% |

Aeroportos dos 10 pares: peso na casa dos clientes x peso nos assentos da Azul com origem no aeroporto (silver.anac_tarifas, só entre aeroportos-casa). A razão voos/assentos explica por que o share do par no sintético difere do público (ver 'Share' acima): os pares com SBSP, SBGR e SBPA têm menos voos Azul no VRA do que assentos vendidos em tarifas.

| Aeroporto | Share de voos Azul (VRA) | Share de assentos de origem (tarifas) | Razão voos/assentos |
|---|---|---|---|
| SBBR | 2.29% | 3.72% | 0.62 |
| SBCF | 13.78% | 7.91% | 1.74 |
| SBCT | 4.05% | 4.41% | 0.92 |
| SBGL | 2.41% | 4.09% | 0.59 |
| SBGR | 3.30% | 4.89% | 0.68 |
| SBKP | 17.72% | 9.75% | 1.82 |
| SBPA | 3.21% | 5.50% | 0.58 |
| SBRF | 8.70% | 8.72% | 1.00 |
| SBRJ | 3.11% | 3.78% | 0.82 |
| SBSP | 4.87% | 6.42% | 0.76 |

## Cobertura das ameaças (clientes distintos)

Eventos por tipo e período (A = sorteado por viagem; B e C = pares reais de `gold.route_exits` e `gold.route_competition` em que o cliente voou nos 12 meses até o mês da ameaça):

| Tipo | Detalhe | Período | Eventos | Clientes |
|---|---|---|---|---|
| A | atraso_30 | historico | 41960 | 20451 |
| A | atraso_30 | rotulo | 13793 | 9359 |
| A | cancelamento | historico | 9690 | 7325 |
| A | cancelamento | rotulo | 2618 | 2325 |
| B | reducao | historico | 2861 | 2840 |
| B | reducao | rotulo | 4218 | 3912 |
| B | saida_total | historico | 953 | 932 |
| B | saida_total | rotulo | 155 | 154 |
| C | queda_tarifa | historico | 2191 | 2161 |
| C | queda_tarifa | rotulo | 2316 | 2289 |

Clientes distintos atingidos (qualquer período): A 26082, B 7093, C 3800 de 50000.

Por nível vigente em 28/02/2026 (histórico = ameaças até 2026-02; todos = inclui mar-ago/2026):

| Nível | Clientes | A hist. | B hist. | C hist. | A todos | B todos | C todos |
|---|---|---|---|---|---|---|---|
| Diamante Unique | 242 | 242 | 19 | 11 | 242 | 33 | 14 |
| Diamante | 1416 | 1384 | 128 | 84 | 1397 | 246 | 131 |
| Safira | 9667 | 8286 | 992 | 632 | 8779 | 2001 | 1100 |

## Efeitos da evasão recuperáveis nos dados (diagnóstico bruto, sem controle de confundidores)

| Condição (histórico, entre quem viajou) | Clientes | Evasão com a condição | Evasão sem a condição |
|---|---|---|---|
| saída total na rota favorita | 175 | 63.4% | 40.0% |
| redução na rota favorita | 2277 | 44.0% | 39.8% |
| queda de tarifa na rota favorita | 1734 | 43.9% | 39.9% |
| perto de perder o nível | 8677 | 32.0% | 42.2% |
| cancelamento nos últimos 6 meses | 2225 | 28.7% | 40.7% |
| atraso > 30 min nos últimos 6 meses | 10830 | 27.5% | 44.5% |

As diferenças brutas misturam o efeito injetado com confundidores (ex.: quem tem atraso viaja mais; quem perde nível viaja menos).

## Proxy do arquétipo nas tabelas de entrada

Distância de variação total média entre P(arquétipo | valor da coluna) e P(arquétipo) (0 = a coluna não informa nada sobre o arquétipo; 1 = proxy perfeito): aeroporto_casa 0.0231, consentimento_marketing 0.0026. As colunas de comportamento (frequência, antecedência, tarifa) são correlacionadas ao arquétipo por construção, mas as classes se sobrepõem (Gamma, ruído) e nenhuma coluna o identifica sozinha.

Tempo total de execução: 16 s.
