# Exportador Jira Standalone

Processo de extração de dados do Jira desacoplado do projeto principal, pronto para ser copiado para outro repositório.

## O que este pacote faz

- Conecta na API Jira Cloud (`/rest/api/3`)
- Executa JQL com paginação por cursor (`nextPageToken`)
- Mapeia campos Jira para uma estrutura flat estável
- Opcionalmente extrai comentários por issue
- Salva saída em arquivos `JSONL` para ingestão em outros sistemas

## Atualizações já implementadas

- Suporte a `--jql` com consulta literal
- Suporte a `--jql` apontando para arquivo `.txt`
	- Exemplo: `python export_jira.py --jql query_1.txt`
	- O conteúdo do arquivo é lido e usado como consulta JQL
	- Se o arquivo estiver vazio, o processo retorna erro informativo
- Ajuda do CLI atualizada para refletir o novo formato do `--jql`

## Estrutura do pacote

- `export_jira.py`: CLI principal
- `jira_client.py`: cliente HTTP Jira
- `jira_mapper.py`: mapeamento de campos
- `jira_comments.py`: normalização de comentários
- `.env.example`: variáveis de ambiente
- `requirements.txt`: dependências do projeto

## Pré-requisitos

- Python 3.10+ (recomendado)
- Credenciais de API Jira Cloud:
	- `JIRA_BASE_URL`
	- `JIRA_EMAIL`
	- `JIRA_API_TOKEN`

## Passo a passo de utilização

### 1) Entrar na pasta do projeto

```powershell
cd C:\Pedro_Codes\exporter_jira
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

### 8) Arquivos gerados

- `issues_mapped.jsonl`
- `issues_raw.jsonl` (somente com `--raw`)
- `comments.jsonl` (somente com `--with-comments`)

## Observações importantes

- Se `--jql` for omitido, o script usa `JIRA_JQL_BASE` do `.env`
- Se `--jql` for um caminho de arquivo existente, o script lê o conteúdo do arquivo como JQL
- O arquivo de JQL deve conter texto válido de consulta Jira

## Como levar para outro projeto

Copie toda a pasta `exporter_jira` e execute os mesmos passos de setup (`requirements.txt` + `.env`).
