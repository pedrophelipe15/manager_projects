/**
 * nav.js — Casca da aplicação: menu lateral por MÓDULO + topo com breadcrumb.
 * Asset da plataforma; carregado por todas as páginas de todos os módulos.
 *
 * O menu NÃO é fixo no código: vem de GET /api/platform/modules (campo "menu"), montado pelo
 * kernel a partir dos módulos LIGADOS. Um item por módulo; as páginas do módulo ficam dentro.
 * Módulo desligado some; módulo novo aparece sozinho (basta declarar `nav` no manifest);
 * módulo com falha aparece marcado. "Plataforma" fica fixa no rodapé do menu.
 *
 * Comportamento:
 *   - monta a casca em volta do conteúdo da página (as páginas não mudam; só carregam este script);
 *   - esconde a barra de navegação antiga (#main-nav) — o menu lateral a substitui;
 *   - NÃO monta nada dentro de iframe (ex.: timeline embutida);
 *   - menu recolhível (só ícones) e, em tela <= 900px, gaveta; estado lembrado em localStorage;
 *   - o último menu recebido fica em sessionStorage só para não "piscar" entre páginas.
 */
(function () {
    "use strict";
    if (window.self !== window.top) return;           // iframe: sem casca

    var CACHE_KEY = "platform.shell.v1";
    var RAIL_KEY = "platform.rail";
    var OPEN_KEY = "platform.open";
    var ICONS = {
        chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
        tree: '<circle cx="12" cy="5" r="2.2"/><circle cx="5.5" cy="19" r="2.2"/><circle cx="18.5" cy="19" r="2.2"/><path d="M12 7.2v4.3M12 11.5H5.5v5.3M12 11.5h6.5v5.3"/>',
        shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
        grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
        alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.01"/>',
        chev: '<path d="M9 6l6 6-6 6"/>',
        rail: '<path d="M15 6l-6 6 6 6M20 5v14"/>',
        menu: '<path d="M4 7h16M4 12h16M4 17h16"/>'
    };

    function svg(name, size) {
        size = size || 18;
        return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || ICONS.grid) + "</svg>";
    }
    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined && text !== null) n.textContent = text;   // textContent: sem injeção de HTML
        return n;
    }
    function normalize(path) {
        try { return decodeURIComponent(path || "").split("?")[0]; } catch (e) { return (path || "").split("?")[0]; }
    }
    var store = {
        get: function (k, d) { try { var v = window.localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
        set: function (k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sem storage: segue */ } },
        sget: function (k) { try { var v = window.sessionStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } },
        sset: function (k, v) { try { window.sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* idem */ } }
    };

    var open = {};                 // módulos expandidos (id -> true)
    (store.get(OPEN_KEY, []) || []).forEach(function (id) { open[id] = true; });
    var currentMenu = [];
    var platformHome = "";         // URL do painel de módulos (vem da API, entrada "platform")
    var ui = {};                   // referências aos elementos da casca

    /* ------------------------------------------------------------ localizar a página atual no menu */
    function locate(menu) {
        var here = normalize(window.location.pathname);
        var i, g, l, m, loose = null;
        for (i = 0; i < menu.length; i++) {
            m = menu[i];
            for (g = 0; g < m.groups.length; g++) {
                for (l = 0; l < m.groups[g].links.length; l++) {
                    var link = m.groups[g].links[l];
                    if (normalize(link.href) === here) return { mod: m, group: m.groups[g].group, link: link, exact: true };
                }
            }
        }
        // página que não está no menu (ex.: detalhe de épico): atribui ao módulo da mesma pasta
        var dir = here.split("/").slice(0, -1).join("/");
        if (dir) {
            for (i = 0; i < menu.length && !loose; i++) {
                for (g = 0; g < menu[i].groups.length && !loose; g++) {
                    for (l = 0; l < menu[i].groups[g].links.length; l++) {
                        if (normalize(menu[i].groups[g].links[l].href).split("/").slice(0, -1).join("/") === dir) {
                            loose = { mod: menu[i], group: "", link: null, exact: false };
                            break;
                        }
                    }
                }
            }
        }
        return loose;
    }

    /* ------------------------------------------------------------ montar a casca (uma vez) */
    function mount() {
        var oldNav = document.getElementById("main-nav") || document.getElementById("hierarchy-nav");
        if (oldNav) oldNav.parentNode.removeChild(oldNav);     // o menu lateral substitui a barra antiga

        var shell = el("div", "shell");
        var sidebar = el("aside", "shell-sidebar");
        sidebar.id = "shell-sidebar";
        sidebar.setAttribute("aria-label", "Navegação principal");

        var brand = el("div", "shell-brand");
        brand.appendChild(el("div", "shell-logo", "CT"));
        var bn = el("div", "shell-brand-name", "Changelog Timeline");
        bn.appendChild(el("small", null, "gestão de fluxo"));
        brand.appendChild(bn);
        sidebar.appendChild(brand);

        ui.nav = el("nav");
        ui.nav.setAttribute("aria-label", "Módulos");
        var scroll = el("div", "shell-scroll");
        scroll.appendChild(ui.nav);
        ui.bottom = el("nav", "shell-bottom");
        ui.bottom.setAttribute("aria-label", "Plataforma");
        sidebar.appendChild(scroll);
        sidebar.appendChild(ui.bottom);

        var main = el("div", "shell-main");
        var top = el("header", "shell-topbar");
        var menuBtn = el("button", "shell-iconbtn");
        menuBtn.id = "shell-menu-btn"; menuBtn.type = "button";
        menuBtn.setAttribute("aria-label", "Abrir menu"); menuBtn.setAttribute("aria-controls", "shell-sidebar");
        menuBtn.innerHTML = svg("menu");
        var railBtn = el("button", "shell-iconbtn");
        railBtn.id = "shell-rail-btn"; railBtn.type = "button";
        railBtn.setAttribute("aria-label", "Recolher ou expandir o menu"); railBtn.title = "Recolher / expandir o menu";
        railBtn.innerHTML = svg("rail");
        ui.crumbs = el("div", "shell-crumbs");
        ui.crumbs.setAttribute("aria-label", "Você está em");
        top.appendChild(menuBtn); top.appendChild(railBtn); top.appendChild(ui.crumbs);

        var content = el("main", "shell-content");
        content.id = "shell-content";
        content.setAttribute("tabindex", "-1");
        // move o conteúdo existente da página (menos scripts/estilos) para dentro da casca
        var nodes = Array.prototype.slice.call(document.body.childNodes);
        nodes.forEach(function (n) {
            if (n.nodeType === 1 && /^(SCRIPT|LINK|STYLE)$/.test(n.tagName)) return;
            content.appendChild(n);
        });
        main.appendChild(top); main.appendChild(content);
        shell.appendChild(sidebar); shell.appendChild(main);

        var skip = el("a", "shell-skip", "Pular para o conteúdo");
        skip.setAttribute("href", "#shell-content");
        var overlay = el("div", "shell-overlay");
        overlay.addEventListener("click", closeDrawer);

        document.body.insertBefore(overlay, document.body.firstChild);
        document.body.insertBefore(shell, document.body.firstChild);
        document.body.insertBefore(skip, document.body.firstChild);
        document.body.classList.add("has-shell");
        if (store.get(RAIL_KEY, false)) document.body.classList.add("shell-rail");

        menuBtn.addEventListener("click", function () { document.body.classList.add("shell-drawer"); });
        railBtn.addEventListener("click", function () {
            var on = !document.body.classList.contains("shell-rail");
            document.body.classList.toggle("shell-rail", on);
            store.set(RAIL_KEY, on);
        });
        document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
    }
    function closeDrawer() { document.body.classList.remove("shell-drawer"); }

    /* ------------------------------------------------------------ render */
    function flatRule(group) {   // grupo com 1 link do mesmo nome do grupo => link solto, sem subtítulo
        return group.links.length === 1 && group.links[0].label === group.group ? "" : group.group;
    }

    function renderModule(m, loc) {
        var wrap = el("div", "shell-mod");
        var active = loc && loc.mod.id === m.id;
        if (active) wrap.classList.add("has-active");
        if (m.state === "failed") wrap.classList.add("is-failed");
        if (open[m.id]) wrap.classList.add("is-open");

        var head = el("button", "shell-mod-head");
        head.type = "button"; head.title = m.name;
        head.setAttribute("aria-expanded", String(!!open[m.id]));
        var ico = el("span", "shell-mod-ico"); ico.innerHTML = svg(m.icon);
        head.appendChild(ico);
        head.appendChild(el("span", "shell-mod-name", m.name));
        var chev = el("span", "shell-chev"); chev.innerHTML = svg("chev", 16);
        head.appendChild(chev);
        head.addEventListener("click", function () {
            if (document.body.classList.contains("shell-rail") && window.matchMedia("(min-width: 901px)").matches) {
                document.body.classList.remove("shell-rail"); store.set(RAIL_KEY, false);   // no modo recolhido, clicar abre o menu
            }
            if (open[m.id]) delete open[m.id]; else open[m.id] = true;
            store.set(OPEN_KEY, Object.keys(open));
            render(currentMenu);
        });
        wrap.appendChild(head);

        var body = el("div", "shell-mod-body");
        if (m.state === "failed") {
            var f = el("div", "shell-fail", "Módulo com falha. Veja ");
            var a = el("a", null, "Plataforma › Módulos"); a.setAttribute("href", platformHome || "#");   // home da Plataforma vem da API
            f.appendChild(a);
            body.appendChild(f);
        } else {
            m.groups.forEach(function (g) {
                var label = flatRule(g);
                if (label) body.appendChild(el("div", "shell-grp", label));
                g.links.forEach(function (link) {
                    var lk = el("a", "shell-link", link.label);
                    lk.setAttribute("href", link.href);
                    if (loc && loc.exact && loc.link === link) lk.setAttribute("aria-current", "page");
                    body.appendChild(lk);
                });
            });
        }
        wrap.appendChild(body);
        return wrap;
    }

    function renderCrumbs(loc) {
        ui.crumbs.textContent = "";
        var parts = [];
        if (loc) {
            parts.push(loc.mod.name);
            if (loc.link) {
                var grpLinks = loc.mod.groups.filter(function (g) { return g.group === loc.group; })[0];
                if (loc.group && loc.group !== loc.link.label && grpLinks && grpLinks.links.length > 1) parts.push(loc.group);
                parts.push(loc.link.label);
            } else {
                parts.push((document.title || "").split(" - ")[0]);   // página de detalhe fora do menu
            }
        } else {
            parts.push((document.title || "").split(" - ")[0]);
        }
        parts.forEach(function (p, i) {
            if (i) ui.crumbs.appendChild(el("span", "shell-sep", "›"));
            ui.crumbs.appendChild(i === parts.length - 1 ? el("b", null, p) : el("span", null, p));
        });
    }

    var firstRender = true;
    function render(menu) {
        currentMenu = menu;
        menu.forEach(function (m) { if (m.id === "platform") platformHome = m.home || ""; });
        var loc = locate(menu);
        if (loc && firstRender) { open[loc.mod.id] = true; store.set(OPEN_KEY, Object.keys(open)); }   // ao navegar, expande o módulo atual
        firstRender = false;

        ui.nav.textContent = "";
        ui.bottom.textContent = "";
        ui.nav.appendChild(el("div", "shell-label", "Módulos"));
        menu.forEach(function (m) {
            (m.pinned ? ui.bottom : ui.nav).appendChild(renderModule(m, loc));
        });
        renderCrumbs(loc);
    }

    /* ------------------------------------------------------------ iniciar */
    function start() {
        mount();
        var cached = store.sget(CACHE_KEY);
        if (Array.isArray(cached)) render(cached);       // pinta já; a API atualiza em seguida
        fetch("/api/platform/modules", { cache: "no-store" })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
            .then(function (data) {
                var menu = Array.isArray(data.menu) ? data.menu : [];
                store.sset(CACHE_KEY, menu);
                render(menu);
            })
            .catch(function () {
                if (!Array.isArray(cached)) {
                    ui.nav.textContent = "";
                    ui.nav.appendChild(el("div", "shell-fail", "Menu indisponível: não foi possível ler /api/platform/modules."));
                    renderCrumbs(null);
                }
            });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
})();
