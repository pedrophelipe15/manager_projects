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

    function escapeHtml(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    /**
     * Gera o HTML interno de um tooltip explicativo reutilizavel (`.ct-tip`).
     * Embuta o retorno dentro de:
     *   <span class="ct-tip-wrap" tabindex="0" role="button" aria-label="...">
     *     <span>VALOR</span>
     *     {aqui}
     *   </span>
     *
     * config = {
     *   title:   string,                  // titulo (uppercase)
     *   formula: string (HTML permitido), // ex: "mantidas ÷ total × 100"
     *   calc:    string (HTML permitido), // ex: "387 ÷ 715 × 100 = <strong>54.1%</strong>"
     *   rows:    [{ label, value, tone }],// tone: good|info|warn|bad|'' ; total: true marca linha de total
     *   note:    string,                  // rodape explicativo
     *   empty:   string,                  // se presente e nao ha rows/calc, mostra so isto
     *   position:'left'|'up'|''           // modificador de posicao
     * }
     */
    function infoTooltip(config) {
        config = config || {};
        var cls = "ct-tip";
        if (config.position === "left") cls += " ct-tip--left";
        else if (config.position === "up") cls += " ct-tip--up";

        var title = config.title ? '<div class="ct-tip-title">' + escapeHtml(config.title) + "</div>" : "";

        if (config.empty && !(config.rows && config.rows.length) && !config.calc) {
            return '<div class="' + cls + '">' + title +
                '<div class="ct-tip-empty">' + escapeHtml(config.empty) + "</div></div>";
        }

        var formula = config.formula ? '<div class="ct-tip-formula">' + config.formula + "</div>" : "";
        var calc = config.calc ? '<div class="ct-tip-calc">' + config.calc + "</div>" : "";

        var rows = "";
        if (config.rows && config.rows.length) {
            rows = '<div class="ct-tip-rows">' + config.rows.map(function (r) {
                var rowCls = "ct-tip-row" + (r.total ? " total" : "");
                var toneCls = "ct-tip-dot" + (r.tone ? " " + r.tone : "");
                return '<div class="' + rowCls + '"><span class="' + toneCls + '"></span>' +
                    '<span class="ct-tip-lbl">' + escapeHtml(r.label) + "</span>" +
                    '<span class="ct-tip-val">' + escapeHtml(r.value) + "</span></div>";
            }).join("") + "</div>";
        }

        var note = config.note ? '<div class="ct-tip-note">' + escapeHtml(config.note) + "</div>" : "";
        return '<div class="' + cls + '">' + title + formula + calc + rows + note + "</div>";
    }

    global.CTUI = {
        getDensity: getDensity,
        setDensity: setDensity,
        tableToTSV: tableToTSV,
        copyTable: copyTable,
        copyText: copyText,
        token: token,
        chartPalette: chartPalette,
        infoTooltip: infoTooltip,
    };
})(window);
