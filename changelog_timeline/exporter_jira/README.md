# Exportador Jira Standalone

Processo de extração de dados do Jira desacoplado do projeto principal, pronto para ser copiado para outro repositório.

## O que este pacote faz

- Conecta na API Jira Cloud (`/rest/api/3`)
- Executa JQL com paginação por cursor (`nextPageToken`)
- Mapeia campos Jira para uma estrutura flat estável
- Opcionalmente extrai comentários e/ou changelog completo por issue
- Suporta cache por banco (`--db-cache`) para pular changelog de issues não alteradas
- Salva saída em arquivos `JSONL` para ingestão em outros sistemas

## Atualizações já implementadas

- Suporte a `--jql` com consulta literal
- Suporte a `--jql` apontando para arquivo `.txt`
	- Exemplo: `python export_jira.py --jql query_1.txt`
	- O conteúdo do arquivo é lido e usado como consulta JQL
	- Se o arquivo estiver vazio, o processo retorna erro informativo
- `--with-changelog`: extrai o changelog completo de cada issue (gera `changelogs.jsonl`)
- `--db-cache <issues.db>`: pula a extração de changelog de issues cujo `updated` não mudou desde a última sync
- `--skip-test`: pula o `test_connection` (usado quando chamado pela pipeline)
- Ajuda do CLI atualizada para refletir os formatos de `--jql`

## Estrutura do pacote

- `export_jira.py`: CLI principal (extração de issues + changelog/comentários → JSONL)
- `export_hierarchy.py`: extração hierárquica em cascata (Iniciativa → Épico → Story → Sub-task) que persiste direto no `hierarchy.db`
- `jira_client.py`: cliente HTTP Jira (paginação por cursor, retry com backoff, pausa em 429)
- `jira_mapper.py`: mapeamento de campos (inclui `extract_text_from_adf`, reutilizado por comentários)
- `jira_comments.py`: normalização de comentários (delega a extração de texto ADF ao `jira_mapper`)
- `.env.example`: variáveis de ambiente
- `requirements.txt`: dependências do pacote (`requests`, `python-dotenv`)

## Pré-requisitos

- Python 3.10+ (recomendado)
- Credenciais de API Jira Cloud:
	- `JIRA_BASE_URL`
	- `JIRA_EMAIL`
	- `JIRA_API_TOKEN`

## Passo a passo de utilização

### 1) Entrar na pasta do projeto

```powershell
cd C:\Pedro_Github\manager_projects\changelog_timeline\exporter_jira
```

### 2) Criar ambiente virtual

```powershell
python -m venv .venv
```

### 3) Ativar ambiente virtual (Windows PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 4) Instalar dependências

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5) Criar o arquivo de configuração `.env`

```powershell
copy .env.example .env
```

Edite o `.env` e preencha:

- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `JIRA_JQL_BASE` (opcional, usado quando `--jql` não for informado)

### 6) Executar extração

Opção A, JQL literal:

```powershell
python .\export_jira.py --jql "project = REYK ORDER BY updated DESC"
```

Opção B, JQL por arquivo `.txt`:

```powershell
python .\export_jira.py --jql query_1.txt
```

Exemplo de conteúdo do arquivo `query_1.txt`:

```text
project = REYK ORDER BY updated DESC
```

### 7) Opções úteis

Exportar também payload bruto:

```powershell
python .\export_jira.py --jql query_1.txt --raw
```

Exportar comentários:

```powershell
python .\export_jira.py --jql query_1.txt --with-comments
```

Definir diretório de saída:

```powershell
python .\export_jira.py --jql query_1.txt --output-dir output_reyk
```

Extrair changelog completo (necessário para as métricas de fluxo):

```powershell
python .\export_jira.py --jql query_1.txt --with-changelog
```

Usar cache de changelog por banco (pula issues não alteradas):

```powershell
python .\export_jira.py --jql query_1.txt --with-changelog --db-cache ..\issues.db
```

### 8) Arquivos gerados

- `issues_mapped.jsonl`
- `changelogs.jsonl` (somente com `--with-changelog`)
- `issues_raw.jsonl` (somente com `--raw`)
- `comments.jsonl` (somente com `--with-comments`)

### 9) Extração hierárquica (`export_hierarchy.py`)

Extrai a cascata Iniciativa → Épico → Story → Sub-task e persiste no `hierarchy.db`
(iniciativas e épicos: só metadados; stories e sub-tasks: metadados + changelog):

```powershell
python .\export_hierarchy.py --initiative GPPGI-325
python .\export_hierarchy.py --epics PSADB-1457,PSADB-1500
```

## Observações importantes

- Se `--jql` for omitido, o script usa `JIRA_JQL_BASE` do `.env`
- Se `--jql` for um caminho de arquivo existente, o script lê o conteúdo do arquivo como JQL
- O arquivo de JQL deve conter texto válido de consulta Jira

## Como levar para outro projeto

Copie toda a pasta `exporter_jira` e execute os mesmos passos de setup (`requirements.txt` + `.env`).
