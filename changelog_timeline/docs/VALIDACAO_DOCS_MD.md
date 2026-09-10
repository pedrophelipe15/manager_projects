# Validação dos arquivos `.md` — utilização, objetivo e recomendação

> Análise de todos os 14 arquivos Markdown do projeto `changelog_timeline`.
> Objetivo: mapear para que serve cada um, se ainda é usado, e se faz sentido **manter**, **consolidar** ou **remover/arquivar**.

Data da análise: 10/09/2026

---

## Tabela de utilização e objetivo

| Arquivo | Tam. | Objetivo | Utilização atual | Recomendação |
|---------|------|----------|------------------|--------------|
| `DATASHEET.md` | 55,6 KB | Documentação técnica de referência do projeto (arquitetura, pipeline, schema do banco, endpoints, métricas, sync, expurgo). | **Viva** — principal doc de referência; atualizada na sprint. | ✅ **Manter** (doc canônica) |
| `MAPEAMENTO_PROJETO.md` | 20,3 KB | Auditoria/mapa de scripts, dependências e rotas + status das correções. | **Viva** — gerada e mantida na sprint. | ✅ **Manter** |
| `ROTEIRO_CORRECAO_SPRINT.md` | 13,9 KB | Roteiro da sprint de saneamento (backlog, DoD, validação por item). | **Viva** — guia da sprint executada. | ✅ **Manter** (histórico/execução) |
| `design-system.md` | 7,7 KB | Fonte única de tokens de cor/paleta do tema executivo (claro). Referenciada pelo `melhorias_v7` e pelo `mvp_slide`. | **Viva** — consumida pelo tema do slide executivo. | ✅ **Manter** |
| `exporter_jira/README.md` | 3,2 KB | README do pacote extrator (standalone, copiável para outro repo). | **Viva** — ✅ **atualizada (10/09/2026)**: passou a documentar `--with-changelog`, `--db-cache`, `--skip-test`, `changelogs.jsonl`, `export_hierarchy.py` e corrigir o caminho de setup. | ✅ **Manter** |
| `mvp_slide/README.md` | 3,2 KB | Como usar a página de slide executivo (`?key=`). | **Viva** — instruções da feature mvp_slide. | ✅ **Manter** |
| `aba_arquivada_insights.md` | 2,8 KB | Registro histórico do ciclo arquivamento→reativação da aba Insights. | ✅ **atualizada (10/09/2026)**: passou a refletir que a aba foi **reativada** na sprint (não está mais arquivada); vira registro histórico. | ✅ **Manter** (como histórico) |
| `melhorias_v1.md` | 8,5 KB | Histórico: otimização de performance da pipeline (306s→8s). | Concluída (histórico). | 🟢 **Consolidar** em histórico |
| `melhorias_v2.md` | 11,8 KB | Histórico: engine de insights + métricas avançadas. | Concluída (histórico). | 🟢 **Consolidar** em histórico |
| `melhorias_v3.md` | 25,2 KB | Proposta/prompt: substituir análise estática (IF/ELSE) por IA. | **Proposta não implementada** (planejamento). | 🟡 **Consolidar** (backlog de ideias) |
| `melhorias_v4.md` | 28,3 KB | Histórico/planejamento: hierarquia Jira (iniciativas/épicos/visão executiva). | Parcialmente implementada (hierarchy existe). | 🟢 **Consolidar** em histórico |
| `melhorias_v5.md` | 3,8 KB | Prompt de especificação do roadmap/Gantt (feature). | Implementada (`hierarchy/roadmap`). | 🟢 **Consolidar** ou remover (prompt já consumido) |
| `melhorias_v6.md` | 0,2 KB | 2 linhas soltas: uma URL + ideia de report copiável por assignee. | **Rascunho mínimo** — praticamente vazio; ideia já coberta pela aba Maturidade. | 🔴 **Remover** |
| `melhorias_v7.md` | 15,8 KB | Análise UX + plano do slide executivo data-driven. | Implementada (`mvp_slide/`). | 🟢 **Consolidar** em histórico |

Legenda: ✅ manter · 🟡 manter com ajuste/consolidar como backlog · 🟢 consolidar em histórico · 🔴 remover/arquivar.

---

## Conflito detectado — RESOLVIDO (10/09/2026)

**`aba_arquivada_insights.md` estava desatualizado e contradizia o estado atual.**
O documento afirmava que a aba Insights foi removida da navegação em 21/08/2026, mas na sprint de saneamento (Item 3) o link **Insights foi readicionado à nav de todas as páginas** para o badge de alertas do `nav-alerts.js` voltar a funcionar.

**Ação tomada:** o arquivo foi **atualizado** — agora registra o ciclo arquivamento→reativação, deixa claro que a aba está ativa e que Insights e Maturidade coexistem. Vira um registro histórico, não um estado "arquivado".

---

## Recomendação de consolidação dos `melhorias_v*`

Os 7 arquivos `melhorias_v1..v7` são **prompts/planos históricos** de evolução (não são documentação viva de referência). Somam ~93 KB e poluem a raiz. Sugestão:

1. Criar uma pasta `docs/historico/` (ou `docs/melhorias/`) e mover `melhorias_v1..v7` para lá.
2. Opcional: criar um `docs/historico/README.md` com um índice de uma linha por versão (o que cada uma entregou/propôs), preservando rastreabilidade sem ocupar a raiz.
3. Casos especiais:
   - `melhorias_v6.md` (2 linhas, ideia já coberta pela Maturidade) → **remover**, ou incorporar como uma linha no índice.
   - `melhorias_v3.md` (IA para análises) → **não implementado**; mover para um `docs/backlog.md` como ideia futura, em vez de histórico.

Resultado: raiz do projeto fica só com a documentação viva (`DATASHEET`, `MAPEAMENTO_PROJETO`, `ROTEIRO_CORRECAO_SPRINT`, `design-system`) + READMEs nas subpastas.

---

## Resumo executivo

- **Desatualizados — CORRIGIDOS (10/09/2026):** `exporter_jira/README.md` (CLI/args/hierarquia/caminho) e `aba_arquivada_insights.md` (reativação da aba).
- **Manter como está:** `DATASHEET.md`, `MAPEAMENTO_PROJETO.md`, `ROTEIRO_CORRECAO_SPRINT.md`, `design-system.md`, `mvp_slide/README.md`.
- **Pendente (não executado — aguarda decisão):** consolidar `melhorias_v1, v2, v4, v5, v7` em `docs/historico/`; reclassificar `melhorias_v3` como backlog; remover `melhorias_v6` (rascunho vazio).

> Nesta rodada foram atualizados **apenas os documentos desatualizados** (os dois acima). Consolidações e remoções **não** foram executadas — permanecem como sugestão para sua decisão.
