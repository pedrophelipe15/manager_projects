/**
 * nav.js — Navegacao compartilhada (Onda 2 UX).
 *
 * Fonte UNICA da barra de navegacao. Substitui as 10 navs duplicadas.
 * Injeta a nav dentro de <nav id="main-nav" class="nav-bar"></nav>.
 *
 * Organizada por PERGUNTA que o gestor faz, nao por area tecnica:
 *   Minha Visao  -> o que preciso fazer hoje?
 *   Prazos       -> vamos entregar? (Compromisso, Previsibilidade)
 *   Pessoas      -> quem precisa de ajuda? (Maturidade, Pessoas)
 *   Fluxo        -> onde trava? (Gargalo, Portfolio)
 *   Hierarquia   -> como esta a iniciativa?
 *   Dados        -> da pra confiar? (Inconsistencias, Config)
 *
 * A aba ativa e detectada pelo pathname atual.
 */
(function () {
    "use strict";

    // Grupos e suas abas, na ordem de leitura do gestor.
    var GROUPS = [
        {
            label: "Minha Visao",
            links: [
                { href: "/minha-visao.html", label: "Minha Visao" },
            ],
        },
        {
            label: "Prazos",
            links: [
                { href: "/compromisso.html", label: "Compromisso" },
                { href: "/wave2.html", label: "Previsibilidade" },
            ],
        },
        {
            label: "Pessoas",
            links: [
                { href: "/maturidade.html", label: "Maturidade" },
                { href: "/wave3.html", label: "Pessoas" },
            ],
        },
        {
            label: "Fluxo",
            links: [
                { href: "/wave1.html", label: "Gargalo e Fluxo" },
                { href: "/wave4.html", label: "Portfolio" },
                { href: "/dashboard.html", label: "Dashboard" },
            ],
        },
        {
            label: "Hierarquia",
            links: [
                { href: "/hierarchy/dashboard-v2.html", label: "Hierarquia" },
            ],
        },
        {
            label: "Dados",
            links: [
                { href: "/inconsistencies.html", label: "Inconsistencias" },
                { href: "/settings.html", label: "Configuracoes" },
            ],
        },
    ];

    function normalize(path) {
        // '/', '/index.html' e afins normalizam para o proprio pathname.
        try {
            return decodeURIComponent(path || "").split("?")[0];
        } catch (e) {
            return (path || "").split("?")[0];
        }
    }

    function render() {
        var nav = document.getElementById("main-nav");
        if (!nav) return;

        var current = normalize(window.location.pathname);
        var html = "";

        GROUPS.forEach(function (group, gi) {
            if (gi > 0) {
                html += '<span class="nav-sep" aria-hidden="true"></span>';
            }
            html += '<span class="nav-group">';
            html += '<span class="nav-group-label">' + group.label + "</span>";
            html += '<span class="nav-group-links">';
            group.links.forEach(function (link) {
                var active = current === normalize(link.href) ? " active" : "";
                html += '<a href="' + link.href + '" class="nav-link' + active + '">' + link.label + "</a>";
            });
            html += "</span></span>";
        });

        nav.innerHTML = html;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", render);
    } else {
        render();
    }
})();
