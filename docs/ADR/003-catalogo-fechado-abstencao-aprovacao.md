# ADR 003 · Catálogo fechado de ações, abstenção e aprovação humana

**Status:** aceita (2026-10-20). **Detalhes:** P-17, `agent/tools.py`, `agent/nba_agent.py`.

## Contexto
Um agente que promete benefício inexistente ao cliente de alto valor é pior que nenhum agente.

## Decisão
- **Catálogo fechado** de 6 ações: recuperação de serviço, oferta na rota favorita, bônus de pontos, upgrade
  (só Diamante Unique), desafio de manutenção de nível, contato humano.
- Cada ação exige que o benefício prometido exista na KB (`agent/kb/`) para o nível do cliente. Se não existir:
  **abstenção** (`sem_acao_automatica`).
- Abstenção também quando: não elegível (sem risco estimável), valor baixo, ROI ≤ 0, sem consentimento de marketing
  (exceto recuperação e contato) ou guardrail violado.
- **Toda** proposta, inclusive a abstenção, sai com `requer_aprovacao_humana = true`. O app só grava a aprovação; nada
  é enviado ao cliente.
- Crédito de pontos de cortesia sai em campo separado: "decisão comercial (sem regra pública)".

## Consequências
- No lote, 9.326 de 12.734 clientes ficam em abstenção. É o comportamento esperado, não falha.
- O aprovador pode editar o contexto da mensagem, nunca a oferta (números, pontos, prazos). Risco residual aceito
  pela auditoria: a lista de bloqueio da edição manual não é completa.
