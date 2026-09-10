Preciso adicionar um novo componente de visualização de roadmap em uma página HTML já existente.

Objetivo

Criar uma seção semelhante a um roadmap/Gantt simplificado, inspirada no modelo da imagem de referência.

A visualização deve agrupar as demandas por Projeto e exibir cada Story em uma linha, posicionada na linha do tempo conforme seu Due Date.

Fonte de Dados

Utilizar os campos já disponíveis na aplicação:

Conceito da tela	Campo JiraResiliência	Projeto
Teste	Story
Data	Due Date
Status	Status
Regras de Exibição
Filtro

Exibir apenas Stories cujo Status seja diferente de:

Done
Canceled

Esses itens devem ser ignorados completamente.

Agrupamento

Agrupar as Stories pelo campo:

Plain Text
1
Projeto
Mostrar mais linhas

Cada Projeto será exibido como um cabeçalho de seção.

Exemplo:

Plain Text
1
PROJETO A
2
Story 1
3
Story 2
4
Story 3
5
 
6
PROJETO B
7
Story 4
8
Story 5
Mostrar mais linhas
Timeline

A timeline deve ser mensal, semelhante ao modelo:

Plain Text
1
AGO | SET | OUT | NOV | DEZ
Mostrar mais linhas

Posicionar cada Story de acordo com seu Due Date.

Exibição da Story

Cada Story deve aparecer como uma barra horizontal.

A barra deve ser posicionada no mês correspondente ao Due Date.

Exemplo:

Plain Text
1
Story ABC ----------------- [Outubro]
Mostrar mais linhas
Cores por Status

Aplicar cores conforme o Status da Story:

Blocked
CSS
1
background-color: #dc3545;
Mostrar mais linhas

Cor vermelha.

In Progress
CSS
1
background-color: #0d6efd;
Mostrar mais linhas

Cor azul.

Qualquer outro status
CSS
1
background-color: #6c757d;
Mostrar mais linhas

Cor cinza.

Exemplos:

Plain Text
1
Blocked -> Vermelho
2
In Progress -> Azul
3
To Do -> Cinza
4
Open -> Cinza
5
Refinement -> Cinza
6
Ready -> Cinza
7
Waiting -> Cinza
Mostrar mais linhas
Layout
Cabeçalho do Projeto

Utilizar faixa horizontal destacada ocupando toda a largura.

Exemplo:

Plain Text
1
┌───────────────────────────────────────────────┐
2
│ PROJETO PIX CORE │
3
└───────────────────────────────────────────────┘
Mostrar mais linhas
Linhas das Stories

Exibir:

Nome da Story na primeira coluna
Status na segunda coluna
Barra visual na timeline

Exemplo:

Plain Text
1
Story Status Timeline
2
────────────────────────────────────────────────────────────────
3
Ajuste Sequence Cache In Progress ███████
4
Migração OCI Blocked ████
5
Revisão Backup To Do ███
Mostrar mais linhas
Requisitos Técnicos
Utilizar HTML, CSS e JavaScript puros.
Seguir o padrão visual já existente na página.
Componente responsivo.
Não utilizar bibliotecas externas de Gantt.
O componente deve ser gerado dinamicamente a partir do dataset já carregado na página.
Ordenar Projetos alfabeticamente.
Dentro de cada Projeto, ordenar Stories pelo Due Date crescente.
Exibir tooltip ao passar o mouse contendo:
Story
Projeto
Status
Due Date
Critérios de Aceite
Apenas itens não Done e não Canceled aparecem.
Agrupamento por Projeto funcionando.
Story exibida em sua respectiva linha.
Cor correta conforme Status.
Ordenação por Due Date.
Timeline mensal visível.
Tooltip funcionando.
Layout semelhante ao roadmap da imagem de referência.

Esse prompt está suficientemente detalhado para o Kiro gerar a implementação praticamente completa sem necessidade de refinamentos adicionais.