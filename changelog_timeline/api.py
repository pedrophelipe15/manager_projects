"""Manager Projects API — ponto de entrada (uvicorn api:app).

Só monta a aplicação via kernel. A lógica vive em:
  kernel/    registry de módulos, contrato (Module) e app factory
  modules/   manifests dos módulos (flow, hierarchy)
  routers/   APIRouters por domínio (movidos para modules/<id>/ na fase 8)
  core/      conexão com issues.db e criação das tabelas de configuração
Quais módulos sobem é definido em config/modules.yaml.
"""
from kernel.app_factory import create_app

app = create_app()
