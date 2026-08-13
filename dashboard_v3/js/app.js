/* =========================================================================
   UPLOAD, ORQUESTRAÇÃO E BOOTSTRAP DA APLICAÇÃO
   ========================================================================= */

function normalizeInput(json) {
  if (Array.isArray(json)) return json;
  if (json.issues && Array.isArray(json.issues)) return json.issues;
  throw new Error('Formato não reconhecido: esperado um array de issues, ou { "issues": [...] }.');
}

window.addEventListener('DOMContentLoaded', () => {
  const jsonUploadEl = document.getElementById('jsonUpload');
  const useSampleBtnEl = document.getElementById('useSampleBtn');
  const statusEl = document.getElementById('dataStatus');

  if (jsonUploadEl) {
    jsonUploadEl.addEventListener('change', function (e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function (ev) {
        try {
          const json = JSON.parse(ev.target.result);
          const issues = normalizeInput(json);
          render(issues, file.name);
          if (statusEl) {
            statusEl.textContent = `Dados carregados de "${file.name}" com sucesso.`;
            statusEl.className = 'ok';
          }
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = 'Erro ao ler o arquivo: ' + err.message;
            statusEl.className = 'warn';
          }
        }
      };
      reader.readAsText(file);
    });
  }

  if (useSampleBtnEl) {
    useSampleBtnEl.addEventListener('click', function () {
      render(generateSampleData(), 'dados de exemplo (sintéticos)');
      if (statusEl) {
        statusEl.textContent = 'Exibindo dados de exemplo — carregue seu export para ver os números reais.';
        statusEl.className = 'ok';
      }
    });
  }

  // Bootstrap Inicial
  render(generateSampleData(), 'dados de exemplo (sintéticos)');
});
