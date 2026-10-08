# Documentação — changelog_timeline

Índice da documentação do projeto. Estes arquivos são apenas documentação
(não são servidos como páginas nem referenciados em runtime).

## Documentação viva (referência)

| Arquivo | Conteúdo |
|---------|----------|
| `DATASHEET.md` | Referência técnica: arquitetura, pipeline, schema do banco, endpoints, métricas, sync, expurgo. |
| `MAPEAMENTO_PROJETO.md` | Auditoria/mapa de scripts, dependências e rotas + status das correções. |
| `ROTEIRO_CORRECAO_SPRINT.md` | Roteiro da sprint de saneamento técnico (backlog, DoD, validação por item). |
| `design-system.md` | Fonte única de tokens de cor/paleta do tema executivo (claro). |
| `VALIDACAO_DOCS_MD.md` | Validação dos próprios arquivos `.md` (utilização, objetivo, recomendação). |

## Histórico (`historico/`)

Prompts e planos de evolução já executados ou propostos — mantidos para rastreabilidade.

| Arquivo | Tema |
|---------|------|
| `melhorias_v1.md` | Performance da pipeline (306s → 8s). |
| `melhorias_v2.md` | Engine de insights + métricas avançadas. |
| `melhorias_v3.md` | Proposta (não implementada): análise por IA no lugar de IF/ELSE. |
| `melhorias_v4.md` | Hierarquia Jira (iniciativas/épicos/visão executiva). |
| `melhorias_v5.md` | Roadmap/Gantt simplificado. |
| `melhorias_v6.md` | Rascunho: report copiável por assignee. |
| `melhorias_v7.md` | Slide executivo data-driven (mvp_slide). |
| `aba_arquivada_insights.md` | Ciclo arquivamento→reativação da aba Insights. |

> READMEs de subpacotes (`exporter_jira/README.md`, `mvp_slide/README.md`) permanecem
> junto ao respectivo código, propositalmente.
