# Dicionário de dados

Uma linha por tabela. Schema completo (colunas, tipos, nulidade) no contrato YAML indicado.

| Tabela | Camada | Grão | Fonte pública | Produzida por | Contrato | Uso |
|---|---|---|---|---|---|---|
| `silver.anac_tarifas` | silver | empresa x origem x destino x tarifa x mês (assentos vendidos àquela tarifa) | ANAC, Tarifas Aéreas Domésticas (`sas.anac.gov.br/sas/tarifadomestica/`) | `pipelines/ingest_anac.py tarifas` | `contracts/silver_anac_tarifas.yaml` | Ameaça C: share de assentos e tarifa média por empresa/rota |
| `silver.anac_vra` | silver | etapa de voo regular doméstico (empresa, voo, origem, partida prevista) | ANAC, VRA – Voo Regular Ativo (`siros.anac.gov.br/siros/registros/diversos/vra/`) | `pipelines/ingest_anac.py vra` | `contracts/silver_anac_vra.yaml` | Ameaça A: atraso > 30 min e cancelamento; Ameaça B: frequência Azul por rota/mês |
| `gold.route_disruptions` | gold | rota (origem→destino) x companhia x mês | derivada de `silver.anac_vra` | `pipelines/build_gold.py` (`pipelines/sql/route_disruptions.sql`) | `contracts/gold_route_disruptions.yaml` | Ameaça A: voos previstos/realizados/cancelados e % com atraso > 30 min |
| `gold.route_exits` | gold | rota (origem→destino) x mês, só rotas já operadas pela Azul | derivada de `silver.anac_vra` | `pipelines/build_gold.py` (`pipelines/sql/route_exits.sql`) | `contracts/gold_route_exits.yaml` | Ameaça B: voos da Azul por rota/mês, flags `saida_total` e `reducao` |
| `gold.route_competition` | gold | rota (origem→destino) x companhia x mês, só rotas onde a Azul vendeu | derivada de `silver.anac_tarifas` | `pipelines/build_gold.py` (`pipelines/sql/route_competition.sql`) | `contracts/gold_route_competition.yaml` | Ameaça C: share de assentos, tarifa média ponderada, flags `entrada_concorrente` e `queda_tarifa` |
