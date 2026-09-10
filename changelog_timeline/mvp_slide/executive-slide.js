/**
 * Slide Executivo (MVP) — apartado do restante do projeto.
 *
 * Consome dados AO VIVO (somente leitura) das APIs existentes:
 *   - GET /api/hierarchy/tree?key=INI  -> iniciativa + epicos + stories
 *
 * Enriquecimentos OPCIONAIS (progressive enhancement), carregados de arquivos
 * locais nesta mesma pasta. Se nao existirem, o slide funciona sem eles:
 *   - eco_classification.json  -> { "IR-5904": "sim", "NASH-6499": "nao", ... }
 *   - initiative_meta.json     -> { "GPPGI-325": { objetivo, ganhos[], indicadores[], atencao[] } }
 *
 * Nao altera nenhum dado; nao depende de codigo do projeto principal.
 */

const DONE_STATES = ["Done", "Canceled"];
const MESES_PT = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
                  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

// Faixas de concentracao (parametrizavel)
const CONC = { high: 6, mid: 3 }; // >=6 high, >=3 mid, senao low

// ---------- Helpers ----------

function getKeyFromUrl() {
    return new URLSearchParams(window.location.search).get("key");
}

function formatDateBR(iso) {
    if (!iso) return "";
    const [y, m, d] = iso.split("T")[0].split("-");
    return `${d}/${m}/${y}`;
}

function monthLabel(iso) {
    const [y, m] = iso.split("T")[0].split("-");
    return `${MESES_PT[parseInt(m, 10) - 1]}/${y.slice(2)}`;
}

function concClass(n) {
    if (n >= CONC.high) return "high";
    if (n >= CONC.mid) return "mid";
    return "low";
}

function pct(part, total) {
    return total > 0 ? Math.round((part / total) * 1000) / 10 : 0;
}

/** Carrega um JSON opcional; retorna null se nao existir/erro. */
async function loadOptional(path) {
    try {
        const res = await fetch(path, { cache: "no-store" });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

/** Extrai um nome curto/legivel do summary da story para a tag. */
function shortLabel(story) {
    // Ex.: "[TIER GOLD] [PDBNOTIFICATIONSENDER]" -> PDBNOTIFICATIONSENDER
    let summary = story.summary || "";
    // remove o prefixo/rotulo "[TIER GOLD]" em qualquer forma
    summary = summary.replace(/\[?\s*tier\s+gold\s*\]?/gi, "").trim();

    let label = "";
    const matches = summary.match(/\[([^\]]+)\]/g);
    if (matches && matches.length) {
        // pega o ultimo bloco entre colchetes restante
        const cleaned = matches.map(s => s.replace(/[\[\]]/g, "").trim()).filter(Boolean);
        label = cleaned.length ? cleaned[cleaned.length - 1] : "";
    }
    // fallback: primeiro termo significativo do summary limpo
    if (!label) label = summary.replace(/[\[\]]/g, "").trim().slice(0, 28);
    return `${story.key} ${label}`.trim();
}

// ---------- Data ----------

/** Achata a arvore em uma lista de stories. */
function flattenStories(tree) {
    const stories = [];
    const epics = tree.epics || [];
    for (const epic of epics) {
        for (const st of (epic.stories || [])) {
            stories.push(st);
        }
    }
    return stories;
}

/** Agrupa stories com due_date por mes -> dia. Ordenado cronologicamente. */
function buildSchedule(stories) {
    const withDue = stories.filter(s => s.due_date);
    const byMonth = new Map();

    for (const s of withDue) {
        const iso = s.due_date.split("T")[0];
        const monthKey = iso.slice(0, 7); // YYYY-MM
        if (!byMonth.has(monthKey)) byMonth.set(monthKey, new Map());
        const days = byMonth.get(monthKey);
        if (!days.has(iso)) days.set(iso, []);
        days.get(iso).push(s);
    }

    // ordena meses e dias
    const months = [...byMonth.keys()].sort();
    return months.map(mk => {
        const days = byMonth.get(mk);
        const dayKeys = [...days.keys()].sort();
        const total = dayKeys.reduce((acc, dk) => acc + days.get(dk).length, 0);
        return {
            monthKey: mk,
            monthLabel: monthLabel(mk + "-01"),
            total,
            days: dayKeys.map(dk => ({ date: dk, stories: days.get(dk) })),
        };
    });
}

// ---------- Render ----------

function renderHeader(ini, meta) {
    document.getElementById("title-bar").textContent = `${ini.key} · ${ini.summary}`;
    const teamsCtx = document.getElementById("exec-context");
    teamsCtx.textContent = ini.status ? ini.status.toUpperCase() : "";

    const sub = document.getElementById("exec-subtitle");
    if (meta && meta.objetivo) {
        sub.innerHTML = `<strong>Objetivo:</strong> ${meta.objetivo}`;
    } else {
        sub.textContent = "";
    }
    document.title = `Slide Executivo | ${ini.key}`;
}

function kpiCard({ value, valueClass = "", pctValue, pctClass = "", label, hero = false }) {
    const heroClass = hero ? " kpi-hero" : "";
    let valueHtml;
    if (pctValue !== undefined) {
        valueHtml = `
            <div class="kpi-line">
                <span class="kpi-value ${valueClass}">${value}</span>
                <span class="kpi-sep">|</span>
                <span class="kpi-pct ${pctClass}">${pctValue}%</span>
            </div>`;
    } else {
        valueHtml = `<div class="kpi-value ${valueClass}">${value}</div>`;
    }
    return `<div class="kpi${heroClass}">${valueHtml}<div class="kpi-label">${label}</div></div>`;
}

function renderKpis(stories, teams, eco) {
    const total = stories.length;
    const done = stories.filter(s => DONE_STATES.includes(s.status)).length;
    const todo = total - done;

    let cards = "";
    cards += kpiCard({ value: total, valueClass: "positive", label: "Total de atividades" });
    cards += kpiCard({ value: done, valueClass: "positive", pctValue: pct(done, total), pctClass: "positive", label: "Concluidas" });
    cards += kpiCard({ value: todo, valueClass: "alert", pctValue: pct(todo, total), pctClass: "alert", label: "A fazer" });
    cards += kpiCard({ value: (teams ? teams.length : 0), label: "Times envolvidos" });

    // KPI Eco (opcional) — so aparece se houver classificacao
    if (eco) {
        let sim = 0, nao = 0;
        for (const s of stories) {
            const c = eco[s.key];
            if (c === "sim") sim++;
            else if (c === "nao") nao++;
        }
        const classified = sim + nao;
        if (classified > 0) {
            cards += `
                <div class="kpi">
                    <div class="kpi-label">Ecossistema PIX/PSI</div>
                    <div class="eco-counter">
                        <div class="eco-cell sim"><span class="eco-n">${sim}</span><span class="eco-pc">${pct(sim, classified)}% sim</span></div>
                        <div class="eco-cell nao"><span class="eco-n">${nao}</span><span class="eco-pc">${pct(nao, classified)}% nao</span></div>
                    </div>
                </div>`;
        }
    }

    document.getElementById("kpi-row").innerHTML = cards;
}

function renderNarrative(meta) {
    const el = document.getElementById("narrative");
    if (!meta) { el.hidden = true; return; }

    const blocks = [];
    const listBlock = (title, items, attention = false) => {
        if (!items || !items.length) return;
        const cls = attention ? " attention" : "";
        blocks.push(`<div class="block${cls}"><h3>${title}</h3><ul>${items.map(i => `<li>${i}</li>`).join("")}</ul></div>`);
    };
    listBlock("Ganhos previstos", meta.ganhos);
    listBlock("Indicadores-alvo impactados", meta.indicadores);
    listBlock("Pontos de atencao", meta.atencao, true);

    if (!blocks.length) { el.hidden = true; return; }
    el.innerHTML = blocks.join("");
    el.hidden = false;
}

function renderSchedule(schedule, eco) {
    const body = document.getElementById("schedule-body");
    if (!schedule.length) {
        body.innerHTML = `<p class="state-msg">Nenhuma atividade com due date encontrada.</p>`;
        return;
    }

    let rows = "";
    for (const month of schedule) {
        const span = month.days.length;
        month.days.forEach((day, idx) => {
            const dayTags = day.stories.map(s => {
                let ecoCls = "";
                if (eco) {
                    if (eco[s.key] === "sim") ecoCls = " eco-sim";
                    else if (eco[s.key] === "nao") ecoCls = " eco-nao";
                }
                return `<span class="tag${ecoCls}">${shortLabel(s)}</span>`;
            }).join("");

            rows += "<tr>";
            if (idx === 0) {
                rows += `<td class="period" rowspan="${span}">${month.monthLabel}</td>`;
                rows += `<td rowspan="${span}"><span class="count-pill ${concClass(month.total)}">${month.total}</span></td>`;
            }
            rows += `<td class="day-date">${formatDateBR(day.date)}</td>`;
            rows += `<td><span class="count-pill ${concClass(day.stories.length)}">${day.stories.length}</span></td>`;
            rows += `<td><div class="activity-list">${dayTags}</div></td>`;
            rows += "</tr>";
        });
    }

    body.innerHTML = `
        <table class="schedule-table">
            <caption>Atividades com due date, agrupadas por mes e dia.</caption>
            <thead>
                <tr>
                    <th scope="col" style="width:110px">Periodo</th>
                    <th scope="col" style="width:70px">Qtde Mensal</th>
                    <th scope="col" style="width:110px">Data</th>
                    <th scope="col" style="width:70px">Qtde Diaria</th>
                    <th scope="col">Lista de atividades</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;
}

function renderFooter(tree) {
    // usa last_synced_at da iniciativa se disponivel
    const ini = tree.initiative || {};
    const synced = ini.last_synced_at ? ` · Dados de ${formatDateBR(ini.last_synced_at)}` : "";
    document.getElementById("footer-updated").textContent =
        `Slide Executivo (MVP)${synced}`;
}

// ---------- Init ----------

async function init() {
    const key = getKeyFromUrl();
    const scheduleBody = document.getElementById("schedule-body");

    if (!key) {
        scheduleBody.innerHTML = `<p class="state-msg">Informe uma iniciativa na URL: <code>?key=GPPGI-325</code></p>`;
        return;
    }

    let tree;
    try {
        const res = await fetch(`/api/hierarchy/tree?key=${encodeURIComponent(key)}`, { cache: "no-store" });
        if (!res.ok) {
            scheduleBody.innerHTML = `<p class="state-msg">Iniciativa "${key}" nao encontrada.</p>`;
            return;
        }
        tree = await res.json();
    } catch (err) {
        scheduleBody.innerHTML = `<p class="state-msg">Erro ao carregar dados: ${err.message}</p>`;
        return;
    }

    if (tree.type !== "initiative") {
        scheduleBody.innerHTML = `<p class="state-msg">A key "${key}" nao e uma iniciativa.</p>`;
        return;
    }

    // Enriquecimentos opcionais (nao bloqueiam)
    const [ecoAll, metaAll] = await Promise.all([
        loadOptional("eco_classification.json"),
        loadOptional("initiative_meta.json"),
    ]);
    const eco = ecoAll || null;
    const meta = (metaAll && metaAll[key]) ? metaAll[key] : null;

    const stories = flattenStories(tree);
    const teams = [...new Set(stories.map(s => s.project_key).filter(Boolean))];
    const schedule = buildSchedule(stories);

    renderHeader(tree.initiative, meta);
    renderKpis(stories, teams, eco);
    renderNarrative(meta);
    renderSchedule(schedule, eco);
    renderFooter(tree);
}

init();
