# Plano de Execução: Simulação de Carga e Dashboard UI

Com a arquitetura aprovada, vamos colocar a mão na massa e construir a infraestrutura real. Dividiremos a entrega nas três solicitações que você fez:

## 1. Script de Carga Full Mockada (`mock_full_load.py`)
Criarei um script em Python que será o coração da nossa simulação do Banco de Dados.
- **O que ele fará:** Lerá o arquivo `example_largest_changelog.json` como molde. Faremos um loop de 1 a 5.000 para gerar chaves de `STN-1` a `STN-5000`.
- **Lógica ETL Integrada:** O script criará o banco local `issues.db` com as 3 tabelas (`issues`, `metrics`, `parsed_changelogs`). Ele vai randomizar autores, horários e calcular o *Cycle Time / Lead Time* na hora para cada um dos 5.000 registros, gravando tudo estruturado no SQLite.
- **Objetivo:** Provar que o Python consegue calcular as métricas e popular um banco com milhares de registros em poucos segundos.

### Tabela: `issues` (Tabela Pai)
Contém os dados brutos e metadados vitais da issue, extraídos diretamente do objeto `fields` do JSON do Jira.
- `key` (PK) - Ex: STN-2034
- `summary` (Resumo/Título)
- `issuetype_name` (Extraído de `fields.issuetype.name`, ex: Story, Sub-task)
- `issuetype_hierarchy_level` (Extraído de `fields.issuetype.hierarchyLevel`, ex: 0 para Story, -1 para Sub-task)
- `status` (Status atual extraído de `fields.status.name`)
- `project_key` (Chave do projeto, extraído de `fields.project.key`, ex: STN)
- `project_name` (Nome do projeto, extraído de `fields.project.name`, ex: PS - San Antonio)
- `parent_key` (Extraído de `fields.parent.key`, se existir)
- `assignee_name` (Extraído de `fields.assignee.displayName`)
- `reporter_name` (Extraído de `fields.reporter.displayName`)
- `labels` (Array convertido para string ou JSON, ex: `["stn_demanda_interna"]`)
- `created_at` (Extraído de `fields.created`)
- `updated_at` (Extraído de `fields.updated`)
- `due_date` (Extraído de `fields.duedate`)
- `resolved_at` (Extraído de `fields.resolutiondate`)
- `executors_teams` (Mapeado do respectivo `customfield_XXXXX` no seu Jira)
- `pagseguro_teams` (Mapeado do respectivo `customfield_XXXXX` no seu Jira)
- `start_date` (Mapeado do `customfield_XXXXX` específico de Start Date, se diferente do `created`)

### Tabela: `metrics` (Métricas Pré-Calculadas)
Calculada pela pipeline durante a extração, baseada na máquina de estados que definimos. Além dos cálculos, esta tabela recebe uma cópia (desnormalização) de campos vitais para permitir consultas SQL mais rápidas e diretas, sem precisar de `JOIN` com a tabela pai.
- `issue_key` (FK -> issues.key)
- `project_key` (Cópia atualizada da issue)
- `project_name` (Cópia atualizada da issue)
- `parent_key` (Cópia atualizada da issue)
- `status` (Garante ser o status atual e mais recente da issue)
- `created_at` (Cópia atualizada da issue)
- `updated_at` (Cópia atualizada da issue)
- `due_date` (Cópia atualizada da issue)
- `resolved_at` (Cópia atualizada da issue)
- `lead_time_ms` (Tempo de criação até Done. **Garantia:** Recalculado do zero a cada Delta Sync)
- `cycle_time_ms` (Tempo total na fase In Progress. **Garantia:** Recalculado do zero a cada Delta Sync)

### Tabela: `parsed_changelogs` (Pronto para a Timeline UI)
A pipeline filtra as blacklists (ex: *Attachment*, *Checklists for Jira*) e salva apenas os eventos limpos e úteis.
- `id` (PK)
- `issue_key` (FK -> issues.key)
- `project_key` (Cópia atualizada da issue)
- `project_name` (Cópia atualizada da issue)
- `author_name`

## 2. Script de Simulação de Delta Sync (`mock_delta_sync.py`)
Este script provará que a nossa sincronização incremental funciona sem destruir a base.
- **O que ele fará:** Conectará no `issues.db`, selecionará 20 chaves (`STN-X`) aleatórias e adicionará novos eventos no changelog delas (simulando que os times trabalharam nelas hoje).
- **Lógica de Upsert:** Em seguida, o script executará exatamente a lógica arquitetural aprovada: Atualiza a Tabela Pai, DELETA os filhos antigos (`metrics` e `changelogs`) dessas 20 issues, recalcula as métricas incluindo os eventos novos, e os insere novamente.

## 3. UI/UX do Dashboard Principal (`dashboard.html`)
Para validar a fluidez da Opção C, construiremos a tela do Dashboard gerencial.
- **Bibliotecas:** Utilizarei o **Chart.js** via CDN (é leve, rápido e gera gráficos muito bonitos) e continuaremos com o CSS puro (Glassmorphism e Dark Mode) para manter a coerência visual do projeto.
- **O Layout:** 
  1. *Topo:* 3 Cards grandes mostrando as médias de Lead Time, Cycle Time e Total de Issues.
  2. *Meio:* Um Gráfico de Linha/Dispersão e um Histograma mostrando a distribuição do tempo.
  3. *Base:* Uma tabela paginada com as 5.000 issues simuladas em memória para provar a fluidez do *Virtual Scrolling* ou Paginação, sem travar a aba.
- **O Mock:** Para não precisarmos de um backend agora, injetarei 5.000 linhas de dados *fakes* diretamente no Javascript (gerados via laço de repetição) apenas para você ver o HTML/CSS renderizando essa massa brutal de informações perfeitamente.

> [!IMPORTANT]
> ## User Review Required
> 
> Como arquiteto (Winston), minha função era desenhar o modelo de dados e a topologia. O caminho está pavimentado e livre de falhas estruturais.
> 
> Você aprova que o nosso **Agente Desenvolvedor (Amelia)** assuma a partir de agora e comece a escrever esses 2 scripts em Python e o código HTML do Dashboard exatamentente como planejado acima?
