# Painel e API

Pré-requisito: `data/` e `ml/resultados/` já gerados (`make all`). Custo zero: nada chama API paga.

## Como rodar (Windows, sem `make`)
```
.venv\Scripts\python -I app\lote.py                      # agente em lote (~1 min, só se o score mudou)
.venv\Scripts\python -I -m streamlit run app\main.py     # painel em http://localhost:8501
.venv\Scripts\python -I -m uvicorn api.main:app --app-dir . --port 8000   # API em http://localhost:8000/docs
.venv\Scripts\python -I api\test_api.py                  # teste da API
```
Com `make`: `make app`, `make api`, `make api-test`.

Aprovar/Descartar só grava em `app/.cache/aprovacoes.jsonl`. Nada é enviado ao cliente.

## Roteiro do demo (3 minutos)
1. **Radar de ameaças** (abre sozinho). Mostre os três contadores (A, B, C) até 28/02/2026 e o gráfico valor × risco:
   o quadrante de cima à direita é onde agir primeiro. A lista abaixo está ordenada por receita em risco.
2. Em **Agir**, digite `9132e89e` na busca, escolha o cliente e clique **Agir**. Mostre a ação (recuperação de
   serviço), o ROI e o custo, as regras citadas com o selo "a conferir por negócios", edite a mensagem e clique
   **Aprovar**. Nada é enviado.
3. **Cliente 360**: o id `85e407cb-e65a-4be9-a5ab-eb6b99cbecd0` já vem preenchido (cliente Diamante perto de cair de
   nível). Mostre os 3 motivos do modelo, as viagens e clique **Gerar próxima melhor ação** (desafio de manutenção).
4. **Simulador de ROI**: arraste a verba e mostre clientes salvos e receita protegida. Diga que os efeitos são
   supostos (P-17).
