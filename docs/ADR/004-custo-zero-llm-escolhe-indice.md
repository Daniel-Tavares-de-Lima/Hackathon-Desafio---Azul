# ADR 004 · Custo zero: sem LLM pago; o Ollama só escolhe um índice

**Status:** aceita (2026-10-20). **Detalhes:** P-17.

## Contexto
Sem verba para API paga e com risco de texto livre inventar benefício ou número.

## Decisão
- A decisão é determinística: regras + catálogo + guardrails. Nenhum LLM decide nada.
- A mensagem = contexto fixo aprovado (3 ou 4 por ação: empático, direto, caloroso, formal) + oferta montada por
  texto-modelo fixo com os números da decisão, que nunca muda.
- Padrão: `LLM_PROVIDER=nenhum` (usa o 1º contexto). Opcional: `LLM_PROVIDER=ollama`, modelo local, que recebe um
  resumo sem atributo sensível e responde **só o número do contexto**. A resposta só vale se casar com `^[1-N]$`;
  qualquer outra coisa usa o padrão.
- RAG por TF-IDF do scikit-learn sobre a KB, sem embeddings pagos.

## Consequências
- Nenhum texto do LLM chega ao cliente. Não há lista de bloqueio para o LLM manter.
- Menos personalização de texto. Aceitamos: o ganho está em agir no gatilho certo, não na redação.
- Painel, API e modelos rodam num notebook, sem custo de nuvem.
