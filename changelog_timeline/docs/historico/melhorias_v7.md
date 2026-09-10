# Melhorias v7 — Slide Executivo por Iniciativa (data-driven)

> Analise UX + plano de implementacao para transformar o template estatico
> `temp/slide_unico_diretoria_visual_impacto_xlsx.html` em uma pagina viva
> alimentada pelo `hierarchy.db`, parametrizada por `?key=GPPGI-325`.
>
> Autora da analise: Sally (UX Designer) — Metodo BMad.

---

## 1. Objetivo

Hoje o template e um "slide de diretoria" 1366x768 com **dados 100% mockados** (hardcoded no HTML). A meta e reutilizar o mesmo layout de alto impacto executivo, porem consumindo dados reais da hierarquia (Initiative -> Epic -> Story), de forma que a pagina:

- Receba a iniciativa por URL (`/hierarchy/executive-slide.html?key=GPPGI-325`);
- Busque dados via API existente (`/api/hierarchy/*`);
- Renderize KPIs, cronograma por due date e blocos narrativos automaticamente;
- Permaneca apresentavel para projecao/print em uma unica tela.

---

## 1.1 Decisoes registradas (validadas com Pedro)

Estas decisoes orientam o MVP e sobrescrevem trechos anteriores do plano quando houver conflito:

1. **Implementacao 100% apartada.** O MVP vive em pasta propria (`changelog_timeline/mvp_slide/`), com HTML/JS/CSS proprios, **sem alterar** `api.py`, `hierarchy_metrics.py`, `hierarchy.css` nem as paginas atuais. Acesso ao `hierarchy.db` e **somente leitura** (ou via snapshot exportado — a definir).
2. **Classificacao Eco PIX/PSI e facultativa e com carga manual.** O slide funciona sem ela. A classificacao vem de um arquivo manual a parte (ex.: `mvp_slide/eco_classification.json`, mapeando `KEY -> sim/nao`), que pode ser preenchido em outro momento. Sem o arquivo, o contador Eco simplesmente nao aparece (progressive enhancement).
3. **Abordagem MVP incremental.** Comecar pequeno e validar melhorias em ciclos, em vez de entregar tudo de uma vez.
4. **Identidade visual = paleta do PNG PagBank.** O MVP adota o **tema executivo claro** (bege/branco + amarelo PagBank + teal), documentado em `design-system.md`. Isso substitui a ideia anterior (Fase 2) de reusar o `hierarchy.css` escuro.

### Decisoes ainda pendentes
- **Live x snapshot:** o slide le o `hierarchy.db` ao vivo (pasta apartada, so leitura) ou trabalha sobre um JSON exportado sob demanda (totalmente standalone)?
- **Narrativa (Objetivo/Ganhos/Indicadores/Atencao):** arquivo de config editavel no MVP (recomendado) — confirmar formato.

## 1.2 Identidade visual do MVP

A base visual do MVP e o **Design System — Paleta Executiva PagBank**, documentado em
`changelog_timeline/design-system.md`. Esse documento e reutilizavel por outras partes
do projeto e e a fonte unica de verdade para o tema executivo claro.

Resumo da paleta (detalhes e tokens CSS no design-system.md):

| Papel | Token | Cor |
|-------|-------|-----|
| Destaque / KPI hero | `--color-highlight` | Amarelo PagBank `#F5D029` |
| Numero neutro/positivo | `--color-positive` | Teal `#2E7D8A` |
| Serie de apoio / info | `--color-info` | Azul-claro `#9FD3DD` |
| Alerta / pico / atencao | `--color-alert` | Coral `#D9534F` |
| Superficie de card | `--color-card` | Bege `#EDEAE0` |
| Fundo | `--color-bg` | Off-white `#FAF9F5` |
| Faixa de titulo | `--color-title-bar` | Preto `#1C1C1C` |
| Texto | `--color-text` | Quase-preto `#1A1A1A` |

> Regra de ouro: consumir os **tokens semanticos**, nunca os hex crus. Novas cores
> entram primeiro no design-system.md.

---

## 2. Diagnostico do template atual

### 2.1 Estrutura visual (o que o slide entrega)

| Regiao | Conteudo | Origem hoje |
|--------|----------|-------------|
| Header | Titulo `[GPPGI-325] Implementacao Oracle Tier Gold` + "Objetivo" | Mockado |
| KPIs (linha superior) | Total de atividades (46), Concluidas (13 / 28.3%), A fazer (33 / 71.7%), Contador Ecossistema PIX/PSI (15 sim / 18 nao) | Mockado |
| Bloco narrativo | Ganhos previstos, Indicadores-alvo, Pontos de atencao | Mockado |
| Cronograma | Tabela por Periodo (mes) -> Data -> Qtde -> Lista de atividades (tags), com cores por concentracao e tag Eco sim/nao | Mockado |
| Footer | Legenda de concentracao + legenda Eco + data de atualizacao | Mockado |

### 2.2 Pontos POSITIVOS (manter)

- **Hierarquia visual forte.** Titulo -> KPIs -> narrativa -> cronograma segue o fluxo de leitura executivo (do "quanto" para o "quando"). Otimo para diretoria.
- **Densidade calibrada.** Cabe tudo em uma tela sem scroll (o `.slide` e fixo em 1366x768). Ideal para projecao e export para imagem/PDF.
- **Codificacao por cor consistente.** Concentracao alta/media/baixa (vermelho/ambar/cinza) e Eco sim/nao (verde/vermelho) sao intuitivas e reforcadas por legenda no footer.
- **Semantica de acessibilidade iniciada.** Uso de `aria-label` nas secoes e `role="img"` no slide — bom ponto de partida.
- **Agrupamento temporal inteligente.** Cronograma com `rowspan` por mes + subtotal mensal comunica carga de trabalho por periodo de forma imediata.
- **Paleta coerente com o produto.** As variaveis CSS (fundo escuro, accent ambar/ciano) conversam com o restante do dashboard.

### 2.3 Pontos NEGATIVOS (corrigir/decidir)

1. **Largura fixa em px (1366x768) nao e responsiva.** Quebra em telas menores e nao segue as regras de layout do workspace (`body padding: 2rem 0.5rem`, container `max-width: 100%`, media query mobile). Precisa de estrategia: manter modo "slide fixo" para print E oferecer modo responsivo para tela.
2. **Fonte fora do padrao.** Usa `Segoe UI/Calibri`; o padrao do projeto e **Inter**. Divergencia visual com as demais paginas.
3. **Sem navegacao.** Nao tem a nav-bar padrao. Como e um "slide", isso pode ser intencional, mas dificulta voltar ao dashboard.
4. **Cores hardcoded, nao usam o design system.** O template define suas proprias variaveis (`--bg0`, `--accent: #f9c74f`) em vez de reutilizar `hierarchy.css`. Gera manutencao dupla.
5. **`role="img"` no slide inteiro e um risco de acessibilidade.** Marca TODO o conteudo textual como uma unica imagem para leitores de tela — as tabelas e KPIs viram invisiveis semanticamente. Deve ser removido quando o conteudo for real (dados reais sao legiveis; nao precisam ser "imagem").
6. **Contraste de alguns textos.** `#a7b1c2` sobre fundo escuro em fonte 10-11px fica no limite do WCAG AA para texto pequeno. Revisar.
7. **Datalabels/plugin nao usados.** As regras de layout do projeto exigem `chartjs-plugin-datalabels` em graficos de barra — o template nao tem grafico, so tabela. Se adicionarmos um grafico de carga por mes, precisa seguir a regra.

### 2.4 Mapeamento dado a dado (template x hierarchy.db)

Legenda: **[OK]** ja disponivel · **[FACIL]** query trivial nova · **[GAP]** nao existe, precisa de nova fonte de dados.

| Elemento do slide | Campo/calculo | Status |
|-------------------|---------------|--------|
| Titulo `[KEY] summary` | `h_initiatives.key`, `.summary` | **[OK]** via `/api/hierarchy/initiative-health?key=` |
| Total de atividades | `progress.total_stories` | **[OK]** |
| Concluidas + % | `progress.done_stories` / total | **[OK]** |
| A fazer + % | `progress.pending_count` (ou total - done) | **[OK]** |
| Lista de atividades por data | `h_stories`: key, summary, status, due_date, project_key | **[FACIL]** (ver 4.1) |
| Agrupamento por mes/data | derivar de `due_date` | **[FACIL]** |
| Qtde por mes / por dia | contagem agrupada | **[FACIL]** |
| Cor de concentracao (high/mid/low) | regra de faixa sobre a contagem | **[FACIL]** (regra no front) |
| Times envolvidos | `teams` (project_keys distintos) | **[OK]** |
| **Contador Ecossistema PIX/PSI (sim/nao)** | classificacao por atividade | **[GAP]** — nao existe campo. Ver 4.2 |
| **Objetivo (subtitulo)** | descricao da iniciativa | **[GAP]** — so existe `summary` |
| **Ganhos previstos** | texto narrativo | **[GAP]** |
| **Indicadores-alvo impactados** | texto narrativo | **[GAP]** |
| **Pontos de atencao** | texto narrativo | **[GAP]** |
| Data de atualizacao (footer) | `last_synced_at` | **[OK/FACIL]** |

**Resumo:** ~70% do slide ja pode ser preenchido com dados reais hoje. Os 30% restantes (Eco PIX/PSI + 4 blocos narrativos) **nao tem fonte de dados** e sao a principal decisao de produto deste plano.

---

## 3. Lacunas de dados e opcoes de fonte

### 3.1 GAP A — Classificacao "Ecossistema PIX/PSI (sim/nao)"

Nao existe nenhum campo/label/flag em `h_stories`. Opcoes, da mais rapida a mais robusta:

- **Opcao 1 (config manual — recomendada para MVP):** tabela/arquivo de mapeamento por prefixo de projeto ou por key. Ex.: um `eco_pix_psi.yaml` ou tabela `h_story_tags(issue_key, tag)` populada manualmente. Simples, sem depender do Jira.
- **Opcao 2 (labels do Jira):** adicionar coluna `labels` em `h_stories` e popular no export (`export_hierarchy.py`), classificando Eco a partir de um label do Jira (ex.: `pix-psi`). Requer que o time mantenha o label no Jira.
- **Opcao 3 (regra por projeto):** se "Eco = sim" mapeia para certos `project_key`, basta uma regra declarativa (ex.: `NASH`, `REYK` = sim). Rapido, mas fragil se a regra mudar.

> Decisao necessaria (Pedro): qual criterio define "Eco PIX/PSI = sim"? Isso destrava a implementacao completa do KPI e das tags.

### 3.2 GAP B — Metadados narrativos (Objetivo, Ganhos, Indicadores, Pontos de atencao)

Sao textos de negocio, nao derivaveis de dados de execucao. Opcoes:

- **Opcao 1 (recomendada):** nova tabela `h_initiative_meta(initiative_key, objetivo, ganhos_json, indicadores_json, atencao_json, updated_at)` + endpoints `GET/PUT /api/hierarchy/initiative-meta?key=` + uma pequena UI de edicao (pode viver na pagina de Configuracoes). Mantem o slide 100% editavel sem tocar em codigo.
- **Opcao 2 (leve):** arquivo `initiative_meta.yaml` keyed por initiative key, versionado no repo. Menos amigavel para usuario final, mas zero backend novo alem de leitura.
- **Opcao 3 (Jira description):** extrair `description` da iniciativa no export e parsear secoes. Fragil (depende de formatacao livre no Jira).

> Decisao necessaria (Pedro): esses textos devem ser editaveis pela UI (tabela) ou versionados no repo (YAML)?

---

## 4. Plano de implementacao (faseado)

> Toda a implementacao ocorre na pasta apartada `changelog_timeline/mvp_slide/`
> (decisao 1.1). Estrutura alvo:
>
> ```
> changelog_timeline/mvp_slide/
>   executive-slide.html        <- layout do slide, tema claro PagBank
>   executive-slide.js          <- le ?key= e monta a tela
>   executive-theme.css         <- copia dos tokens do design-system.md
>   eco_classification.json     <- carga manual OPCIONAL (KEY -> sim/nao)
>   initiative_meta.json        <- narrativa editavel (Objetivo/Ganhos/etc.)
>   README.md                   <- como usar / como preencher os arquivos
> ```

### Fase 1 (MVP) — Fundacao data-driven apartada

**Objetivo:** slide isolado, funcional, com titulo, KPIs numericos e cronograma reais.
Eco e narrativa opcionais (aparecem so se o arquivo de config existir).

1. **Acesso a dados (so leitura).**
   - Reusar as APIs existentes ao vivo: `GET /api/hierarchy/initiative-health?key=` (KPIs)
     e `GET /api/hierarchy/tree?key=` (stories via `epics[].stories[]`, ja traz
     key/summary/status/due_date/project_key). **Nenhum endpoint novo, nenhuma alteracao no backend.**
   - Alternativa standalone (se a decisao for snapshot): um pequeno script exporta um
     JSON a partir do `hierarchy.db` e o slide le esse JSON — zero dependencia do `api.py`.

2. **Pagina isolada** `mvp_slide/executive-slide.html` + `executive-slide.js`
   - Ler `?key=` via `URLSearchParams`.
   - Buscar dados (live ou snapshot) e renderizar: titulo, KPIs (total/done/pending),
     cronograma agrupado por mes com subtotal e cor por concentracao.
   - Regra de concentracao (front): `high` >= 6, `mid` 3-5, `low` 1-2 (parametrizavel).

3. **Eco PIX/PSI opcional (progressive enhancement).**
   - Tentar carregar `eco_classification.json`. Se existir, mostrar contador sim/nao +
     tags no cronograma. Se nao existir ou a story nao estiver mapeada, ocultar/neutro.

4. **Narrativa opcional.**
   - Tentar carregar `initiative_meta.json` (keyed por initiative key). Se existir,
     renderizar Objetivo + blocos de impacto. Se vazio, ocultar (nao mostrar placeholder).

5. **Estado vazio e erro:** iniciativa inexistente ou sem stories -> mensagem clara.

### Fase 2 — Tema visual (PalETA PagBank) e responsividade

6. **Aplicar o design system claro** (`design-system.md`)
   - Fonte **Inter**; copiar os tokens para `mvp_slide/executive-theme.css` (a copia
     mantem o MVP apartado; a fonte de verdade continua o `design-system.md`).
   - Amarelo = KPI hero + serie primaria; teal = numeros neutros; coral = alerta/pico;
     bege = cards; faixa preta = titulo (espelhando o PNG de referencia).
7. **Dois modos de exibicao**
   - **Modo Slide (print/projecao):** canvas fixo (ex.: 1366x768) para exportar PDF/imagem.
   - **Modo Tela (responsivo):** container fluido + media query mobile.
8. **Acessibilidade**
   - Remover `role="img"` do slide (conteudo real e semantico).
   - Texto sobre amarelo sempre escuro (`--ink`), nunca branco.
   - Contraste AA; tabela com `<caption>` e headers `scope`.

### Fase 3 — Metadados e classificacao (destrava os GAPs)

7. **Eco PIX/PSI** — implementar a fonte escolhida (secao 3.1). Adicionar KPI contador + tags `eco-sim`/`eco-nao` no cronograma.
8. **Metadados narrativos** — implementar a fonte escolhida (secao 3.2). Renderizar Objetivo + os 3 blocos de impacto. Se vazio, ocultar o bloco (nao mostrar placeholder na diretoria).

### Fase 4 — Refinos e integracao

9. **Grafico opcional de carga por mes** (barras) seguindo a regra do workspace: `chartjs-plugin-datalabels`, fonte 18px bold, branco, ocultar zeros, `.chart-container { height: 320px }`.
10. **Botao de export** (PDF/PNG) e link a partir do `initiative-health.html` ("Ver slide executivo").
11. **Data de atualizacao real** no footer via `last_synced_at`.

---

## 5. Boas praticas a aplicar

- **Isolamento total:** MVP em `mvp_slide/`, so leitura de dados, sem tocar em codigo/paginas existentes.
- **Separacao dado/apresentacao:** logica de agrupamento e faixa de cor em funcoes puras no JS (testaveis), sem HTML string espalhado.
- **Progressive enhancement:** Eco e narrativa sao opcionais; sem o arquivo de config, o bloco some (nunca "N/A" para diretoria).
- **Design tokens unicos:** consumir os tokens semanticos do `design-system.md`; nunca hex crus. Novas cores entram primeiro no design system.
- **Acessibilidade WCAG AA:** contraste, semantica de tabela, remover `role="img"`, texto escuro sobre amarelo. (Validacao completa exige teste manual com leitor de tela.)
- **Idempotencia de dados:** o slide reflete exatamente o `hierarchy.db`; nenhuma metrica "inventada" no front.
- **Parametrizacao:** faixas de concentracao e criterio Eco vindos de config, nao hardcoded.

---

## 6. Status das decisoes

**Resolvidas (ver 1.1):**
- [x] Implementacao apartada em `mvp_slide/`.
- [x] Eco PIX/PSI facultativa + carga manual via `eco_classification.json`.
- [x] Abordagem MVP incremental.
- [x] Identidade visual = paleta PagBank do PNG (`design-system.md`).

**Pendentes (nao bloqueiam a Fase 1):**
- [ ] **Live x snapshot:** ler `hierarchy.db` ao vivo (via APIs existentes) ou trabalhar sobre um JSON exportado (standalone)?
- [ ] **Formato da narrativa:** confirmar `initiative_meta.json` como fonte editavel.
- [ ] **Criterio detalhado do Eco:** o `eco_classification.json` sera preenchido a mao (KEY -> sim/nao); confirmar se ha regra auxiliar (ex.: prefixo de projeto) para pre-popular.

---

## 7. Proximo passo sugerido

Iniciar a **Fase 1 (MVP)** — pasta `mvp_slide/` isolada, renderizando titulo, KPIs e
cronograma reais com a paleta PagBank, e Eco/narrativa opcionais via arquivo de config.
Entrega um slide real e apartado para validacao rapida, sem risco para o projeto atual.
A unica escolha que muda o arranque e **live x snapshot** (secao 6).

---

## 8. Artefatos relacionados

- `design-system.md` — Paleta Executiva PagBank (tokens de cor reutilizaveis por todo o projeto).
- `temp/Captura de tela 2026-08-27 150608.png` — referencia visual da paleta (slide "Soluços do Pix").
- `temp/slide_unico_diretoria_visual_impacto_xlsx.html` — template original (estrutura/layout).
