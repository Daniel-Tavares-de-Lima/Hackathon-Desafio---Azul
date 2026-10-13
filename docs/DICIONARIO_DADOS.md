# Dicionário de dados

Uma linha por tabela. Schema completo (colunas, tipos, nulidade) no contrato YAML indicado.

| Tabela | Camada | Grão | Fonte pública | Produzida por | Contrato | Uso |
|---|---|---|---|---|---|---|
| `silver.anac_tarifas` | silver | empresa x origem x destino x tarifa x mês (assentos vendidos àquela tarifa) | ANAC, Tarifas Aéreas Domésticas (`sas.anac.gov.br/sas/tarifadomestica/`) | `pipelines/ingest_anac.py tarifas` | `contracts/silver_anac_tarifas.yaml` | Ameaça C: share de assentos e tarifa média por empresa/rota |
| `silver.anac_vra` | silver | etapa de voo regular doméstico (empresa, voo, origem, partida prevista) | ANAC, VRA – Voo Regular Ativo (`siros.anac.gov.br/siros/registros/diversos/vra/`) | `pipelines/ingest_anac.py vra` | `contracts/silver_anac_vra.yaml` | Ameaça A: atraso > 30 min e cancelamento; Ameaça B: frequência Azul por rota/mês |
