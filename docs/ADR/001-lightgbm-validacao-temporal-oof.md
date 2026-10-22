# ADR 001 · LightGBM, validação temporal e previsão out-of-fold declarada

**Status:** aceita (2026-10-17). **Detalhes:** `ml/model_card.md`, P-16.

## Contexto
Precisamos de dois números por cliente: risco de evasão em 6 meses e CLV de 6 meses. A banca precisa confiar na
métrica, e a base é sintética.

## Decisão
- LightGBM (classificador para evasão, regressor Tweedie para CLV). Lida bem com dado tabular, valores nulos e
  relações não lineares, e tem explicação SHAP exata e barata.
- Sempre comparar com uma regra simples (logística RFM; gasto de 12 meses ÷ 2).
- Avaliação principal **temporal**: treina com corte em 31/08/2025 e testa em 28/02/2026.
- O score de produção usa o modelo do corte de 28/02/2026 com previsão **out-of-fold** (5 dobras por cliente). Isso
  está escrito no model card: não é validação temporal.

## Por quê
O gerador sintético só aplica o efeito das ameaças no período de rótulo oficial. No corte de treino as ameaças não
mudam o comportamento, então o modelo temporal não tem como aprendê-las. O OOF é o único jeito de medir se o modelo
recupera esse mecanismo.

## Consequências
- No temporal o LightGBM **empata com a logística** (AUC-PR 0,415 contra 0,425). Dizemos isso na banca.
- No OOF o LightGBM ganha (AUC-PR 0,466 contra 0,444), vindo de ameaças, nível e tendência.
- Com dado real: treinar num corte com rótulo e validar no seguinte. Se a logística continuar empatando, fica a
  logística.
