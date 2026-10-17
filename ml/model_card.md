# Model card · ÓRBITA · evasão, CLV, score, personas

Base 100% sintética (P-06). Todo número abaixo mede quanto os modelos recuperam as regras do gerador sob ruído, não
desempenho em clientes reais. Números gravados por `make ml` em `ml/resultados/*.csv` (reexecução idêntica byte a byte;
seed 20261017). Premissas em `docs/PREMISSAS.md` (P-13, P-16).

## Dados e janelas
| | Corte de treino | Corte de teste / produção |
|---|---|---|
| Corte | 2025-08-31 | 2026-02-28 |
| Features | voos de set/2024 a ago/2025 (12 meses) | voos de set/2024 a fev/2026 (18 meses) |
| Rótulo | set/2025 a fev/2026, recalculado de `synthetic_viagens` (definição P-13) | mar a ago/2026, `synthetic_alvos` |
| Elegíveis à evasão | 14.296 (evasão 21,70%) | 13.825 (evasão 27,83%) |

- Entradas: `synthetic_clientes`, `synthetic_viagens`, `synthetic_customer_threats` (só ameaças observáveis no corte) e
  `gold.route_exits` (mês em que a saída total fica visível). Nunca lidos como entrada: `synthetic_alvos`,
  `synthetic_viagens_futuro`, `synthetic_customer_threats_rotulo`, `synthetic_archetypes_validacao`.
  `ml/features.py` faz asserção de que nenhuma data usada passa do corte.
- 22 features (`features.MODELO`): recência, taxa mensal, trechos 6 m e 12 m, tendência (6 m vs até 12 m anteriores),
  gasto 12 m, tarifa média, antecedência mediana, nº de rotas 12 m, concentração na rota favorita, eventos graves 90 d,
  cancelados 12 m, % atraso > 30 min, nível 12 m e folga/falta, ameaças A (nº 6 m, dias desde), B saída e B redução e
  C queda de tarifa na rota favorita (6 m), dias desde B/C. Região de origem fica fora de propósito (só fairness).
- **Limitação 12 x 18 meses:** o corte de treino tem 12 meses de histórico e o de teste 18. Por isso não entra contagem
  acumulada; a tendência compara a taxa dos últimos 6 meses com a dos 6 (treino) ou 12 (teste) anteriores, e nível e
  recência de ameaça usam janela de 12 meses nos dois cortes.

## Por que há duas avaliações (achado importante)
O gerador só aplica o evento oculto de parada (e, com ele, todo efeito de ameaça, nível e tendência, P-13) no
período de rótulo oficial (mar a ago/2026). No rótulo de treino (set/2025 a fev/2026) só existe evasão natural de
Poisson, e B redução e C nem existem antes de 2025-10/11. O modelo temporal, portanto, **não tem como aprender os
efeitos de ameaça**: as features de ameaça B/C são constantes no treino. Medimos as duas coisas:

1. **Temporal (principal, pedida):** treina em 2025-08, avalia em 2026-02. Mede o que se sustentaria fora do tempo.
2. **Produção:** o modelo do score é treinado no corte 2026-02 e cada cliente recebe a previsão out-of-fold
   (5 dobras estratificadas, sorteio fixo de clientes, mesmo corte). **Não é validação temporal**: mede quanto o
   modelo recupera o mecanismo do gerador. Não há segundo corte com o mesmo mecanismo para validar fora do tempo.

## Evasão (LightGBM classificador, só elegíveis) · `ml/churn.py`
| Avaliação | Modelo | AUC-PR | Prevalência (baseline AUC-PR) | AUC-ROC | Precisão top decil | Recall top decil | Brier |
|---|---|---|---|---|---|---|---|
| Temporal | LightGBM | 0,415 | 0,278 | 0,664 | 0,496 | 0,178 | 0,195 |
| Temporal | Baseline logística RFM (recência, taxa, gasto 12 m, tendência) | **0,425** | 0,278 | 0,657 | **0,523** | **0,188** | 0,196 |
| Produção (OOF 2026-02) | LightGBM | **0,466** | 0,278 | **0,704** | **0,563** | **0,202** | **0,180** |
| Produção (OOF 2026-02) | Baseline logística RFM | 0,444 | 0,278 | 0,675 | 0,527 | 0,189 | 0,185 |

- No temporal o LightGBM não supera a logística RFM: sem o mecanismo de parada no treino, só frequência e recência
  carregam sinal, e a regra simples basta. No OOF de 2026-02 o LightGBM ganha 0,03 de AUC-ROC e 0,02 de AUC-PR,
  vindos das ameaças, do nível e da tendência.
- Calibração (`churn_calibracao.csv`): o temporal subestima em todos os decis (p média 0,05 a 0,36 contra evasão real
  0,12 a 0,50), porque a prevalência sobe de 21,7% para 27,8%. O OOF é bem calibrado (decil 1: p 0,59 x real 0,56;
  decil 10: 0,06 x 0,06).
- Nada parece bom demais: AUC-PR 0,47 contra baseline 0,28. O teto é baixo por construção (Poisson + ruído N(0; 0,6²)
  no logit + 78% dos evadidos com zero trecho, P-13).

## CLV de 6 meses (LightGBM regressor Tweedie) · `ml/clv.py`
Alvo `clv_futuro_6m_brl` = receita aérea bruta de mar a ago/2026. **A base só tem 6 meses de futuro**; não há CLV de
12 meses e nada é extrapolado.

| Avaliação | Modelo | MAE (R$) | R² | Gain top 10% |
|---|---|---|---|---|
| Temporal | LightGBM | 1.677 | **0,476** | **44,9%** |
| Temporal | Baseline RFM (gasto 12 m ÷ 2) | **1.593** | 0,472 | 44,1% |
| Produção (OOF 2026-02) | LightGBM | 1.580 | 0,496 | 45,3% |
| Referência | Aleatório | | | 10,0% |
| Referência | Oráculo (ordem perfeita) | 0 | 1 | 57,7% |

- O modelo prevê a média (Tweedie), que é o que o score precisa; por isso perde em MAE para o ritmo recente (a MAE
  favorece a mediana, e o alvo tem muitos zeros). Em R² e gain fica ligeiramente acima. No temporal superestima
  6% a receita média (R$ 2.065 x R$ 1.946), de novo pela parada que só existe no teste.
- Os 10% com maior CLV previsto concentram 45% da receita futura (4,5 vezes o aleatório; 78% do máximo possível).

## SHAP (TreeExplainer, modelos de produção) · `ml/explain.py`
Top 10 da evasão (média de |SHAP|, log-odds; `shap_churn.csv`):

| # | Feature | média \|SHAP\| |
|---|---|---|
| 1 | trechos_6m | 0,344 |
| 2 | antecedencia_mediana | 0,179 |
| 3 | trechos_12m | 0,174 |
| 4 | razao_tendencia | 0,113 |
| 5 | dias_desde_a (ameaça A) | 0,107 |
| 6 | taxa_mensal | 0,107 |
| 7 | recencia_dias | 0,096 |
| 8 | tarifa_media | 0,069 |
| 9 | dias_desde_bc (ameaça B/C na rota favorita) | 0,063 |
| 10 | cancelados_12m | 0,048 |

Importância global e efeito nos expostos vêm do modelo treinado no corte inteiro (descrevem o que o modelo
aprendeu; não chegam a nenhum cliente). Ameaças são raras, então a média global as dilui. SHAP médio **nos
expostos** (log-odds, `shap_ameacas.csv`):

| Ameaça | Expostos | SHAP médio nos expostos | Efeito imposto pelo gerador (P-13, efetivo) |
|---|---|---|---|
| A grave (dias desde, 12 m) | 1.400 | +0,50 | +7,9 pp |
| B saída total na rota favorita | 56 | +0,37 | +37,8 pp (nominal +20) |
| C queda de tarifa na rota favorita | 486 | +0,15 | +10,5 pp |
| B redução na rota favorita | 864 | +0,003 | +8,2 pp |

- **Exposição a A não é a da P-13:** aqui exposto = ao menos um gatilho A grave nos 12 meses até o corte
  (`dias_desde_a` preenchido, 1.400 clientes); na P-13 o efeito do gerador vale para gatilho de set/2025 a fev/2026
  (6 meses, 912 expostos). A feature `a_6m` > 0 (914) é a que corresponde à definição da P-13.
- As ameaças A, B saída e C aparecem e empurram o risco para cima. B redução quase não aparece como feature própria: o
  efeito dela vem do mecanismo (a oferta cortada já reduz trechos, P-13), e o modelo o capta por `trechos_6m` e
  `razao_tendencia`.
- CLV: taxa_mensal, gasto_12m, recencia_dias, antecedencia_mediana e trechos_6m dominam (`shap_clv.csv`).
- Motivos por cliente: as 3 features com SHAP positivo, em frase neutra com o valor do cliente (ex.: "última ameaça
  de atraso grave (A) há 4 dias", "a Azul saiu da rota que ele mais voa (B)"). Contagem zero é pulada. Os motivos são
  out-of-fold: cada cliente é explicado pelo SHAP do mesmo modelo de dobra de `churn.oof` que produziu o p_evasao
  dele, e esse modelo não viu o rótulo do cliente (`explain.py` confere que as dobras reproduzem o p_evasao gravado).
  Alguns motivos são
  descritivos e pouco acionáveis (ex.: "já está no nível mais alto"): o SHAP é honesto, a frase não interpreta.

## Score de Alto Valor · `ml/score.py` → `gold.customer_scores`
`score = CLV_6m × (1 − p_evasao) + 0,25 × CLV_6m × clip(tendência − 1; 0; 1)`. O CLV já embute parte da evasão;
multiplicar por (1 − p) pesa o risco de novo, de propósito, para preferir valor estável. O potencial dá até 25% do
CLV a quem acelerou (horizonte além dos 6 meses; peso de produto). Sem ele, 94,0% do top decil seria igual. Não
elegíveis usam p = 27,8% (prevalência dos elegíveis). Corte do top decil: R$ 3.833.

## Personas (k-means, k = 5) · `ml/segment.py`
Silhueta 0,238 (k = 5) x 0,209 (k = 4), amostra fixa de 10.000. Separação fraca: as personas são faixas de um
contínuo, úteis para comunicar, não grupos naturais. Tabela persona x score em `ml/resultados/personas_score.csv`
(gravada por `ml/score.py`); traços dos centróides em `ml/resultados/personas.csv`.

| Persona | Clientes | Traço (centróide) | Score médio (R$) | % no top decil | p evasão média |
|---|---|---|---|---|---|
| Frequente de negócios | 3.715 | 2,1 trechos/mês, compra 7 dias antes, gasto 12 m R$ 19,2 mil | 8.956 | 82,6% | 0,16 |
| Em ascensão | 7.818 | frequência recente 2,7 vezes a anterior | 2.300 | 14,0% | 0,22 |
| Multirrota | 6.605 | só 60% dos voos na rota favorita, 27 dias de antecedência | 1.855 | 10,7% | 0,31 |
| Ocasional | 11.621 | 0,3 trecho/mês, tarifa mais alta (R$ 877) | 957 | 1,1% | 0,41 |
| Caçador de tarifa | 10.352 | tarifa média R$ 416, compra 33 dias antes | 565 | 0,0% | 0,43 |
| Sem voo no histórico | 9.889 | nenhum trecho voado até o corte | 345 | 0,0% | – |

## Fairness por região de origem · `ml/fairness.py` (só reporta)
| Região | Clientes | Score médio (R$) | Taxa de oferta (top decil) | Evasão real | Brier | AUC | MAE CLV (R$) | CLV real médio (R$) |
|---|---|---|---|---|---|---|---|---|
| Centro-Oeste | 4.948 | 1.659 | 9,5% | 30,5% | 0,188 | 0,711 | 1.545 | 1.906 |
| Nordeste | 10.988 | 1.770 | 10,9% | 26,9% | 0,178 | 0,697 | 1.639 | 2.023 |
| Norte | 4.999 | 1.773 | 10,8% | 31,7% | 0,196 | 0,688 | 1.971 | 2.412 |
| Sudeste | 20.908 | 1.639 | 9,6% | 26,9% | 0,178 | 0,701 | 1.503 | 1.860 |
| Sul | 8.157 | 1.606 | 9,6% | 27,3% | 0,174 | 0,719 | 1.479 | 1.802 |

Disparidade máx/mín: score 1,10 (Norte/Sul); taxa de oferta 1,15 (Nordeste/Centro-Oeste); Brier 1,13; AUC 1,05;
MAE do CLV 1,33, que acompanha o CLV real (1,34, Norte maior: tarifas mais altas na região). A região não é feature;
as diferenças vêm de tarifa e frequência por aeroporto, calibradas na ANAC. Nada foi corrigido.

## Circularidade do sintético · `ml/circularidade.py`
- O modelo não lê variável latente: arquétipo e evento de parada não estão em nenhuma tabela de entrada (P-06, P-14).
  `ml/circularidade.py` é o único arquivo de `ml/` que lê `synthetic_archetypes_validacao`, depois de tudo gravado, só
  para medir. (O contrato da tabela diz "não pode ser lida por ml/"; a leitura aqui é a auditoria pedida, não uso.)
- **Proxies de uma coluna** (reproduzem a auditoria em +-0,01): lazer premium pela antecedência média, AUC 0,889
  (referência 0,887); corporativo pelo nº de trechos, AUC 0,866 (referência 0,862). Arquétipos aparecem quase de
  graça em frequência e antecedência porque o gerador os define assim (P-07).
- **Personas x arquétipo:** pureza global 0,50 contra 0,44 de chutar sempre "ocasional"; ARI 0,10. Só "Frequente de
  negócios" recupera bem um arquétipo (66% corporativo). Bom, não perfeito: as classes se sobrepõem (Gamma, ruído).
- **Evasão por arquétipo** (OOF, `circularidade_churn_arquetipo.csv`): AUC 0,63 a 0,68 dentro de cada arquétipo.
  Calibração boa em corporativo (0,17 previsto x 0,16 real), lazer premium (0,36 x 0,33) e regional (0,29 x 0,29);
  erra em dois: "ocasional" é subestimado em ~9 pp (0,37 x 0,47) e "em ascensão" é superestimado em ~9 pp
  (0,24 x 0,15). O modelo não vê o arquétipo; o intercepto mais alto do ocasional e o multiplicador de crescimento
  do em ascensão (P-07, P-13) só chegam a ele em parte, pelas features de comportamento.
- **Efeitos impostos pelo gerador** (P-13, delta efetivo medido na base): A grave +7,9 pp; B saída total +37,8 pp
  (nominal +20; o excesso é estrutural: perder a rota favorita já corta viagens, e o kappa chegou a 0); B redução
  +8,2 pp; C +10,5 pp; perto de cair de nível +5,9 pp. O SHAP acima mostra o modelo achando os mesmos sinais, na mesma
  ordem de grandeza relativa (saída total o maior por exposto, redução absorvida pela frequência). Isso devolve as
  regras do gerador; não é evidência de que ameaças causem evasão em clientes reais.

## Limitações
- Sintético: efeitos de evasão, arquétipos e pontos são premissas sem fonte pública (P-06). Métricas não valem para a Azul.
- Não estacionariedade do gerador: a validação temporal não vê o mecanismo de parada; o modelo de produção é avaliado
  só no mesmo corte (OOF). Com dado real, o certo é treinar num corte com rótulo e validar no seguinte.
- CLV é de 6 meses e é receita bruta, não margem.
- Nível no modelo é aproximado (janela móvel de 12 meses, pontos sem ruído), não o nível oficial do programa.
- Score e potencial têm pesos de produto (0,25), não estimados.
- Uplift não foi feito (fora do prazo): o score diz quem vale proteger, não quem muda de ideia com oferta.
