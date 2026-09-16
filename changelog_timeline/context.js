/**
 * context.js — Contexto compartilhado entre paginas (Onda 1 UX).
 *
 * Persiste a selecao de projeto em localStorage para que o gestor nao precise
 * reselecionar o projeto a cada troca de aba. Fonte unica de verdade.
 *
 * Uso tipico numa pagina, DEPOIS de popular o <select> de projeto:
 *
 *   CTContext.bindProjectSelect(selectEl, onProjectChange);
 *
 * Isso: (1) restaura o projeto salvo se ainda existir nas opcoes; (2) senao,
 * cai no auto-select quando ha 1 unica opcao valida; (3) registra o onchange
 * para persistir toda nova selecao; (4) dispara onProjectChange se restaurou
 * ou auto-selecionou.
 */
(function (global) {
    "use strict";

    var KEY = "ct.selectedProject";

    function getProject() {
        try {
            return global.localStorage.getItem(KEY) || "";
        } catch (e) {
            return "";
        }
    }

    function setProject(value) {
        try {
            if (value) {
                global.localStorage.setItem(KEY, value);
            } else {
                global.localStorage.removeItem(KEY);
            }
        } catch (e) {
            /* localStorage indisponivel (modo privado) — degrada sem quebrar */
        }
    }

    function optionValues(selectEl) {
        return Array.prototype.map.call(selectEl.options, function (o) {
            return o.value;
        }).filter(function (v) {
            return v !== "";
        });
    }

    /**
     * Liga um <select> de projeto ao contexto compartilhado.
     * @param {HTMLSelectElement} selectEl - o select ja populado com opcoes.
     * @param {Function} onChange - callback disparado ao restaurar/selecionar.
     * @returns {string} o valor efetivamente aplicado (ou "").
     */
    function bindProjectSelect(selectEl, onChange) {
        if (!selectEl) return "";

        // Persiste toda mudanca feita pelo usuario.
        selectEl.addEventListener("change", function () {
            setProject(selectEl.value);
        });

        var values = optionValues(selectEl);
        var saved = getProject();
        var applied = "";

        if (saved && values.indexOf(saved) !== -1) {
            selectEl.value = saved;
            applied = saved;
        } else if (values.length === 1) {
            selectEl.value = values[0];
            applied = values[0];
            setProject(applied);
        }

        if (applied && typeof onChange === "function") {
            onChange(applied);
        }
        return applied;
    }

    global.CTContext = {
        getProject: getProject,
        setProject: setProject,
        bindProjectSelect: bindProjectSelect,
    };
})(window);
