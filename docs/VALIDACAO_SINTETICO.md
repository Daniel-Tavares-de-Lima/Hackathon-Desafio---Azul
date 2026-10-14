# Validação do sintético contra fontes públicas

Gerado por `pipelines/synthetic/generate.py` (seed 20261017). Erro % = 100 × (sintético − público) / público.
Comparação sobre os 10 maiores pares (`par_rota`, dois sentidos somados) por assentos vendidos pela Azul (silver.anac_tarifas, AZU), janela 2024-09 a 2026-08.
O sintético usa 50.000 clientes e todas as viagens geradas (histórico + rótulo). Ver premissas P-06 a P-14 e a circularidade (P-06).

| Par | Tarifa pública (R$) | Tarifa sint. (R$) | Erro % | Share do par no total Azul (pub.) | Share sint. | Erro % | Azul no par (assentos Azul / mercado, pub.) | Atraso>30 pub. | Atraso>30 sint. | Erro % | Trechos sint. | Atraso esperado no mix sint. | Erro % vs esperado (ruído amostral) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SBRJ-SBSP | 470.85 | 471.08 | +0.0% | 2.88% | 2.90% | +0.7% | 23.3% | 8.50% | 8.40% | -1.1% | 15480 | 8.68% | -3.2% |
| SBGR-SBRF | 629.32 | 620.38 | -1.4% | 2.79% | 2.70% | -3.3% | 50.3% | 7.03% | 7.18% | +2.2% | 14399 | 7.25% | -0.9% |
| SBGR-SBPA | 411.82 | 406.90 | -1.2% | 1.93% | 1.73% | -10.6% | 50.7% | 6.79% | 6.52% | -4.0% | 9236 | 7.01% | -6.9% |
| SBRF-SBSP | 689.82 | 686.66 | -0.5% | 1.91% | 1.87% | -2.3% | 42.7% | 8.79% | 9.76% | +11.1% | 9978 | 9.32% | +4.7% |
| SBCF-SBSP | 441.61 | 442.15 | +0.1% | 1.69% | 1.45% | -14.0% | 28.1% | 10.31% | 10.60% | +2.8% | 7760 | 10.41% | +1.8% |
| SBPA-SBSP | 402.94 | 399.43 | -0.9% | 1.68% | 1.63% | -3.0% | 27.3% | 7.46% | 7.56% | +1.4% | 8714 | 7.75% | -2.4% |
| SBBR-SBSP | 420.24 | 401.65 | -4.4% | 1.65% | 1.60% | -3.1% | 22.2% | 8.45% | 8.32% | -1.5% | 8530 | 8.68% | -4.2% |
| SBGL-SBRF | 666.45 | 654.92 | -1.7% | 1.63% | 1.63% | -0.2% | 48.3% | 8.12% | 8.01% | -1.3% | 8708 | 7.65% | +4.6% |
| SBCT-SBPA | 397.65 | 396.34 | -0.3% | 1.36% | 1.38% | +2.2% | 67.7% | 8.11% | 7.69% | -5.2% | 7397 | 8.20% | -6.2% |
| SBBR-SBKP | 465.70 | 461.99 | -0.8% | 1.28% | 1.22% | -4.8% | 59.2% | 8.61% | 8.29% | -3.7% | 6501 | 8.46% | -2.0% |

- Tarifa média global: público R$ 694.40; sintético R$ 697.89 (+0.5%).
- Atraso > 30 min global (voos realizados): público 8.20%; sintético 8.12% (-0.9%).
- Share do par: erro absoluto máximo 14.0%, médio 4.4% (versão anterior, casa por voos do VRA: de -46% a +17%).

**Erros acima de 5% e causas prováveis (não isoladas por teste):** (1) *Share do par* (SBGR-SBPA, SBCF-SBSP): casa e destino já saem dos mesmos assentos de tarifas, mas o peso do par depende também da sazonalidade por rota (índice com teto 3), de cada cliente ter só 1 a 3 destinos favoritos e dos eventos perdidos onde a Azul saiu; com 50.000 clientes e poucos milhares de trechos por par, parte é ruído de composição. (2) *Atraso > 30 min*: o sorteio é binomial (desvio-padrão de 2,5% a 3,5% relativo nos pares) e o mix rota-mês do sintético segue as vendas, não os voos; compare as duas últimas colunas (erro contra o esperado no mix). (3) *Cancelamento por par*: evento de cerca de 0,5% a 2%, desvio-padrão do sorteio de 8% a 15% relativo por par; o teste relevante é o global.

## Cancelamento com a mesma ponderação nos dois lados

A taxa pública de cancelamento de `gold.route_disruptions` é por rota direcional e mês (cancelados / previstos). A comparação anterior (2,04% ponderada por voos x 1,78% do sintético ponderado por passageiros) misturava ponderações. Aqui o **público é reponderado pelo mix de trechos do sintético**: para cada trecho gerado, a taxa pública da sua rota direcional e mês do voo; a média é o cancelamento esperado no mix de passageiros. Só entram trechos de rota-mês com dado na gold (os demais usam média da rota ou da rede, que não é fonte direta).

- Global: público no mix do sintético 1.58%; sintético 1.58%; erro -0.5%. Referência por voo (ponderação anterior): 2.04% público; sintético sem filtro 1.70% (-17.0%).
- Fração dos trechos com rota-mês observada na gold: 71.6%.

| Par | Cancelamento público no mix sint. | Cancelamento sint. | Erro % |
|---|---|---|---|
| SBRJ-SBSP | 2.26% | 2.25% | -0.3% |
| SBGR-SBRF | 0.72% | 0.70% | -2.6% |
| SBGR-SBPA | 1.44% | 1.28% | -11.0% |
| SBRF-SBSP | 0.59% | 0.52% | -12.0% |
| SBCF-SBSP | 0.88% | 0.81% | -8.2% |
| SBPA-SBSP | 0.88% | 0.73% | -17.2% |
| SBBR-SBSP | 1.24% | 1.17% | -5.7% |
| SBGL-SBRF | 0.58% | 0.47% | -18.3% |
| SBCT-SBPA | 1.34% | 1.38% | +3.5% |
| SBBR-SBKP | 2.06% | 2.23% | +8.4% |

Cancelamento é evento raro (cerca de 2%): nos pares com 6 a 15 mil trechos o desvio-padrão do sorteio é de 8% a 15% relativo, então erros desse tamanho nos pares são ruído amostral; o global (centenas de milhares de trechos) é o teste relevante.

**Sobre a coluna 'Azul no par':** é a participação da Azul entre as companhias do par (público). O sintético tem só clientes da Azul e nenhum concorrente, então ela não é reproduzível por construção e vai apenas como contexto. O que o sintético reproduz é o peso do par no total de trechos da Azul, comparado ao peso do par no total de assentos da Azul (coluna 'Share do par').

## Aeroporto de casa x assentos da Azul (tarifas)

Casa e pares saem da mesma fonte: assentos vendidos pela Azul em `silver.anac_tarifas` (AZU, 2024-09 a 2026-08). Os voos do VRA vão só como referência.

| Aeroporto | Share de assentos Azul com origem no aeroporto (tarifas) | Share de clientes (casa) | Share de voos Azul (VRA, só referência) |
|---|---|---|---|
| SBKP | 9.75% | 9.92% | 17.72% |
| SBRF | 8.72% | 8.52% | 8.70% |
| SBCF | 7.91% | 7.82% | 13.78% |
| SBSP | 6.42% | 6.35% | 4.87% |
| SBPA | 5.50% | 5.55% | 3.21% |
| SBGR | 4.89% | 4.80% | 3.30% |
| SBCT | 4.41% | 4.35% | 4.05% |
| SBGL | 4.09% | 4.14% | 2.41% |

## Cobertura das ameaças (clientes distintos)

Eventos por tipo e período (A = ameaça A grave: 2 eventos de atraso de partida > 60 min ou cancelamento em até 90 dias, data do 2º evento; B e C = pares reais de `gold.route_exits` e `gold.route_competition` em que o cliente voou nos 12 meses até o mês da ameaça):

| Tipo | Detalhe | Período | Eventos | Clientes |
|---|---|---|---|---|
| A | grave_2_eventos_90d | historico | 3544 | 2778 |
| A | grave_2_eventos_90d | rotulo | 1127 | 1040 |
| B | reducao | historico | 2517 | 2503 |
| B | reducao | rotulo | 4565 | 4233 |
| B | saida_total | historico | 900 | 887 |
| B | saida_total | rotulo | 177 | 177 |
| C | queda_tarifa | historico | 1668 | 1642 |
| C | queda_tarifa | rotulo | 2581 | 2540 |

Clientes distintos atingidos (qualquer período): A 3533, B 7138, C 3723 de 50000.

Por nível vigente em 28/02/2026 (histórico = ameaças até 2026-02; todos = inclui mar-ago/2026):

| Nível | Clientes | A hist. | B hist. | C hist. | A todos | B todos | C todos |
|---|---|---|---|---|---|---|---|
| Diamante Unique | 167 | 131 | 13 | 7 | 137 | 30 | 11 |
| Diamante | 831 | 444 | 79 | 43 | 497 | 148 | 88 |
| Safira | 6875 | 1328 | 645 | 367 | 1676 | 1520 | 808 |

## Taxa de evasão por ameaça dentro de cada faixa de frequência (entre elegíveis)

Elegíveis: 13846 (trechos esperados em 6 meses >= 3); não elegíveis (rótulo nulo): 36154. Faixas = tercis da taxa mensal do histórico entre elegíveis: baixa < 0.667, média até 1.056, alta acima (trechos/mês). Evasão 'natural' (só acaso) por faixa, usada na calibração: 22.8%, 15.1%, 9.9%. Expostos = ameaça no histórico (últimos 6 meses: 2025-09 a 2026-02); não expostos = sem essa ameaça (podem ter outras). Diferença em pontos percentuais (pp); alvo entre parênteses.

| Ameaça (alvo) | Faixa | Expostos | Evasão expostos | Evasão não expostos | Diferença (pp) |
|---|---|---|---|---|---|
| A grave (2 eventos em 90 dias) (+8 pp) | baixa | 74 | 39.2% | 37.7% | +1.5 |
| A grave (2 eventos em 90 dias) (+8 pp) | média | 187 | 36.9% | 27.7% | +9.2 |
| A grave (2 eventos em 90 dias) (+8 pp) | alta | 670 | 24.9% | 17.0% | +7.9 |
| B saída total na rota favorita (+20 pp) | baixa | 8 | 62.5% | 37.7% | +24.8 |
| B saída total na rota favorita (+20 pp) | média | 26 | 42.3% | 28.0% | +14.3 |
| B saída total na rota favorita (+20 pp) | alta | 24 | 41.7% | 18.0% | +23.7 |
| B redução na rota favorita (+8 pp) | baixa | 219 | 46.1% | 37.2% | +8.9 |
| B redução na rota favorita (+8 pp) | média | 320 | 35.3% | 27.6% | +7.7 |
| B redução na rota favorita (+8 pp) | alta | 267 | 25.8% | 17.7% | +8.2 |
| C queda de tarifa na rota favorita (+10 pp) | baixa | 125 | 45.6% | 37.5% | +8.1 |
| C queda de tarifa na rota favorita (+10 pp) | média | 194 | 37.6% | 27.7% | +10.0 |
| C queda de tarifa na rota favorita (+10 pp) | alta | 170 | 27.6% | 17.8% | +9.9 |
| Perto de cair de nível (+6 pp) | baixa | 1668 | 41.2% | 35.1% | +6.1 |
| Perto de cair de nível (+6 pp) | média | 2775 | 30.8% | 24.9% | +5.9 |
| Perto de cair de nível (+6 pp) | alta | 919 | 23.0% | 17.0% | +6.0 |

Ameaças com poucos expostos por faixa (em especial saída total, dezenas de clientes) têm estimativa ruidosa: com n = 30 e taxa perto de 30%, o erro-padrão da diferença é de cerca de 8 pp.

Multiplicadores de calibração do efeito (kappa, 1 = delta nominal; ameaça × faixa baixa/média/alta): A grave (2 eventos em 90 dias) [1.87, 2.29, 2.12]; B saída total na rota favorita [0.54, 0.54, 0.54]; B redução na rota favorita [0.35, 0.51, 0.31]; C queda de tarifa na rota favorita [1.48, 1.41, 1.25]; Perto de cair de nível [1.2, 1.2, 1.3]. Kappa acima de 1 compensa confundidores que reduzem a diferença; abaixo de 1 ou 0, confundidores que já a aumentam (saída de rota reduz trechos e aciona também a tendência de queda).

## Pirâmide de níveis (vigente em 2026-02-28)

| Nível | Clientes |
|---|---|
| Sem nível | 34097 |
| Topázio | 8030 |
| Safira | 6875 |
| Diamante | 831 |
| Diamante Unique | 167 |

## Proxy do arquétipo nas tabelas de entrada

Distância de variação total média entre P(arquétipo | valor da coluna) e P(arquétipo) (0 = a coluna não informa nada sobre o arquétipo; 1 = proxy perfeito): aeroporto_casa 0.0234, consentimento_marketing 0.0026. As colunas de comportamento (frequência, antecedência, tarifa) são correlacionadas ao arquétipo por construção, mas as classes se sobrepõem (Gamma, ruído) e nenhuma coluna o identifica sozinha.

Tempo total de execução: 13 s.
