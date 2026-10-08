# Design System — Paleta Executiva PagBank

> Fonte da paleta: slide executivo "Soluços do Pix · Além dos Números"
> (`temp/Captura de tela 2026-08-27 150608.png`).
>
> Este documento e a **fonte unica de verdade** para cores, tokens e uso visual
> do tema executivo claro. Pode ser consumido por qualquer pagina do projeto
> (MVP do slide executivo e futuras telas institucionais).
>
> Ha dois temas no projeto:
> - **Tema Dashboard (escuro)** — `hierarchy/hierarchy.css`, usado nas telas operacionais.
> - **Tema Executivo (claro)** — este documento, usado em slides/apresentacoes de diretoria.

---

## 1. Paleta base (raw colors)

Valores extraidos do PNG de referencia. Sempre citar o token, nunca o hex cru, no codigo.

### Neutros / superficies (tema claro, base "areia quente")

| Token | Hex | Uso |
|-------|-----|-----|
| `--bg-page` | `#FAF9F5` | Fundo geral da pagina (off-white quente) |
| `--bg-page-alt` | `#FFFFFF` | Fundo branco puro quando precisa de contraste |
| `--surface` | `#EDEAE0` | Superficie de card padrao (bege claro) |
| `--surface-2` | `#E8E5DA` | Superficie de card alternativa / hover |
| `--border` | `#DDD8CC` | Borda de card / divisorias |
| `--header-bar` | `#1C1C1C` | Faixa preta do titulo principal |

### Tinta / tipografia

| Token | Hex | Uso |
|-------|-----|-----|
| `--ink` | `#1A1A1A` | Texto principal (quase preto) |
| `--ink-invert` | `#FFFFFF` | Texto sobre faixa preta / sobre amarelo |
| `--muted` | `#6E6E6E` | Texto secundario, labels em maiuscula |
| `--muted-2` | `#8A857A` | Texto terciario / captions sobre bege |

### Cores de marca e destaque

| Token | Hex | Uso |
|-------|-----|-----|
| `--accent` | `#F5D029` | Amarelo PagBank — KPI hero, highlight, badge |
| `--accent-strong` | `#F2C500` | Amarelo mais saturado (barras, hover do accent) |
| `--teal` | `#2E7D8A` | Azul-petroleo — numeros neutros, destaque frio |
| `--teal-strong` | `#1F6E7B` | Teal mais fechado (titulos de secao, links) |
| `--teal-light` | `#9FD3DD` | Azul-claro — segunda serie de grafico, chips |
| `--danger` | `#D9534F` | Vermelho/coral — alertas, picos, pontos de atencao |
| `--danger-soft` | `#E05B49` | Coral levemente mais quente (datalabels de pico) |

---

## 2. Tokens semanticos (o que usar no dia a dia)

Prefira SEMPRE os tokens semanticos abaixo. Eles apontam para a paleta base e
mantem o significado consistente entre telas.

| Token semantico | Aponta para | Significado |
|-----------------|-------------|-------------|
| `--color-bg` | `--bg-page` | Fundo da tela |
| `--color-card` | `--surface` | Fundo de card |
| `--color-card-border` | `--border` | Borda de card |
| `--color-text` | `--ink` | Texto de leitura |
| `--color-text-muted` | `--muted` | Rotulos e legendas |
| `--color-title-bar` | `--header-bar` | Faixa de titulo |
| `--color-highlight` | `--accent` | Destaque de maior impacto (KPI hero) |
| `--color-positive` | `--teal` | Numero neutro/positivo |
| `--color-info` | `--teal-light` | Informacao secundaria / serie de apoio |
| `--color-alert` | `--danger` | Alerta, pico, atencao |
| `--series-primary` | `--accent-strong` | Serie principal de grafico (ex.: "Interno") |
| `--series-secondary` | `--teal-light` | Serie secundaria de grafico (ex.: "Externo") |

---

## 3. Bloco CSS pronto (copiar/colar)

```css
:root {
  /* --- Paleta base --- */
  --bg-page: #FAF9F5;
  --bg-page-alt: #FFFFFF;
  --surface: #EDEAE0;
  --surface-2: #E8E5DA;
  --border: #DDD8CC;
  --header-bar: #1C1C1C;

  --ink: #1A1A1A;
  --ink-invert: #FFFFFF;
  --muted: #6E6E6E;
  --muted-2: #8A857A;

  --accent: #F5D029;
  --accent-strong: #F2C500;
  --teal: #2E7D8A;
  --teal-strong: #1F6E7B;
  --teal-light: #9FD3DD;
  --danger: #D9534F;
  --danger-soft: #E05B49;

  /* --- Tokens semanticos --- */
  --color-bg: var(--bg-page);
  --color-card: var(--surface);
  --color-card-border: var(--border);
  --color-text: var(--ink);
  --color-text-muted: var(--muted);
  --color-title-bar: var(--header-bar);
  --color-highlight: var(--accent);
  --color-positive: var(--teal);
  --color-info: var(--teal-light);
  --color-alert: var(--danger);
  --series-primary: var(--accent-strong);
  --series-secondary: var(--teal-light);

  /* --- Tipografia --- */
  --font-family: "Inter", "Segoe UI", Arial, sans-serif;

  /* --- Elevacao / raio --- */
  --radius-card: 14px;
  --radius-pill: 999px;
  --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.06);
}
```

---

## 4. Mapeamento semantico das cores (regras de uso)

Baseado em como o PNG de referencia aplica cada cor:

- **Amarelo (`--color-highlight`)** — reservado para o **numero de maior impacto** da tela
  (no PNG: o card "-82%") e para a **serie primaria** do grafico. Nao usar como cor de
  texto corrido; e cor de "holofote".
- **Teal (`--color-positive`)** — numeros neutros ou positivos, titulos de secao e links.
  E a cor "seria" que carrega a maior parte dos dados.
- **Azul-claro (`--color-info` / `--series-secondary`)** — serie de apoio no grafico
  (no PNG: "Externo") e chips informativos. Sempre subordinada ao teal.
- **Vermelho/coral (`--color-alert`)** — exclusivamente para **alerta, pico ou atencao**
  (no PNG: "60", "50", "47% concentrados"). Se tudo vira vermelho, nada e alerta —
  usar com parcimonia.
- **Bege (`--color-card`)** — superficie neutra dos cards. Da o tom "premium/quente"
  do slide. O fundo da pagina e um off-white ainda mais claro.
- **Faixa preta (`--color-title-bar`)** — apenas para o titulo principal da tela,
  criando ancora visual no topo.

### Regra de contraste de dado

Para KPIs no formato "numero · percentual" (ex.: `129 · 55%`):
- Numero absoluto em `--ink` (peso 800).
- Percentual em `--color-positive` (teal) quando neutro, ou `--color-alert` (vermelho)
  quando representa concentracao/risco.

---

## 5. Componentes de referencia (padroes visuais do PNG)

- **KPI hero:** card amarelo solido (`--color-highlight`), numero grande em `--ink`
  (contraste alto sobre amarelo), label menor em `--ink` peso medio.
- **KPI secundario:** card bege (`--color-card`), numero grande em `--color-positive`
  ou `--color-alert`, label em MAIUSCULAS + `--color-text-muted`, letter-spacing ~0.6px.
- **Grafico de barras empilhadas:** serie primaria `--series-primary` (amarelo),
  serie secundaria `--series-secondary` (azul-claro), datalabels no topo em peso bold —
  picos podem receber `--color-alert`.
- **Rodape "Informacoes importantes":** colunas com marcador quadrado em `--color-alert`
  ou `--color-positive`, titulo em `--ink` bold + descricao em `--color-text-muted`.
- **Badge/pill:** fundo `--accent` para destaque, ou contorno `--border` com fundo
  transparente para neutro; raio `--radius-pill`.

---

## 6. Acessibilidade

- Texto principal `--ink` sobre `--surface`/`--bg-page` — contraste alto, OK para AA/AAA.
- **Atencao:** texto sobre amarelo (`--accent`) DEVE ser `--ink` (escuro), nunca branco —
  branco sobre amarelo reprova no contraste.
- `--muted` em fontes <= 12px fica no limite do AA; para textos muito pequenos preferir
  `--ink` ou aumentar o peso.
- Nao comunicar informacao APENAS por cor (ex.: sim/nao, interno/externo): sempre
  acompanhar de rotulo textual ou legenda.
- Validacao completa WCAG exige teste manual com leitor de tela e ferramenta de contraste.

---

## 7. Como reutilizar em outras partes do projeto

1. Copiar o bloco CSS da secao 3 para um arquivo compartilhado (ex.:
   `changelog_timeline/shared/executive-theme.css`) e importar onde precisar.
2. Consumir SEMPRE os tokens semanticos (secao 2), nunca os hex crus.
3. Se surgir uma nova cor necessaria, adicionar primeiro na paleta base (secao 1)
   e depois expor via token semantico — mantendo este documento como fonte unica.
4. Para telas do tema escuro (dashboard operacional) continuar usando `hierarchy.css`;
   este tema e para contextos executivos/apresentacao.
