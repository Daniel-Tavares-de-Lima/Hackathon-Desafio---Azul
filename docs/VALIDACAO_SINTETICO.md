# Validação do sintético contra fontes públicas

Gerado por `pipelines/synthetic/generate.py` (seed 20261017). Erro % = 100 × (sintético − público) / público.
Comparação sobre os 10 maiores pares (`par_rota`, dois sentidos somados) por assentos vendidos pela Azul (silver.anac_tarifas, AZU), janela 2024-09 a 2026-08.
O sintético usa 50.000 clientes e todas as viagens geradas (histórico + rótulo). Ver premissas P-06 a P-15 e a circularidade (P-06).

| Par | Tarifa pública (R$) | Tarifa sint. (R$) | Erro % | Share do par no total Azul (pub.) | Share sint. | Erro % | Azul no par (assentos Azul / mercado, pub.) | Atraso>30 pub. | Atraso>30 sint. | Erro % | Trechos sint. | Atraso esperado no mix sint. | Erro % vs esperado (ruído amostral) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SBRJ-SBSP | 470.85 | 476.03 | +1.1% | 2.88% | 2.90% | +0.7% | 23.3% | 8.50% | 8.64% | +1.7% | 15456 | 8.66% | -0.2% |
| SBGR-SBRF | 629.32 | 628.27 | -0.2% | 2.79% | 2.69% | -3.5% | 50.3% | 7.03% | 6.83% | -2.8% | 14366 | 7.22% | -5.5% |
| SBGR-SBPA | 411.82 | 406.30 | -1.3% | 1.93% | 1.76% | -9.0% | 50.7% | 6.79% | 7.22% | +6.3% | 9388 | 7.01% | +3.0% |
| SBRF-SBSP | 689.82 | 698.38 | +1.2% | 1.91% | 1.86% | -2.6% | 42.7% | 8.79% | 9.36% | +6.5% | 9939 | 9.23% | +1.4% |
| SBCF-SBSP | 441.61 | 432.96 | -2.0% | 1.69% | 1.45% | -14.0% | 28.1% | 10.31% | 9.94% | -3.6% | 7753 | 10.40% | -4.4% |
| SBPA-SBSP | 402.94 | 398.32 | -1.1% | 1.68% | 1.66% | -1.5% | 27.3% | 7.46% | 7.67% | +2.9% | 8845 | 7.87% | -2.5% |
| SBBR-SBSP | 420.24 | 401.99 | -4.3% | 1.65% | 1.59% | -3.8% | 22.2% | 8.45% | 8.72% | +3.2% | 8460 | 8.61% | +1.2% |
| SBGL-SBRF | 666.45 | 651.11 | -2.3% | 1.63% | 1.60% | -2.2% | 48.3% | 8.12% | 7.25% | -10.7% | 8528 | 7.56% | -4.2% |
| SBCT-SBPA | 397.65 | 399.52 | +0.5% | 1.36% | 1.36% | +0.3% | 67.7% | 8.11% | 7.89% | -2.7% | 7255 | 8.18% | -3.6% |
| SBBR-SBKP | 465.70 | 480.53 | +3.2% | 1.28% | 1.24% | -3.4% | 59.2% | 8.61% | 8.90% | +3.4% | 6593 | 8.50% | +4.8% |

- Tarifa média global: público R$ 694.40; sintético R$ 699.09 (+0.7%).
- Atraso > 30 min global (voos realizados): público 8.20%; sintético 8.18% (-0.1%).
- Share do par: erro absoluto máximo 14.0%, médio 4.1% (versão anterior, casa por voos do VRA: de -46% a +17%).

**Erros acima de 5% e causas prováveis (não isoladas por teste):** (1) *Share do par* (SBGR-SBPA, SBCF-SBSP): casa e destino já saem dos mesmos assentos de tarifas, mas o peso do par depende também da sazonalidade por rota (índice com teto 3), de cada cliente ter só 1 a 3 destinos favoritos e dos eventos perdidos onde a Azul saiu; com 50.000 clientes e poucos milhares de trechos por par, parte é ruído de composição. (2) *Atraso > 30 min*: o sorteio é binomial (desvio-padrão de 2,5% a 3,5% relativo nos pares) e o mix rota-mês do sintético segue as vendas, não os voos; compare as duas últimas colunas (erro contra o esperado no mix). (3) *Cancelamento por par*: evento de cerca de 0,5% a 2%, desvio-padrão do sorteio de 8% a 15% relativo por par; o teste relevante é o global.

## Cancelamento com a mesma ponderação nos dois lados

A taxa pública de cancelamento de `gold.route_disruptions` é por rota direcional e mês (cancelados / previstos). A comparação anterior (2,04% ponderada por voos x 1,78% do sintético ponderado por passageiros) misturava ponderações. Aqui o **público é reponderado pelo mix de trechos do sintético**: para cada trecho gerado, a taxa pública da sua rota direcional e mês do voo; a média é o cancelamento esperado no mix de passageiros. Só entram trechos de rota-mês com dado na gold (os demais usam média da rota ou da rede, que não é fonte direta).

- Global: público no mix do sintético 1.59%; sintético 1.61%; erro +1.3%. Referência por voo (ponderação anterior): 2.04% público; sintético sem filtro 1.70% (-16.7%).
- Fração dos trechos com rota-mês observada na gold: 71.7%.

| Par | Cancelamento público no mix sint. | Cancelamento sint. | Erro % |
|---|---|---|---|
| SBRJ-SBSP | 2.26% | 2.25% | -0.2% |
| SBGR-SBRF | 0.71% | 0.74% | +3.3% |
| SBGR-SBPA | 1.46% | 1.49% | +1.6% |
| SBRF-SBSP | 0.57% | 0.64% | +13.1% |
| SBCF-SBSP | 0.88% | 0.88% | +0.1% |
| SBPA-SBSP | 0.89% | 0.81% | -8.7% |
| SBBR-SBSP | 1.25% | 1.30% | +4.2% |
| SBGL-SBRF | 0.57% | 0.48% | -16.3% |
| SBCT-SBPA | 1.34% | 1.48% | +10.3% |
| SBBR-SBKP | 2.11% | 2.02% | -4.3% |

Cancelamento é evento raro (cerca de 2%): nos pares com 6 a 15 mil trechos o desvio-padrão do sorteio é de 8% a 15% relativo, então erros desse tamanho nos pares são ruído amostral; o global (centenas de milhares de trechos) é o teste relevante.

**Sobre a coluna 'Azul no par':** é a participação da Azul entre as companhias do par (público). O sintético tem só clientes da Azul e nenhum concorrente, então ela não é reproduzível por construção e vai apenas como contexto. O que o sintético reproduz é o peso do par no total de trechos da Azul, comparado ao peso do par no total de assentos da Azul (coluna 'Share do par').

## Aeroporto de casa x assentos da Azul (tarifas)

Casa e pares saem da mesma fonte: assentos vendidos pela Azul em `silver.anac_tarifas` (AZU, 2024-09 a 2026-08): 152 aeroportos de origem candidatos, 135 sorteados como casa de ao menos um cliente. Os voos do VRA vão só como referência.

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

## Saída total e retorno da Azul ao par

`gold.route_exits` marca 53 pares com saída total; 51 têm venda da Azul (AZU) na ANAC Tarifas e entram no sintético (os demais são pares só da ACN ou sem venda AZU; P-15). A Azul fica fora do par de `mes_saida` até o mês anterior ao retorno (primeiro mês seguinte com voo do grupo Azul): 10 pares voltam na janela (10 deles no sintético): SBAT-SBCY (2025-07 → 2026-04), SBBE-SNMZ (2026-01 → 2026-07), SBBV-SBKP (2025-04 → 2026-08), SBCF-SBCN (2025-08 → 2026-06), SBCF-SBLE (2025-03 → 2026-06), SBCR-SBKP (2025-11 → 2026-03), SBCY-SBJI (2025-09 → 2026-04), SBCY-SBVH (2025-04 → 2026-04), SBCY-SSKW (2025-04 → 2026-04), SBEG-SWKO (2026-01 → 2026-08).

## Cobertura das ameaças (clientes distintos)

Duas tabelas: `synthetic_customer_threats` (histórico, mês <= 2026-02; entrada do modelo e do Radar) e `synthetic_customer_threats_rotulo` (período de rótulo, 2026-03 a 2026-08; nunca entrada de modelo). A = ameaça A grave: 2 eventos de atraso de partida > 60 min ou cancelamento em até 90 dias, data do 2º evento; B e C = pares reais de `gold.route_exits` e `gold.route_competition` em que o cliente voou nos 12 meses até o mês da ameaça. C é só `queda_tarifa` (a entrada de concorrente saiu da gold, P-05).

| Tipo | Detalhe | Tabela | Eventos | Clientes | Primeiro mês | Último mês |
|---|---|---|---|---|---|---|
| A | grave_2_eventos_90d | customer_threats | 3509 | 2793 | 2024-09 | 2026-02 |
| A | grave_2_eventos_90d | customer_threats_rotulo | 1084 | 997 | 2026-03 | 2026-08 |
| B | reducao | customer_threats | 2596 | 2582 | 2025-11 | 2026-02 |
| B | reducao | customer_threats_rotulo | 4566 | 4227 | 2026-03 | 2026-08 |
| B | saida_total | customer_threats | 823 | 815 | 2025-04 | 2026-01 |
| B | saida_total | customer_threats_rotulo | 118 | 118 | 2026-03 | 2026-04 |
| C | queda_tarifa | customer_threats | 1674 | 1647 | 2025-10 | 2026-02 |
| C | queda_tarifa | customer_threats_rotulo | 2545 | 2513 | 2026-03 | 2026-08 |

Clientes distintos atingidos (as duas tabelas): A 3530, B 7119, C 3719 de 50000.

Por nível vigente em 2026-02-28 (hist. = `synthetic_customer_threats`; todos = inclui `synthetic_customer_threats_rotulo`):

| Nível | Clientes | A hist. | B hist. | C hist. | A todos | B todos | C todos |
|---|---|---|---|---|---|---|---|
| Diamante Unique | 161 | 139 | 15 | 6 | 143 | 27 | 12 |
| Diamante | 863 | 462 | 88 | 42 | 522 | 170 | 77 |
| Safira | 6826 | 1235 | 696 | 371 | 1575 | 1550 | 806 |

## Taxa de evasão por ameaça dentro de cada faixa de frequência (entre elegíveis)

Elegíveis: 13825 (trechos esperados em 6 meses >= 3); não elegíveis (rótulo nulo): 36175. Faixas = tercis da taxa mensal do histórico entre elegíveis: baixa < 0.667, média até 1.056, alta acima (trechos/mês). Evasão 'natural' (só acaso) por faixa, usada na calibração: 23.8%, 16.2%, 10.3%. Expostos = ameaça no histórico (últimos 6 meses: 2025-09 a 2026-02); não expostos = sem essa ameaça (podem ter outras). Diferença em pontos percentuais (pp); alvo entre parênteses.

| Ameaça (alvo) | Faixa | Expostos | Evasão expostos | Evasão não expostos | Diferença (pp) |
|---|---|---|---|---|---|
| A grave (2 eventos em 90 dias) (+8 pp) | baixa | 88 | 46.6% | 39.5% | +7.1 |
| A grave (2 eventos em 90 dias) (+8 pp) | média | 186 | 36.6% | 28.5% | +8.0 |
| A grave (2 eventos em 90 dias) (+8 pp) | alta | 638 | 23.8% | 15.9% | +7.9 |
| B saída total na rota favorita (+20 pp) | baixa | 16 | 56.2% | 39.6% | +16.7 |
| B saída total na rota favorita (+20 pp) | média | 17 | 76.5% | 28.7% | +47.8 |
| B saída total na rota favorita (+20 pp) | alta | 28 | 57.1% | 16.7% | +40.4 |
| B redução na rota favorita (+8 pp) | baixa | 247 | 47.8% | 39.1% | +8.7 |
| B redução na rota favorita (+8 pp) | média | 314 | 36.3% | 28.3% | +8.0 |
| B redução na rota favorita (+8 pp) | alta | 303 | 24.4% | 16.4% | +8.0 |
| C queda de tarifa na rota favorita (+10 pp) | baixa | 138 | 50.7% | 39.2% | +11.5 |
| C queda de tarifa na rota favorita (+10 pp) | média | 187 | 38.5% | 28.5% | +10.1 |
| C queda de tarifa na rota favorita (+10 pp) | alta | 161 | 26.7% | 16.6% | +10.1 |
| Perto de cair de nível (+6 pp) | baixa | 1732 | 42.9% | 37.0% | +5.9 |
| Perto de cair de nível (+6 pp) | média | 2780 | 31.5% | 25.7% | +5.9 |
| Perto de cair de nível (+6 pp) | alta | 911 | 21.7% | 15.8% | +5.9 |

### Delta efetivo (medido) x nominal

Delta efetivo = média das diferenças por faixa ponderada pelos expostos de cada faixa (o que a calibração mira). Bruto = diferença entre expostos e não expostos sem estratificar por faixa (mistura o efeito da frequência).

| Ameaça | Nominal (pp) | Expostos | Delta efetivo (pp) | Bruto (pp) |
|---|---|---|---|---|
| A grave (2 eventos em 90 dias) | +8 | 912 | +7.9 | +0.8 |
| B saída total na rota favorita | +20 | 61 | +36.3 | +34.6 |
| B redução na rota favorita | +8 | 864 | +8.2 | +8.1 |
| C queda de tarifa na rota favorita | +10 | 486 | +10.5 | +10.6 |
| Perto de cair de nível | +6 | 5423 | +5.9 | +9.4 |

Ameaças com poucos expostos por faixa (em especial saída total, dezenas de clientes) têm estimativa ruidosa: com n = 30 e taxa perto de 30%, o erro-padrão da diferença é de cerca de 8 pp.

Multiplicadores de calibração do efeito (kappa, 1 = delta nominal; ameaça × faixa baixa/média/alta): A grave (2 eventos em 90 dias) [2.34, 2.68, 1.44]; B saída total na rota favorita [0.0, 0.0, 0.0]; B redução na rota favorita [0.16, 0.69, 0.02]; C queda de tarifa na rota favorita [1.34, 0.94, 1.41]; Perto de cair de nível [1.28, 0.74, 0.51]. Kappa acima de 1 compensa confundidores que reduzem a diferença; abaixo de 1 ou 0, confundidores que já a aumentam (saída de rota reduz trechos e aciona também a tendência de queda).

## Pirâmide de níveis (vigente em 2026-02-28)

| Nível | Clientes |
|---|---|
| Sem nível | 34176 |
| Topázio | 7974 |
| Safira | 6826 |
| Diamante | 863 |
| Diamante Unique | 161 |

## Proxy do arquétipo nas tabelas de entrada

Distância de variação total média entre P(arquétipo | valor da coluna) e P(arquétipo) (0 = a coluna não informa nada sobre o arquétipo; 1 = proxy perfeito): aeroporto_casa 0.0234, consentimento_marketing 0.0026. As colunas de comportamento (frequência, antecedência, tarifa) são correlacionadas ao arquétipo por construção, mas as classes se sobrepõem (Gamma, ruído) e nenhuma coluna o identifica sozinha.

