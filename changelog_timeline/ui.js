/**
 * ui.js — Utilitarios de UI compartilhados (Onda 4 UX).
 *
 * 1) Densidade (compacto / confortavel): aplica data-density no <html>,
 *    persiste em localStorage e injeta um toggle no header da pagina.
 * 2) Copiar tabela: exporta qualquer <table> para o clipboard em TSV
 *    (colavel direto em Excel/Sheets).
 *
 * Nao depende de nenhuma biblioteca. Carregar em qualquer pagina.
 */
(function (global) {
    "use strict";

    var LS_DENSITY = "ct.density";
    var DEFAULT = "comfortable"; // 'comfortable' | 'compact'

    function getDensity() {
        try { return global.localStorage.getItem(LS_DENSITY) || DEFAULT; }
        catch (e) { return DEFAULT; }
    }
    function setDensity(v) {
        document.documentElement.setAttribute("data-density", v);
        try { global.localStorage.setItem(LS_DENSITY, v); } catch (e) { /* ignore */ }
        var btn = document.getElementById("density-toggle");
        if (btn) updateToggleLabel(btn, v);
    }
    function updateToggleLabel(btn, v) {
        var compact = v === "compact";
        btn.textContent = compact ? "Densidade: compacta" : "Densidade: confortavel";
        btn.setAttribute("aria-pressed", compact ? "true" : "false");
    }

    /** Injeta o botao de densidade dentro do .page-header (ou onde indicado). */
    function mountDensityToggle() {
        var header = document.querySelector(".page-header");
        if (!header || document.getElementById("density-toggle")) return;
        var btn = document.createElement("button");
        btn.id = "density-toggle";
        btn.className = "btn btn--ghost btn--sm density-toggle";
        btn.type = "button";
        updateToggleLabel(btn, getDensity());
        btn.addEventListener("click", function () {
            setDensity(getDensity() === "compact" ? "comfortable" : "compact");
        });
        header.appendChild(btn);
    }

    /** Converte um <table> em TSV. Usa data-copy quando presente na celula. */
    function tableToTSV(table) {
        var lines = [];
        table.querySelectorAll("tr").forEach(function (tr) {
            var cells = tr.querySelectorAll("th, td");
            if (!cells.length) return;
            var row = Array.prototype.map.call(cells, function (c) {
                var txt = c.getAttribute("data-copy");
                if (txt === null) txt = (c.innerText || c.textContent || "").trim();
                return txt.replace(/\t/g, " ").replace(/\r?\n/g, " ");
            });
            lines.push(row.join("\t"));
        });
        return lines.join("\n");
    }

    function copyText(text) {
        if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) {
            return global.navigator.clipboard.writeText(text);
        }
        // Fallback
        return new Promise(function (resolve, reject) {
            try {
                var ta = document.createElement("textarea");
                ta.value = text;
                ta.style.position = "fixed";
                ta.style.opacity = "0";
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                resolve();
            } catch (e) { reject(e); }
        });
    }

    /**
     * Copia a primeira <table> encontrada dentro de `selector` e da feedback
     * visual no botao `btn`.
     */
    function copyTable(selectorOrEl, btn) {
        var container = typeof selectorOrEl === "string"
            ? document.querySelector(selectorOrEl) : selectorOrEl;
        var table = container ? container.querySelector("table") : null;
        if (!table) return;
        copyText(tableToTSV(table)).then(function () {
            if (!btn) return;
            var original = btn.textContent;
            btn.textContent = "Copiado!";
            btn.classList.add("copied");
            setTimeout(function () {
                btn.textContent = original;
                btn.classList.remove("copied");
            }, 1500);
        });
    }

    function init() {
        setDensity(getDensity());
        mountDensityToggle();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    /**
     * Le o valor de um token CSS (ex: "--chart-1") do :root. Chart.js precisa de
     * string de cor; isto mantem os graficos alinhados ao tokens.css sem hex solto.
     * Aceita nome com ou sem os hifens iniciais. Retorna fallback se vazio.
     */
    function token(name, fallback) {
        var varName = name.indexOf("--") === 0 ? name : "--" + name;
        try {
            var v = getComputedStyle(document.documentElement)
                .getPropertyValue(varName).trim();
            return v || fallback || "#888";
        } catch (e) {
            return fallback || "#888";
        }
    }

    /** Paleta categorica de grafico (--chart-1..6) como array de strings. */
    function chartPalette() {
        return [
            token("--chart-1"), token("--chart-2"), token("--chart-3"),
            token("--chart-4"), token("--chart-5"), token("--chart-6"),
        ];
    }

    global.CTUI = {
        getDensity: getDensity,
        setDensity: setDensity,
        tableToTSV: tableToTSV,
        copyTable: copyTable,
        copyText: copyText,
        token: token,
        chartPalette: chartPalette,
    };
})(window);
