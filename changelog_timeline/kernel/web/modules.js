/**
 * modules.js — Painel de módulos (somente leitura).
 * Fonte: GET /api/platform/modules. Ligar/desligar é por config/modules.yaml + reinício
 * (decisão D1/A); esta tela só mostra estado, saúde e a causa de falhas de carga.
 * Todo texto vindo da API entra via textContent (nada é interpretado como HTML).
 */
(function () {
    "use strict";

    var STATE = {
        enabled: { label: "Ligado", cls: "badge-ok" },
        disabled: { label: "Desligado", cls: "badge-off" },
        failed: { label: "Falhou", cls: "badge-fail" },
    };

    function el(tag, className, text) {
        var n = document.createElement(tag);
        if (className) n.className = className;
        if (text !== undefined && text !== null) n.textContent = text;
        return n;
    }

    function cell(children) {
        var td = document.createElement("td");
        (Array.isArray(children) ? children : [children]).forEach(function (c) {
            if (c) td.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
        });
        return td;
    }

    function healthCell(m) {
        if (m.state !== "enabled") return cell(el("span", "muted", "—"));
        if (!m.health) return cell(el("span", "muted", "sem verificação"));
        var ok = m.health.ok;
        return cell([
            el("span", "badge " + (ok ? "badge-ok" : "badge-warn"), ok ? "OK" : "Atenção"),
            el("span", "health-detail", " " + (m.health.detail || "")),
        ]);
    }

    function row(m) {
        var tr = document.createElement("tr");

        var name = [el("strong", null, m.name || m.id), el("div", "muted mono", m.id)];
        if (m.state === "failed" && m.error) {
            name.push(el("div", "module-error", m.error));
        }
        tr.appendChild(cell(name));

        var st = STATE[m.state] || { label: m.state, cls: "badge-off" };
        tr.appendChild(cell(el("span", "badge " + st.cls, st.label)));
        tr.appendChild(cell(m.version || "—"));
        tr.appendChild(cell((m.requires && m.requires.length) ? m.requires.join(", ") : "—"));
        tr.appendChild(healthCell(m));

        var entry;
        if (m.state === "enabled" && m.home) {
            entry = el("a", "nav-link", m.home);
            entry.setAttribute("href", m.home);
        } else {
            entry = el("span", "muted", "—");
        }
        tr.appendChild(cell(entry));
        return tr;
    }

    function render(modules) {
        var body = document.getElementById("modules-body");
        body.textContent = "";
        if (!modules.length) {
            var tr = document.createElement("tr");
            var td = el("td", "empty-state", "Nenhum módulo configurado.");
            td.setAttribute("colspan", "6");
            tr.appendChild(td);
            body.appendChild(tr);
        }
        modules.forEach(function (m) { body.appendChild(row(m)); });

        var count = function (s) { return modules.filter(function (m) { return m.state === s; }).length; };
        var summary = document.getElementById("summary");
        summary.textContent = "";
        [["enabled", "ligado(s)"], ["disabled", "desligado(s)"], ["failed", "com falha"]].forEach(function (p) {
            var n = count(p[0]);
            var chip = el("span", "badge " + STATE[p[0]].cls, n + " " + p[1]);
            summary.appendChild(chip);
        });
    }

    function load() {
        fetch("/api/platform/modules", { cache: "no-store" })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
            .then(function (data) { render(data.modules || []); })
            .catch(function (e) {
                var body = document.getElementById("modules-body");
                body.textContent = "";
                var tr = document.createElement("tr");
                var td = el("td", "empty-state", "Não foi possível carregar os módulos (" + e.message + ").");
                td.setAttribute("colspan", "6");
                tr.appendChild(td);
                body.appendChild(tr);
            });
    }

    document.getElementById("btn-refresh").addEventListener("click", load);
    load();
})();
