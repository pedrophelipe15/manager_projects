# MVP — Slide Executivo por Iniciativa

Pagina apartada que renderiza um "slide de diretoria" a partir dos dados reais da
hierarquia (Initiative -> Epic -> Story), com a paleta executiva PagBank (tema claro).

> **Isolamento:** este MVP nao altera nenhum codigo, banco ou pagina do projeto.
> Ele apenas **le** dados via a API existente (`/api/hierarchy/tree`) e dois arquivos
> de configuracao opcionais desta mesma pasta.

## Como usar

1. Suba o servidor do projeto normalmente (o `api.py` serve esta pasta estaticamente).
2. Acesse no navegador, informando a iniciativa pela URL:

   ```
   http://localhost:8000/mvp_slide/executive-slide.html?key=GPPGI-325
   ```

3. Pronto. O slide mostra titulo, KPIs (total / concluidas / a fazer / times) e o
   cronograma por due date agrupado por mes e dia.

## Arquivos

| Arquivo | Papel |
|---------|-------|
| `executive-slide.html` | Estrutura da pagina (shell) |
| `executive-slide.js` | Busca dados ao vivo e renderiza tudo |
| `executive-theme.css` | Paleta PagBank (copia dos tokens do `../design-system.md`) |
| `eco_classification.json` | **Opcional.** Classificacao PIX/PSI manual |
| `initiative_meta.json` | **Opcional.** Narrativa (objetivo/ganhos/indicadores/atencao) |

## Enriquecimentos opcionais (progressive enhancement)

Ambos os arquivos abaixo sao **facultativos**. Sem eles, o slide funciona; com eles,
fica mais rico. Voce pode preencher em lote quando quiser e so recarregar a pagina.

### `eco_classification.json` — Ecossistema PIX/PSI

Mapeia a **key da atividade** para `"sim"` ou `"nao"`:

```json
{
  "IR-5898": "sim",
  "IR-5904": "nao"
}
```

- Atividades nao listadas ficam sem classificacao (nao contam no contador).
- O KPI contador Eco so aparece se houver ao menos uma atividade classificada.
- As tags no cronograma ganham cor (teal = sim, coral = nao) quando classificadas.

Como preencher em lote: abra o slide, copie as keys que aparecem nas tags do
cronograma e marque `sim`/`nao` conforme o criterio do time.

### `initiative_meta.json` — Narrativa executiva

Textos de negocio por iniciativa (chave = key da iniciativa):

```json
{
  "GPPGI-325": {
    "objetivo": "Texto do objetivo...",
    "ganhos": ["Ganho 1", "Ganho 2"],
    "indicadores": ["Indicador 1"],
    "atencao": ["Ponto de atencao 1"]
  }
}
```

- `objetivo` aparece como subtitulo no header.
- `ganhos`, `indicadores` e `atencao` viram os tres blocos de impacto.
- Blocos com lista vazia sao ocultados automaticamente.

## Paleta / design system

As cores seguem `../design-system.md` (Paleta Executiva PagBank). O `executive-theme.css`
e uma copia local dos tokens para manter o MVP apartado. Se ajustar cores, faca no
design system primeiro e depois reflita aqui.

## Regras de concentracao (cor das contagens)

Configuravel no topo do `executive-slide.js` (`CONC`):
- **Alta** (vermelho): >= 6 atividades
- **Media** (amarelo): 3 a 5
- **Baixa** (cinza): 1 a 2

## Limitacoes conhecidas (MVP)

- Le somente iniciativas (`?key=` precisa ser uma initiative).
- Depende do servidor do projeto no ar (modo "live"). Um modo snapshot (JSON exportado)
  pode ser adicionado depois, se desejado.
- Classificacao Eco e narrativa sao manuais por enquanto (ver `../melhorias_v7.md`).
