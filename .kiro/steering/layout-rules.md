# Regras de Layout — Espaçamento Obrigatório

> **Racional teórico:** o *porquê* de cada regra abaixo (cor, tipografia, tamanho,
> paleta de gráfico, contraste) está documentado em
> [`changelog_timeline/docs/GUIA-DESIGN-DASHBOARD.md`](../../changelog_timeline/docs/GUIA-DESIGN-DASHBOARD.md),
> baseado em Tufte, Few, Munzner, Cleveland & McGill e WCAG. Consulte-o ao criar
> telas novas. As regras aqui são o *como*; o guia é o *por quê*. Fonte única de
> tokens: `changelog_timeline/tokens.css`.

Toda nova página HTML do projeto (tanto raiz quanto hierarchy/) DEVE seguir o padrão de espaçamento:

## Body

```css
body {
    font-family: 'Inter', sans-serif;
    background-color: #0f172a;
    color: #f8fafc;
    min-height: 100vh;
    padding: 2rem 0.5rem;
    background-image:
        radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.1) 0px, transparent 50%);
    background-attachment: fixed;
}
```

## Container principal

```css
.page-container {
    max-width: 100%;
    margin: 0 auto;
    padding: 1.5rem 0.5rem;
}
```

## Navegação (nav-bar) — FONTE ÚNICA COMPARTILHADA

> **Atualizado (Onda 2 UX, 2026-09-15):** a nav deixou de ser HTML duplicado em cada
> página e passou a ser **injetada por `nav.js`**, com estilo em `nav.css`. A ordem
> agora é **agrupada por pergunta do gestor**, em vez de lista plana. Isto substitui
> a antiga regra de "ordem fixa em nível único".

Toda página raiz DEVE:

1. Incluir `<link rel="stylesheet" href="nav.css?v=1">` no `<head>`.
2. Ter um placeholder vazio no topo do container: `<nav id="main-nav" class="nav-bar"></nav>`.
3. Incluir `<script src="nav.js?v=1"></script>` (após `context.js`, antes do script da página).

NUNCA escrever os links da nav à mão em cada página, NUNCA usar inline styles ou
`onmouseover`/`onmouseout`. A aba ativa é detectada automaticamente pelo `nav.js`
com base no `pathname`.

### Agrupamento (definido em `nav.js`)

A nav é organizada por **pergunta que o gestor faz**, nos grupos e ordem abaixo:

| Grupo | Abas | Pergunta |
|-------|------|----------|
| Minha Visao | Minha Visao | O que preciso fazer hoje? |
| Prazos | Compromisso, Previsibilidade | Vamos entregar? |
| Pessoas | Maturidade, Pessoas | Quem precisa de ajuda? |
| Fluxo | Gargalo e Fluxo, Portfolio, Dashboard | Onde trava? |
| Hierarquia | Hierarquia | Como está a iniciativa? |
| Dados | Inconsistencias, Configuracoes | Dá pra confiar no número? |

- Para adicionar/remover/reordenar abas, edite **apenas** o array `GROUPS` em `nav.js`.
  A mudança reflete em todas as páginas de uma vez (não editar página por página).
- `insights.html` foi **removida da nav** (arquivada em 21/08/2026); o arquivo permanece
  acessível por URL direta, mas não aparece na navegação.
- O módulo `hierarchy/` mantém sua nav interna própria (`hierarchy/nav.js`).

```css
.nav-bar {
    display: flex;
    gap: 1rem;
    padding: 0.75rem 1.5rem;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
}
.nav-link {
    padding: 0.4rem 0.8rem;
    color: #94a3b8;
    text-decoration: none;
    font-size: 0.9rem;
    font-weight: 500;
    border-radius: 6px;
    transition: all 0.2s;
}
.nav-link:hover { color: #f8fafc; background: rgba(255,255,255,0.05); }
.nav-link.active { color: #3b82f6; background: rgba(59, 130, 246, 0.1); }
```

## Header da página

```css
.page-header h1 {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}
.subtitle {
    color: #94a3b8;
    font-size: 1rem;
    margin-top: 0.3rem;
}
```

O header DEVE usar `font-size: 2rem` para h1 e `1rem` para subtitle. NUNCA usar 2.5rem ou valores maiores.

## Regras

1. O body DEVE ter `padding: 2rem 0.5rem`, background `#0f172a` com os dois radial-gradients e font Inter.
2. O conteúdo da página deve estar dentro de um container com `max-width: 100%`, centralizado (`margin: 0 auto`), e com padding de `1.5rem 0.5rem`.
3. A nav-bar é INJETADA por `nav.js` num placeholder `<nav id="main-nav" class="nav-bar"></nav>` e estilizada por `nav.css`. NUNCA escrever links à mão, usar estilos inline ou onmouseover/onmouseout.
4. A nav é AGRUPADA POR PERGUNTA (ver tabela acima). A ordem dos grupos e das abas é definida no array `GROUPS` de `nav.js` — não em cada página.
5. Para adicionar/remover/reordenar uma aba, edite APENAS `nav.js`. A mudança reflete em todas as páginas simultaneamente.
6. Nav links DEVEM usar: font-size `0.9rem`, font-weight `500`, padding `0.4rem 0.8rem`, border-radius `6px`, transition `all 0.2s`.
7. Active link: cor `#3b82f6`, bg `rgba(59, 130, 246, 0.1)`.
8. Hover link: cor `#f8fafc`, bg `rgba(255,255,255,0.05)`.
9. Em mobile (max-width: 768px), reduzir padding do container para `1rem`.
10. As páginas de referência que seguem o padrão correto são: `minha-visao.html` e `compromisso.html` (nav compartilhada + estados de loading/erro/vazio), `wave1.html`, `inconsistencies.html`, `hierarchy/dashboard-v2.html`.
11. Gráficos Chart.js devem usar `.chart-container { height: 320px; width: 100%; }` dentro do container.
12. O plugin `chartjs-plugin-datalabels` é obrigatório em todos os gráficos de barras, com: font 18px bold, cor branca, centralizado na barra, ocultar zeros.

## Filtros de Tabela — Padrão Obrigatório

Toda tabela com dados filtráveis DEVE usar o modelo de **dropdown com checkboxes** (multi-select). NUNCA usar `<select multiple>` nativo.

### Estrutura HTML

```html
<div class="filters-row">
    <!-- Cada filtro é um dd-wrapper -->
    <div class="dd-wrapper" id="filter-{campo}">
        <button class="dd-toggle" onclick="toggleDropdown('filter-{campo}')">
            <span class="dd-label">{Label}</span>
            <span class="dd-count" id="filter-{campo}-count"></span>
            <span class="dd-arrow">&#9662;</span>
        </button>
        <div class="dd-menu">
            <label class="dd-option">
                <input type="checkbox" value="{valor}" onchange="onFilterChange()">
                <span>{valor}</span>
            </label>
            <!-- ... mais opções -->
        </div>
    </div>
    <button class="btn-clear-filters" onclick="clearFilters()">Limpar</button>
</div>
```

### CSS obrigatório

```css
.filters-row { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; align-items: center; }
.dd-wrapper { position: relative; }
.dd-toggle {
    display: flex; align-items: center; gap: 0.4rem;
    background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255,255,255,0.1);
    color: #f8fafc; padding: 0.4rem 0.75rem; border-radius: 6px;
    font-size: 0.8rem; font-family: inherit; cursor: pointer; transition: border-color 0.2s;
}
.dd-toggle:hover { border-color: #3b82f6; }
.dd-label { color: #94a3b8; }
.dd-count { color: #3b82f6; font-weight: 600; font-size: 0.75rem; }
.dd-arrow { color: #64748b; font-size: 0.65rem; }
.dd-menu {
    display: none; position: absolute; top: calc(100% + 4px); left: 0;
    background: #1e293b; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
    min-width: 180px; max-height: 220px; overflow-y: auto; z-index: 100;
    box-shadow: 0 10px 25px rgba(0,0,0,0.4); padding: 0.4rem 0;
}
.dd-menu.open { display: block; }
.dd-option {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.4rem 0.75rem; font-size: 0.78rem; color: #f8fafc;
    cursor: pointer; transition: background 0.15s;
}
.dd-option:hover { background: rgba(255,255,255,0.05); }
.dd-option input[type=checkbox] { accent-color: #3b82f6; width: 14px; height: 14px; cursor: pointer; }
.btn-clear-filters {
    background: none; border: 1px solid rgba(255,255,255,0.1);
    color: #94a3b8; padding: 0.4rem 0.75rem; border-radius: 6px;
    font-size: 0.78rem; cursor: pointer; font-family: inherit; transition: all 0.2s;
}
.btn-clear-filters:hover { color: #f8fafc; border-color: #3b82f6; }
```

### Comportamento obrigatório

- Dropdown abre ao clicar no botão toggle
- Fecha ao clicar fora (document click listener)
- Badge com contagem de itens selecionados `(N)`
- Filtragem imediata ao marcar/desmarcar checkbox (sem botão "Aplicar")
- Botão "Limpar" reseta todos os filtros
- **Filtros dinâmicos e cascateantes:** ao selecionar um filtro de nível hierárquico superior (ex: Iniciativa), os dropdowns dos níveis inferiores (Épico, Projeto, Status, Assignee) DEVEM recalcular suas opções mostrando apenas valores relevantes ao contexto filtrado
- Seleções que se tornam inválidas após recálculo devem ser removidas automaticamente
- Checkboxes marcados devem ser preservados ao reconstruir o dropdown (usar parâmetro `selected` no builder)
- Referência de implementação: `hierarchy/roadmap.js` (filtros dinâmicos), `hierarchy/epic-health.js` (filtros simples)

### Ordenação de colunas

Toda tabela com dados DEVE ter headers clicáveis para ordenação:
- Classe `.sortable` no `<th>`
- Indicador visual: ↕ (neutro), ↑ (ascendente), ↓ (descendente)
- Click alterna entre asc/desc
- Ordenação numérica para valores numéricos, lexicográfica para texto
