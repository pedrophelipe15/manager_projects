/**
 * nav.js — Menu principal da plataforma (asset da plataforma, usado por todos os módulos).
 *
 * O menu NÃO é mais fixo no código: vem de GET /api/platform/modules (campo "menu"),
 * montado pelo kernel a partir dos módulos LIGADOS. Módulo desligado = sem itens no menu;
 * módulo novo aparece sozinho (basta declarar `nav` no manifest).
 *
 * Injeta a nav dentro de <nav id="main-nav" class="nav-bar"></nav>.
 * A aba ativa é detectada pelo pathname atual.
 * O último menu recebido fica em sessionStorage só para evitar "piscar" entre páginas.
 */
(function () {
    "use strict";

    var CACHE_KEY = "platform.menu.v1";

    function normalize(path) {
        try {
            return decodeURIComponent(path || "").split("?")[0];
        } catch (e) {
            return (path || "").split("?")[0];
        }
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;  // textContent: sem injeção de HTML
        return node;
    }

    function render(menu) {
        var nav = document.getElementById("main-nav");
        if (!nav || !Array.isArray(menu)) return;

        var current = normalize(window.location.pathname);
        nav.textContent = "";

        menu.forEach(function (group, gi) {
            if (gi > 0) {
                var sep = el("span", "nav-sep");
                sep.setAttribute("aria-hidden", "true");
                nav.appendChild(sep);
            }
            var g = el("span", "nav-group");
            g.appendChild(el("span", "nav-group-label", group.group));
            var links = el("span", "nav-group-links");
            (group.links || []).forEach(function (link) {
                var active = current === normalize(link.href) ? " active" : "";
                var a = el("a", "nav-link" + active, link.label);
                a.setAttribute("href", link.href);
                links.appendChild(a);
            });
            g.appendChild(links);
            nav.appendChild(g);
        });
    }

    function readCache() {
        try {
            var raw = window.sessionStorage.getItem(CACHE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function writeCache(menu) {
        try {
            window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(menu));
        } catch (e) { /* storage indisponível: segue sem cache */ }
    }

    function load() {
        var cached = readCache();
        if (cached) render(cached);  // pinta já; a resposta da API atualiza em seguida

        fetch("/api/platform/modules", { cache: "no-store" })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
            .then(function (data) {
                writeCache(data.menu || []);
                render(data.menu || []);
            })
            .catch(function () { /* sem API: mantém o menu em cache, se houver */ });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", load);
    } else {
        load();
    }
})();
