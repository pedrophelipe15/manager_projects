# Guia de Design — Dashboard de Indicadores de Gestão

Este guia documenta **por que** cada decisão visual do projeto foi tomada, ligando
princípio teórico → regra prática → token em `tokens.css`. Serve de norte ao criar
qualquer tela nova. Não é gosto: é percepção visual aplicada.

Público do produto: ~10 líderes/gestores, cada um com 2 projetos. Eles chegam com
uma pergunta ("estão cumprindo prazo? o que está travado?") e precisam sair com uma
decisão. Todo o design serve a isso.

---

## 1. Fundamentos (a ciência por trás)

Quatro fontes sustentam praticamente tudo aqui:

| Fonte | Contribuição central |
|-------|----------------------|
| **Cleveland & McGill (1984)** | Hierarquia de precisão perceptual: **posição > comprimento > ângulo > área > cor**. Cor é dos canais menos precisos para quantidade. |
| **Tamara Munzner** — *Visualization Analysis and Design* | "Marks & channels": **matiz (hue)** para categorias; **luminosidade/saturação** para ordem. Não misturar. |
| **Stephen Few** — *Information Dashboard Design* | Referência específica de dashboard de gestão/BI. Uso contido de cor, combate ao "chartjunk", sparklines. |
| **Edward Tufte** — *Visual Display of Quantitative Information* | "Data-ink ratio": maximize a tinta que é dado, elimine a que é decoração. |
| **Colin Ware** — *Information Visualization: Perception for Design* | A base de percepção: pré-atenção, canais visuais. |

A consequência prática número 1: **o número e a posição carregam o dado; a cor
carrega categoria ou alerta — nunca magnitude fina.**

---

## 2. Cor

### 2.1 As três famílias de paleta (escolha pelo tipo de dado)

| Família | Quando usar | Como | Onde no projeto |
|---------|-------------|------|-----------------|
| **Categórica** (qualitativa) | Categorias sem ordem (projetos, tipos, status) | Matizes distintos, ~mesma luminosidade | `--chart-1..6` |
| **Sequencial** | Valores de baixo→alto (throughput, contagem) | 1 matiz, luminosidade crescente | derivar de `--action` |
| **Divergente** | Há um ponto médio significativo (acima/abaixo da meta) | 2 matizes com neutro no meio | `--ok` … neutro … `--risk` |

Usar a família errada custa precisão de leitura real: um
[estudo de 2024](https://arxiv.org/abs/2404.03787) mediu ~91% de acerto com paletas
categóricas multi-matiz contra ~81% com sequenciais de matiz único.
*(Conteúdo reformulado para conformidade com licenciamento.)*

### 2.2 O teto de ~8 cores

Para dados categóricos, **~8 matizes é o limite prático** — variedade suficiente sem
o olho perder a distinção ([referência](https://color-analysis.app/blog/best-chart-graph-color-palettes-data-visualization)).
O projeto usa **6** (`--chart-1..6`), com folga proposital. Se precisar de mais de 8
categorias num gráfico, o gráfico está errado — agrupe ("outros") ou troque de visão.
*(Conteúdo reformulado.)*

### 2.3 Cor semântica é escassa e sagrada

**Regra de ouro do projeto:** `--ok` / `--warn` / `--risk` significam **apenas**
bom / atenção / problema. Nunca decoração, nunca série de gráfico.

Por quê: cor é um atributo **pré-atentivo** — o cérebro a processa instantaneamente,
antes do consciente ([referência](https://towardsdatascience.com/the-function-of-color-in-data-viz-a-simple-but-complete-guide-c324ca4c71d0/)).
Se verde aparece em barra decorativa, badge, borda e KPI, "verde" deixa de significar
"bom" e o alerta real se perde no ruído. Por isso gráfico usa `--chart-*` (série
categórica sem carga semântica) e status usa `--ok/--warn/--risk`.
*(Conteúdo reformulado.)*

```
--ok:   #34c98a   /* só "bom / no prazo / concluído" */
--warn: #e8a93a   /* só "atenção / em risco leve" */
--risk: #ef5f5f   /* só "problema / atrasado / bloqueado" */
--chart-1..6      /* categorias em gráficos — sem significado de status */
```

### 2.4 Superfícies dessaturadas (dark mode feito certo)

Dark mode não é inverter o claro. É uma paleta própria de **cinzas escuros
dessaturados**, reservando saturação para o que precisa ser lido. Fundo puro preto
e cores saturadas cansam a vista em uso prolongado.

```
--surface-0: #0f1420   /* fundo da página */
--surface-1: #171e2e   /* card */
--surface-2: #1f2839   /* card elevado / hover */
--surface-3: #35415a   /* borda ativa / divisor forte */
```

Quatro degraus dão profundidade por elevação (mais claro = mais "à frente"), sem
sombra pesada. **Sem gradiente de fundo, sem blur** — são "chartjunk" (Tufte):
textura que compete com o dado e custa render.

### 2.5 Contraste é norma, não opinião

**WCAG 2.1:** mínimo **4.5:1** para texto normal, **3:1** para texto grande. É piso
legal de acessibilidade. Cada cor de texto do projeto foi **medida** sobre
`--surface-0`:

| Token | Uso | Contraste |
|-------|-----|-----------|
| `--text-1` `#f1f5f9` | principal | ~17:1 (AAA) |
| `--text-2` `#a8b4c6` | secundário | ~8.8:1 (AAA) |
| `--text-3` `#7d8ba1` | terciário / hint | ~5.3:1 (AA) |

> Nada de texto funcional abaixo de 4.5:1. O `#64748b` antigo (placeholders) falhava
> a 3.75:1 — foi corrigido. **Ressalva:** contraste é só uma fatia de acessibilidade;
> validação completa exige teste com leitor de tela e navegação por teclado.

---

## 3. Tipografia

### 3.1 Escala por razão modular (não tamanhos ad hoc)

Tamanhos devem "conversar" harmonicamente via uma **razão modular** (Major Second
1.125, Minor Third 1.2…). Dado denso pede razão **pequena** — saltos grandes
desperdiçam espaço vertical ([referência enterprise](https://lollypop.design/blog/2026/july/enterprise-saas-typography-rules/)).
O projeto usa **6 degraus**, piso de **12px**:

```
--fs-xs:  12px   /* badge, label de KPI, header de tabela */
--fs-sm:  13px   /* célula de tabela, texto de filtro */
--fs-md:  14px   /* corpo, link de nav */
--fs-lg:  16px   /* subtítulo */
--fs-xl:  20px   /* título de seção */
--fs-2xl: 32px   /* h1, valor de KPI */
```

> **Piso de 12px** para texto funcional. Abaixo disso a legibilidade cai e falha
> acessibilidade. *(Conteúdo reformulado.)*

### 3.2 Números: a parte técnica que quase ninguém sabe

Duas regras específicas de dashboard:

1. **`tabular-nums`** (algarismos de largura fixa). Em coluna de números, cada dígito
   deve ocupar a mesma largura, senão as casas não alinham na vertical e some a
   comparação de magnitude. CSS: `font-variant-numeric: tabular-nums`. Já aplicado
   nas tabelas e KPIs (`.data-table td.num`, `.pc-num`).

2. **Numerais neutros, baixo contraste de forma.** Quanto mais denso o dado, mais
   "calma" a forma do numeral — formas decorativas atrasam a varredura
   ([referência](http://ic-hope.com/)). Por isso **Inter** (humanista neutra) é a
   fonte do projeto. Alternativas equivalentes: IBM Plex Sans, Roboto, Source Sans.
   *(Conteúdo reformulado.)*

### 3.3 Par de fontes

Convenção enterprise: sans-serif humanista para UI + monoespaçada para blocos densos
de número/código. Para gestão, **uma sans-serif única com `tabular-nums` resolve** —
é o que o projeto faz (Inter).

---

## 4. Tamanho, espaçamento e layout

### 4.1 Hierarquia visual

O KPI mais importante é o **maior elemento** e fica no **topo-esquerda**, onde o olho
pousa primeiro (leitura em F/Z). Valor de KPI usa `--fs-2xl`; label usa `--fs-xs`. O
contraste de tamanho é o que diz "olhe aqui primeiro".

### 4.2 Densidade é uma feature (com escolha)

Dashboard de gestão não é landing page: o trabalho é **tornar a ação barata** e caber
muito na tela. Mas densidade deve ser **escolha do usuário** — daí o toggle
compacto/confortável (`ui.js`, `data-density` no `<html>`). Compacto aperta padding
de tabela/KPI; confortável respira.

### 4.3 Grade de 4px

Todo espaçamento é múltiplo de uma unidade base. Dá ritmo e alinhamento sem decisão
caso a caso.

```
--sp-1: 4px   --sp-2: 8px   --sp-3: 12px   --sp-4: 16px
--sp-5: 20px  --sp-6: 24px  --sp-8: 32px
```

### 4.4 Gráficos

- Altura padrão `320px`, largura 100% (`.chart-container`).
- Barras usam `chartjs-plugin-datalabels` (rótulo direto na barra > ler o eixo).
- Série categórica usa `--chart-*`, **nunca** `--ok/--warn/--risk`.
- Cleveland: para comparar valores, prefira **barra (comprimento)** a pizza (ângulo/área).

---

## 4b. Componentes reutilizaveis

### Tooltip explicativo de metrica (`CTUI.infoTooltip`)

Transparencia de calculo gera confianca: todo big number (score, KPI, %) deveria poder
explicar de onde veio. O componente `.ct-tip` (estilo em `ui.css`) + `CTUI.infoTooltip()`
(em `ui.js`) padroniza isso — aparece no hover/focus do elemento-alvo.

Uso:

```html
<span class="ct-tip-wrap" tabindex="0" role="button" aria-label="Como este numero e calculado">
  <span class="meu-big-number">54.1%</span>
  <!-- HTML gerado por CTUI.infoTooltip(...) -->
</span>
```

```js
const tip = CTUI.infoTooltip({
  title: 'Como o score e calculado',
  formula: 'Score = mantidas &divide; total &times; 100',
  calc: '387 &divide; 715 &times; 100 = <strong>54.1%</strong>',
  rows: [
    { label: 'Mantidas (1a data)', value: 387, tone: 'good' },
    { label: 'Prazo empurrado (3x+)', value: 53, tone: 'bad' },
    { label: 'Total com prazo', value: 715, total: true },
  ],
  note: 'Explicacao curta do que cada termo significa.',
  // position: 'left' | 'up'  (opcional; default abre abaixo/direita)
});
```

`tone` aceita `good | info | warn | bad` (usa os tokens semanticos). Sublinhe o alvo
com borda pontilhada (`border-bottom: 1px dotted var(--border-strong)`) para sinalizar
que e interativo. Acessivel por teclado (focus/focus-within).

---

## 5. Checklist ao criar uma tela nova

- [ ] Incluir `tokens.css` antes de tudo; usar só `var(--token)`, zero hex solto.
- [ ] `--ok/--warn/--risk` só para significado. Gráfico usa `--chart-*`.
- [ ] Escolher a família de paleta certa para o tipo de dado (§2.1).
- [ ] Texto ≥ 12px; contraste ≥ 4.5:1 (usar `--text-1/2/3`).
- [ ] Números em coluna com `tabular-nums` e alinhados à direita.
- [ ] KPI mais importante = maior, topo-esquerda.
- [ ] Sem gradiente/blur de fundo; superfície sólida por elevação.
- [ ] Espaçamento na grade de 4px.
- [ ] Nav via `nav.js`/`nav.css` (não escrever à mão).
- [ ] Estados distintos: loading (skeleton), vazio (com ação), erro (com retry).
- [ ] Tabela grande: header sticky + botão copiar (`ui.js`).
- [ ] Big number/KPI/%: tooltip explicativo do cálculo via `CTUI.infoTooltip` (§4b).

---

## 6. Referências

**Livros (fonte primária):**
- Edward Tufte — *The Visual Display of Quantitative Information*
- Stephen Few — *Information Dashboard Design* (o mais direto para dashboard de gestão)
- Tamara Munzner — *Visualization Analysis and Design*
- Colin Ware — *Information Visualization: Perception for Design*
- Cleveland & McGill (1984) — *Graphical Perception* (Journal of the American Statistical Association)

**Web (verificado 2026):**
- [Revisiting Categorical Color Perception in Scatterplots (arXiv 2024)](https://arxiv.org/abs/2404.03787)
- [Best Chart & Graph Color Palettes](https://color-analysis.app/blog/best-chart-graph-color-palettes-data-visualization)
- [The Function of Color in Data Viz](https://towardsdatascience.com/the-function-of-color-in-data-viz-a-simple-but-complete-guide-c324ca4c71d0/)
- [B2B SaaS Typography Rules for Dashboard UI](https://lollypop.design/blog/2026/july/enterprise-saas-typography-rules/)
- [Number Fonts for Data Visualization](http://ic-hope.com/)
- [Typography for Data-Dense Enterprise UI](https://fontly.io/typography-in-enterprise-ui/)
- [Munzner — Marks, Channels, and Color (slides)](https://www.cs.ubc.ca/~tmm/talks/minicourse14/visualise19.pdf)

*As referências web foram reformuladas e resumidas para conformidade com restrições de licenciamento.*
