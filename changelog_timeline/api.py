"""Manager Projects API — ponto de entrada (uvicorn api:app).

Só monta a aplicação via kernel. A lógica vive em:
  kernel/    registry de módulos, contrato (Module), app factory, migrações, ConfigStore,
             jobs, estáticos da plataforma (kernel/web) e código compartilhado
  modules/   um pacote por módulo (flow, hierarchy): manifest, routers/, metrics, db,
             migrations/, config e web/ (páginas servidas por ele)
Quais módulos sobem é definido em config/modules.yaml.
"""
from kernel.app_factory import create_app

app = create_app()
