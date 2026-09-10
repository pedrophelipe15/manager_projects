/bmad-agent-architect

Objetivo
Evoluir o mecanismo de análise dos indicadores e gráficos da ferramenta de análise de issues do Jira, substituindo a lógica estática (mockada) baseada em múltiplos IF/ELSE por um modelo centralizado utilizando IA especializada em gestão, estratégia, eficiência operacional e performance de times.

Cenário Atual
- As interpretações dos indicadores são geradas através de textos fixos definidos diretamente no código.
- Cada gráfico ou métrica possui regras próprias implementadas via IF/ELSE.
- A manutenção é complexa, pois qualquer alteração de interpretação exige ajuste de código.
- A lógica está distribuída em diversos componentes e abas da aplicação.

Proposta

1. Centralizador de Análises por IA
Criar um componente único responsável por todas as análises interpretativas da aplicação.

Responsabilidades:
- Receber os dados calculados de qualquer gráfico ou indicador.
- Identificar o tipo de métrica sendo analisada.
- Aplicar um prompt especializado em gestão e performance.
- Retornar uma análise textual contextualizada.
- Centralizar a governança de todas as análises da aplicação.

Exemplo de fluxo:

Dashboard
↓
Indicador calculado
↓
Componente Central de Análise
↓
Agente de IA
↓
Texto interpretativo exibido na tela

2. Agente Especializado
Criar um agente com persona especializada em:
- Gestão de equipes.
- Agilidade.
- Lean e Flow Metrics.
- Lead Time.
- Cycle Time.
- Eficiência operacional.
- Previsibilidade.
- Estratégia e melhoria contínua.
- Gestão de capacidade.
- Métricas de engenharia.

O objetivo é que o agente interprete os resultados de forma semelhante a um gestor experiente ou Agile Coach.

Exemplo:

Entrada:
Flow Efficiency = 37,5%

Saída:
"O time apresenta boa eficiência de fluxo, próximo da faixa de excelência. Apesar de existir tempo de espera relevante, a maior parte das demandas percorre o fluxo sem bloqueios excessivos. Recomenda-se avaliar os estados de espera para reduzir ainda mais o lead time."

3. Processamento no Momento do Cálculo
Como os dados não são atualizados continuamente, avaliar gerar as análises apenas durante o processamento dos indicadores.

Fluxo sugerido:
- Calcula métricas.
- Executa análise da IA.
- Armazena resultado.
- Reutiliza o resultado até novo recálculo.

Benefícios:
- Menor consumo de tokens.
- Melhor performance.
- Menor latência da interface.
- Possibilidade de cache das análises.

4. Configuração por Métrica
Nem todos os gráficos ou indicadores precisam ser analisados pela IA.

Criar uma configuração por componente, permitindo controlar se aquela métrica deve ou não passar pelo agente.

Exemplo:

{
  "leadTime": true,
  "cycleTime": true,
  "flowEfficiency": true,
  "aging": false,
  "throughput": true
}

Quando habilitado:
- Utiliza IA.

Quando desabilitado:
- Não gera análise.

5. Fallback para Análises Mockadas
Manter compatibilidade com o modelo atual.

Criar uma configuração global na aba "Configurações":

[ ] Habilitar análises por IA

Comportamento:
- ON → utiliza agente de IA.
- OFF → utiliza as análises mockadas atuais.

Objetivos:
- Permitir comparação entre os modelos.
- Garantir continuidade do produto em caso de indisponibilidade da IA.
- Evitar dependência obrigatória do serviço de IA.

6. Arquitetura Desejada

Configurações
    ↓
Feature Toggle IA
    ↓
Analisador Central
    ↓
Valida se a métrica possui IA habilitada
    ↓
Sim ----------------→ Agente IA
Não ----------------→ Análise Mockada
    ↓
Resultado Final
    ↓
Interface

Requisitos Não Funcionais
- Componente desacoplado dos gráficos.
- Fácil inclusão de novas métricas.
- Cache de análises.
- Baixo consumo de tokens.
- Fallback automático em caso de erro da IA.
- Observabilidade e logs das análises geradas.
- Possibilidade futura de múltiplos agentes especializados.

Resultado Esperado
Substituir progressivamente as análises estáticas por análises inteligentes, centralizadas e configuráveis, mantendo compatibilidade com o comportamento atual e reduzindo o esforço de manutenção ao adicionar novos indicadores e dashboards.

---
---

# Análise de Viabilidade — Winston (System Architect)

Data: 20/08/2026
Escopo desta seção: **análise de viabilidade apenas**. Não contém plano de implementação.

---

## 1. Veredito resumido

| Item da proposta | Veredito |
|---|---|
| Centralizar análises interpretativas | **Já existe** — a proposta descreve algo que o projeto construiu nas Ondas 1-5 do v2 |
| Feature toggle com fallback | **Aprovado** — instinto correto e não negociável para dependência externa |
| Configuração por métrica (opt-in) | **Aprovado** — evita explosão de custo e permite começar pequeno |
| Gerar no momento do cálculo (não no request) | **Aprovado com correção** — direção certa, mas o gatilho de invalidação está indefinido |
| Substituir as regras determinísticas por IA | **Não recomendado** — ver seção 4 |
| IA como camada de síntese sobre as regras | **Recomendado** — é aqui que a IA justifica o custo |

**Viável, com o enquadramento corrigido.** A proposta trata regras como "mock a ser substituído" e IA como primária. Recomendo inverter: regras permanecem a camada primária de detecção e medição; IA passa a ser camada opcional de narrativa e síntese.

---

## 2. Correção da premissa (ponto mais importante)

A proposta afirma:

> "Cada gráfico ou métrica possui regras próprias implementadas via IF/ELSE."
> "A lógica está distribuída em diversos componentes e abas da aplicação."

O que o código mostra:

**Já existe um analisador central** — `metrics/insights/`:
- `engine.py` — `InsightsEngine` com registry de regras, isolamento de erro por regra (uma regra que falha não derruba o lote), ordenação por severidade
- 24 regras em 5 arquivos: `rules_flow.py` (8), `rules_throughput.py` (4), `rules_people.py` (4), `rules_portfolio.py` (3), `rules_alerts.py` (5)
- Contrato de saída já é exatamente o que uma camada de IA precisaria consumir: `category`, `severity`, `title`, `description`, `recommendation`, `metric`, `value`, `threshold`

**No frontend existe apenas UM texto narrativo real:** `wave1.js` → Flow Efficiency (4 ramos de if/else produzindo parágrafo completo).

Todo o resto classificado como "análise espalhada" é, na verdade, lógica de apresentação:
- `wave2.js` — badge de faixa de aging (`180d+` → danger)
- `wave3.js` — `riskClass` por contagem de WIP
- `wave4.js` — `riskBadge` renderizando nível vindo do backend
- `dashboard.js` — `statusClass` por status
- `insights-page.js` — bucketing por severidade e mapeamento severidade → emoji

Isso não deve ir para uma IA. Não se consulta um LLM para decidir a cor de um badge.

**Consequência prática:** o objetivo de "centralização" declarado na proposta é atingível movendo **um** trecho de JS para uma regra Python. Custo zero, dependência externa zero. Esse é o ganho barato e deveria ser validado antes de qualquer decisão sobre IA.

---

## 3. Onde a IA agrega valor real — e onde não agrega

### Agrega valor (templates não conseguem fazer)

**Síntese cross-métrica.** Este é o argumento forte e o único que justifica a dependência externa. As 24 regras hoje operam isoladas: cada uma olha sua própria métrica e emite seu próprio insight. Nenhuma consegue afirmar:

> "Flow Efficiency em 37%, handoffs em 2.3/issue e WIP em 3.1x o throughput não são três problemas — são o mesmo problema visto de três ângulos. A causa raiz é excesso de trabalho simultâneo gerando fila entre etapas."

Correlacionar regras entre si é combinatório: com 24 regras existem centenas de pares e milhares de trios relevantes. Isso não se escreve em `if/else` — é exatamente o tipo de raciocínio em que um LLM é superior.

**Narrativa executiva.** Condensar 12 insights dispersos em três parágrafos com priorização de ação. Hoje o usuário lê 12 cards e faz essa síntese mentalmente.

**Adaptação de tom e profundidade** por público (time vs gestor vs diretoria).

### Não agrega valor (ou piora)

**Classificação de métrica única contra faixas conhecidas.** As faixas de Flow Efficiency (<15 / 15-25 / 25-40 / >40) *são* o conhecimento de domínio. Já estão codificadas e corretas. Um LLM reproduziria as mesmas faixas com variância e risco ocasional de erro. Zero ganho, custo e risco adicionados.

**Detecção determinística.** "Throughput caiu 3 semanas consecutivas?" é um laço, não um julgamento. "Coeficiente de variação > 0.7?" é aritmética. Delegar isso a um LLM troca uma resposta exata por uma resposta provável.

**Severidade que alimenta alerta.** Ver seção 5, item (b).

---

## 4. Por que não substituir as regras (Rule of Three)

Antes de abstrair ou trocar tecnologia, a abordagem atual precisa ter falhado de forma observável — idealmente três vezes. Não é o caso aqui: as 24 regras estão em produção, produzem texto contextual com números interpolados, detectam tendências em janelas móveis, calculam coeficientes de variação e cruzam thresholds. Elas funcionam.

Além disso, as regras produzem artefatos que **não podem** ser não-determinísticos:

- `severity` alimenta o **badge de alertas na nav bar** (presente nas 8 páginas)
- `severity` alimenta o bucketing da página de Insights (Alertas / Atenção / Observações / Saudáveis)
- `value` e `threshold` alimentam a exibição numérica dos cards

Se a IA passar a decidir severidade, o contador de alertas na nav pode variar entre dois carregamentos com os mesmos dados. Em ferramenta de gestão, isso destrói a confiança no produto inteiro — e a confiança é o ativo aqui, não a fluência do texto.

**Regra de invariante que eu recomendaria fixar:** número, severidade e threshold sempre vêm da camada determinística. IA produz prosa, nunca produz o número exibido.

---

## 5. Lacunas e riscos arquiteturais da proposta

### (a) Chave de invalidação de cache indefinida — risco mais grave

A proposta diz: *"Armazena resultado. Reutiliza o resultado até novo recálculo."*

Não existe um evento único de "novo recálculo" neste sistema:
- `_run_sync` roda por projeto, sob demanda
- `/api/metrics/wave1/recalculate` é um caminho separado
- Métricas de Wave 2/3/4 **não têm persistência** — são calculadas ao vivo a partir de `issues`, `metrics` e `parsed_changelogs` a cada request

Ou seja: os números da Wave 3 podem mudar sem que nenhum "recálculo" tenha sido disparado (basta uma sync alterar `issues`).

**Falha resultante:** número correto na tela ao lado de um parágrafo descrevendo os números do mês passado. Isso é pior do que não ter análise nenhuma — é erro silencioso, e o usuário não tem como perceber.

**Mitigação necessária:** cache indexado por hash do payload de entrada (`input_hash`), não por timestamp. Se o hash não bate, o texto não é servido. Sem isso, eu não recomendaria colocar em produção.

### (b) `/api/insights/alert-count` é um multiplicador de custo oculto

Esse endpoint alimenta o badge da nav bar — dispara em **todo carregamento de página, nas 8 páginas**. Internamente ele itera por **todos** os projetos e roda **todas** as 24 regras, sem cache.

Se a geração por IA for conectada ingenuamente ao caminho de insights, cada navegação vira `N_projetos × chamadas de LLM`. Explosão de custo e latência.

Esse endpoint precisa ser explicitamente excluído do enriquecimento por IA — ele só precisa de contagens, que vêm da severidade determinística. Vale registrar que esse endpoint já é hoje o caminho mais caro e não-cacheado do sistema, independente de IA.

### (c) Não existe camada de persistência para texto

Todas as tabelas de métricas são numéricas (`metrics`, `metrics_percentiles`, `metrics_flow`, `metrics_cfd`, `metrics_per_status`). Nenhuma armazena prosa gerada.

Ponto positivo: `wave_recalc_history` já estabelece o padrão exato necessário — chave por projeto, `UNIQUE`, `INSERT OR REPLACE`, timestamp. A tabela de análises seguiria a mesma forma, acrescentando `input_hash`, `model` e `prompt_version`.

### (d) `api.py` não tem acesso ao `.env`

`load_dotenv()` é chamado apenas em `exporter_jira/jira_client.py`, que roda em **subprocesso**. O processo da API nunca carrega o `.env`. Uma chave de API de LLM usada de dentro do `api.py` não estaria disponível hoje. Bloqueador pequeno, mas aparece no primeiro dia.

### (e) Conflito de sanitização entre os dois caminhos de renderização

Inconsistência já existente que a IA amplifica:
- `insights-page.js` → `renderInsightCard` aplica `escapeHTML` em `title`, `description` e `recommendation`. Markdown ou HTML retornado apareceria **literalmente** na tela (`**negrito**`, `<strong>`)
- `wave1.js` → Flow Efficiency injeta `<strong>` **cru** no HTML

Se texto de IA fluir para os dois lugares, um escapa e o outro executa. Além do problema visual, isso é vetor de XSS: saída de LLM é entrada não confiável.

Recomendação: restringir a saída do agente a texto puro (menor surpresa) ou adotar sanitizador com allowlist. Escolher **um** comportamento e aplicar nos dois caminhos.

### (f) Latência no momento do cálculo também não é gratuita

A sync já leva 8-26s por projeto. Chamadas sequenciais de LLM por métrica por projeto podem dobrar isso.

Correção de design ao item 3 da proposta: **uma chamada por projeto**, com todas as métricas em um único prompt — não uma chamada por métrica. Isso simultaneamente:
- reduz latência (1 chamada vs 5-8)
- reduz custo de tokens (contexto compartilhado)
- **habilita a síntese cross-métrica**, que é justamente o valor real (seção 3)

Curiosamente, o desenho mais barato é também o mais valioso. Chamada por métrica é o pior dos dois mundos: custo alto e valor baixo.

### (g) Reprodutibilidade entre usuários

Duas pessoas olhando o mesmo dashboard devem ler a mesma análise. Geração única + cache atende. Mas em cache miss, o texto muda. Requer temperatura baixa/zero, cache por padrão e regeneração **explícita** (ação do usuário), nunca implícita.

### (h) Versionamento de prompt

Ao ajustar o prompt, análises já cacheadas ficam inconsistentes entre si (algumas do prompt antigo, outras do novo). A linha de cache precisa carregar `prompt_version` e `model` para permitir detecção e invalidação em lote.

---

## 6. Trade-offs explícitos

| Dimensão | Determinístico (regras) | LLM |
|---|---|---|
| Reprodutibilidade | Total | Requer cache + temp 0 |
| Custo marginal | Zero | Por token |
| Disponibilidade | 100% | Depende de terceiro |
| Manutenção do texto | Editar código | Editar prompt |
| Síntese cross-métrica | Inviável na prática | Ponto forte |
| Auditabilidade | Total (lê-se a regra) | Requer log |
| Risco de erro factual | Zero | Real (alucinação numérica) |
| Latência | ~ms | ~s |

**Sobre alucinação numérica:** um LLM pedido para escrever *sobre* números eventualmente vai reafirmá-los errado. A mitigação estrutural é a invariante da seção 4 — a UI renderiza números da camada determinística, e o texto da IA fica ao lado, não no lugar. Se o texto precisar citar números, vale validar que todo número presente na saída existe no payload de entrada.

---

## 7. Forma e escopo recomendados

Não como plano de execução, mas como **decisão de arquitetura**: separar em três camadas independentes em vez de um switch IA/mock.

**Camada 1 — Sensores (existe, permanece determinística)**
As 24 regras. Produzem severidade, valor, threshold. Alimentam badges, contadores, cores, alertas. **Nunca** passam por IA.

**Camada 2 — Consolidação da narrativa (refactor pequeno, sem IA)**
Migrar a narrativa de Flow Efficiency do `wave1.js` para uma regra Python. Resultado: 100% da narrativa passa a viver no servidor, em um só lugar.

Isso entrega o objetivo de centralização declarado na proposta com **zero dependência externa e zero custo**. É o ganho barato e deveria vir primeiro — inclusive porque valida se o problema percebido era mesmo "falta de centralização" ou "falta de riqueza analítica".

**Camada 3 — Sintetizador (nova, opcional, com toggle)**
Consome o conjunto completo de insights da Camada 1 para um projeto e produz narrativa executiva com correlação entre métricas. Uma chamada por projeto. Cache por `input_hash` + `prompt_version` + `model`.

**Localização recomendada:** topo da página de Insights, como sumário executivo. **Não** distribuído por gráfico — texto de IA por gráfico é onde custo e latência pioram e onde o valor é menor.

---

## 8. Pontos da proposta que recomendo revisar

| # | Proposta original | Revisão sugerida | Motivo |
|---|---|---|---|
| 1 | Mock é fallback, IA é primária | Regras são primárias, IA é enriquecimento | Severidade/valor/threshold precisam ser determinísticos (nav badge, alertas) |
| 2 | Uma análise por métrica | Uma análise por projeto (batch) | Custo menor, latência menor e habilita a síntese cross-métrica |
| 3 | Cache "até novo recálculo" | Cache por hash do payload de entrada | Não existe evento único de recálculo; risco de texto obsoleto sobre número novo |
| 4 | Análise em todos os gráficos | Sumário executivo na página de Insights | Onde o valor é maior e o custo por token é justificável |
| 5 | Toggle global on/off | Toggle global **+** exclusão explícita do `alert-count` | Endpoint dispara em todo page load nas 8 páginas |
| 6 | (ausente) | Definir contrato de sanitização único | `insights-page.js` escapa HTML, `wave1.js` injeta cru — divergência + risco de XSS |
| 7 | (ausente) | `prompt_version` e `model` no cache | Permite invalidação em lote ao ajustar prompt |

---

## 9. Nota sobre escala e custo

Com 4 projetos e ~24 insights cada, no desenho batch (uma chamada por projeto por sync): **4 chamadas por sync completa**. Ordem de grandeza de alguns milhares de tokens de entrada e centenas de saída por chamada — custo desprezível.

No desenho por métrica: 4 projetos × 5-8 métricas = **20-32 chamadas** por sync, com contexto fragmentado e sem correlação possível.

O número reforça a recomendação: batch por projeto não é só mais barato, é o único desenho em que a IA entrega aquilo que os templates não entregam.

---

## 10. Conclusão

**Viável.** A dependência externa é justificável — mas por um motivo diferente do declarado na proposta.

O ganho não está em substituir if/else por IA (esse if/else é pouco, está quase todo centralizado, e a parte determinística deve permanecer determinística). O ganho está em **sintetizar e correlacionar** os 24 sinais que o sistema já produz e que hoje o usuário precisa cruzar mentalmente.

Recomendação de sequência de decisão:

1. **Camada 2 primeiro** (consolidar narrativa no servidor, sem IA). Barato, reversível, e revela se a dor real era centralização ou profundidade analítica.
2. **Camada 3 como experimento delimitado** — apenas página de Insights, atrás de toggle, cache por `input_hash`, uma chamada por projeto.
3. Reavaliar expansão por gráfico **somente** se a Camada 3 provar valor percebido.

Riscos que eu classificaria como bloqueadores até resolvidos: **(a)** chave de invalidação de cache e **(b)** exclusão do `alert-count` do caminho de IA. Os demais são endereçáveis durante a construção.

— Winston 🏗️


---

# Análise de Impacto ao Projeto Atual — Winston (System Architect)

Data: 20/08/2026
Escopo: avaliar se a implementação do v3 pode quebrar ou degradar funcionalidades existentes.

---

## 1. O que está em funcionamento hoje e não pode ser afetado

| Componente | O que faz | Dependência externa |
|---|---|---|
| 24 regras de insights (engine) | Detecta anomalias, gera severity/title/description | Nenhuma (sqlite3 puro) |
| Badge de alertas na nav bar (8 páginas) | Mostra contador de alertas proativos | `/api/insights/alert-count` |
| Pipeline de sync (8.2s delta) | Extrai Jira → ingere → calcula métricas | Apenas Jira API |
| Wave 1-4 endpoints | Servem dados numéricos para os gráficos | Leitura SQLite |
| Texto do Flow Efficiency | Parágrafo analítico no wave1.html | Frontend JS puro |
| Página de Insights | Renderiza cards de insight com severity/title/description | Backend determinístico |

---

## 2. Cenários de risco concretos

| # | Mudança proposta | O que pode quebrar | Risco | Mitigação |
|---|---|---|---|---|
| 1 | Adicionar chamada de IA no fluxo de sync | Sync falha se IA offline → issues não ingerem | **Alto se mal implementado** | IA deve ser passo PÓS-sync, isolado. Sync nunca depende de IA |
| 2 | Substituir regras determinísticas por IA | Badge na nav inconsistente. Alertas não-determinísticos | **Alto** | **NÃO FAZER.** Regras permanecem primárias, IA é camada adicional |
| 3 | Adicionar tabela de cache de análises | Nenhum impacto em tabelas existentes | **Zero** | `CREATE TABLE IF NOT EXISTS` — padrão já usado |
| 4 | Mover narrativa Flow Efficiency do JS para Python | Seção fica sem texto se endpoint falhar | **Baixo** | Fallback no frontend: se API retornar erro, mostra texto estático atual |
| 5 | Adicionar `load_dotenv()` no api.py | Nenhum efeito se .env não existir | **Zero** | Variáveis ficam None, toggle permanece OFF |
| 6 | Toggle IA on/off no settings | Nova tabela + endpoint, não altera nada existente | **Zero** | Independente de tudo que já existe |
| 7 | Adicionar passo de IA no `_run_wave1_recalculate` | Se IA falhar, passo é isolado — não derruba outros 6 passos | **Baixo** | Arquitetura de steps com try/except individual já existe |

---

## 3. Proteção já existente no código

O projeto possui isolamento de erro por step no recálculo:

```python
# _run_wave1_recalculate — cada step tem try/except individual
for idx, (name, fn) in enumerate(steps):
    try:
        result = fn()
        # ✓ Concluído (elapsed)s — N registros
    except Exception as e:
        # ✗ Erro (elapsed)s: mensagem
        # MAS CONTINUA para o próximo step
```

Consequência: se a IA for adicionada como step 7 nessa lista, uma falha na IA não impede que os 6 steps anteriores (métricas base, percentis, CFD, etc.) completem normalmente. O sistema opera sem análise narrativa — exatamente como opera hoje.

---

## 4. Invariantes que NÃO devem ser violados

| Invariante | Motivo | Consequência se violado |
|---|---|---|
| `Insight.severity` vem SEMPRE das regras determinísticas | Badge na nav, bucketing dos cards, contagem de alertas | Contador varia entre page loads com mesmos dados → perde confiança |
| `Insight.value` e `threshold` vêm SEMPRE das regras | Exibição numérica nos cards de insight | Número errado ao lado do texto → erro factual visível |
| `/api/insights/alert-count` NUNCA chama IA | Dispara em todo page load (8 páginas × N projetos) | Explosão de custo + latência a cada navegação |
| Pipeline sync → ingest → métricas SEM dependência externa | Se IA cair, coleta de dados e cálculos continuam | Indisponibilidade da IA = aplicação inteira parada |
| Tabelas existentes NÃO são alteradas | Migração de schema quebra backwards compatibility | Dados existentes perdidos ou corrompidos |
| Endpoints existentes NÃO mudam de contrato | Frontend depende do formato atual do JSON | Quebra em todas as 8 páginas simultaneamente |

---

## 5. Conclusão sobre impacto

### Se implementado CONFORME a análise do Winston (IA aditiva, não substitutiva):

- ✅ Nenhuma tabela existente é alterada
- ✅ Nenhum endpoint existente muda de comportamento
- ✅ Nenhuma regra existente é removida ou modificada
- ✅ A sync continua funcionando mesmo com IA offline
- ✅ O badge continua determinístico
- ✅ O fallback para texto estático é garantido pelo toggle
- ✅ Risco de quebrar funcionalidades existentes: **próximo de zero**

### Se implementado CONFORME a proposta original (IA substituindo regras):

- ❌ Badge inconsistente entre page loads
- ❌ Sync dependente de serviço externo
- ❌ Indisponibilidade da IA = aplicação sem insights
- ❌ Regressão silenciosa se prompt mudar
- ❌ Risco de quebrar funcionalidades existentes: **alto**

---

## 6. Decisão de proteção recomendada

Antes de qualquer implementação, fixar estas regras como "lei" do projeto:

1. **A IA é um enriquecimento.** Se desligada ou indisponível, o sistema funciona 100% como hoje.
2. **Números nunca vêm da IA.** Severity, value, threshold, contagens — tudo determinístico.
3. **Texto da IA nunca bloqueia rendering.** Frontend renderiza com dados determinísticos primeiro, texto de IA chega como complemento (pode ser lazy load).
4. **Nenhuma tabela existente é ALTER'd.** Só criação de tabelas novas.
5. **Toggle OFF é o default.** Sistema sai da fábrica sem dependência de IA. Ativação é opt-in explícito.

Se essas 5 regras forem respeitadas, a implementação do v3 é **segura para o projeto atual** — independente de bugs na camada de IA, mudanças de prompt, indisponibilidade de serviço ou experimentação.

— Winston 🏗️
