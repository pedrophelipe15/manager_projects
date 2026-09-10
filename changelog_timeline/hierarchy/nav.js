/**
 * Hierarchy Module — Navegação interna compartilhada.
 * Injeta a nav bar do módulo hierárquico em todas as páginas do módulo.
 */
(function () {
    const pages = [
        { href: "/hierarchy/dashboard-v2.html", label: "Dashboard" },
        { href: "/hierarchy/roadmap.html", label: "Roadmap" },
        { href: "/hierarchy/timeline.html", label: "Timeline" },
        { href: "/hierarchy/settings.html", label: "Configuracoes" },
    ];

    const currentPath = window.location.pathname;

    function render() {
        const nav = document.getElementById("hierarchy-nav");
        if (!nav) return;

        let html = `<a href="/dashboard.html" class="nav-link nav-back" title="Voltar ao projeto principal">&larr; VOLTAR</a>`;
        html += `<span class="nav-separator"></span>`;

        for (const p of pages) {
            const active = currentPath === p.href ? " active" : "";
            html += `<a href="${p.href}" class="nav-link${active}">${p.label}</a>`;
        }

        nav.innerHTML = html;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", render);
    } else {
        render();
    }
})();
