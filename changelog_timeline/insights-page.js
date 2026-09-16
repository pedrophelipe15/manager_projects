// Insights Page
document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
    document.getElementById('projectFilter').addEventListener('change', onProjectChange);
});

async function loadProjects() {
    try {
        const r = await fetch('/api/settings/projects');
        const projects = await r.json();
        const select = document.getElementById('projectFilter');
        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.key;
            opt.textContent = `${p.key} - ${p.name}`;
            select.appendChild(opt);
        });
        CTContext.bindProjectSelect(select, onProjectChange);
    } catch (e) { console.error(e); }
}

async function onProjectChange() {
    const key = document.getElementById('projectFilter').value;
    const container = document.getElementById('results-container');
    const badges = document.getElementById('severityBadges');

    if (!key) {
        container.innerHTML = '<p class="empty-state">Selecione um projeto para ver os insights.</p>';
        badges.innerHTML = '';
        return;
    }

    container.innerHTML = '<p class="empty-state">Analisando...</p>';
    badges.innerHTML = '';

    try {
        const r = await fetch(`/api/insights?project_key=${key}`);
        const data = await r.json();
        renderInsights(data);
    } catch (e) {
        container.innerHTML = '<p class="empty-state">Erro ao carregar insights.</p>';
        console.error(e);
    }
}

function renderInsights(data) {
    const container = document.getElementById('results-container');
    const badges = document.getElementById('severityBadges');

    // Badges de severidade
    const counts = data.severity_counts;
    let badgeHtml = '';
    if (counts.critical > 0) badgeHtml += `<span class="badge badge-critical">${counts.critical} critico(s)</span>`;
    if (counts.warning > 0) badgeHtml += `<span class="badge badge-warning">${counts.warning} atencao</span>`;
    if (counts.info > 0) badgeHtml += `<span class="badge badge-info">${counts.info} info</span>`;
    if (counts.healthy > 0) badgeHtml += `<span class="badge badge-healthy">${counts.healthy} saudavel</span>`;
    badges.innerHTML = badgeHtml;

    if (data.total === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum insight gerado. Execute uma sincronizacao para popular os dados.</p>';
        return;
    }

    let html = '';

    // Seção de ALERTAS PROATIVOS (category = "alert") — destaque máximo
    const proactiveAlerts = data.insights.filter(i => i.category === 'alert');
    if (proactiveAlerts.length > 0) {
        html += renderAlertBanner(proactiveAlerts);
    }

    // Seção de avisos (critical/warning que NÃO são alertas proativos)
    const warnings = data.insights.filter(i => (i.severity === 'critical' || i.severity === 'warning') && i.category !== 'alert');
    if (warnings.length > 0) {
        html += renderSection('Diagnostico — Atencao', 'alertas', warnings);
    }

    // Seção de observações (info)
    const observations = data.insights.filter(i => i.severity === 'info');
    if (observations.length > 0) {
        html += renderSection('Observacoes', 'observacoes', observations);
    }

    // Seção saudável
    const healthy = data.insights.filter(i => i.severity === 'healthy');
    if (healthy.length > 0) {
        html += renderSection('Indicadores Saudaveis', 'saudavel', healthy);
    }

    container.innerHTML = html;
}

function renderSection(title, sectionClass, insights) {
    let cards = insights.map(i => renderInsightCard(i)).join('');
    return `
        <section class="insights-section ${sectionClass}">
            <h2>${title}</h2>
            <div class="insights-grid">${cards}</div>
        </section>
    `;
}

function renderAlertBanner(alerts) {
    const criticals = alerts.filter(i => i.severity === 'critical');
    const warnings = alerts.filter(i => i.severity === 'warning');

    let cards = alerts.map(i => renderInsightCard(i)).join('');

    const bannerClass = criticals.length > 0 ? 'alert-banner-critical' : 'alert-banner-warning';
    const icon = criticals.length > 0 ? '🚨' : '⚠️';
    const countText = criticals.length > 0 
        ? `${criticals.length} alerta(s) critico(s)${warnings.length > 0 ? ` + ${warnings.length} atencao` : ''}`
        : `${warnings.length} alerta(s) de atencao`;

    return `
        <section class="alert-banner ${bannerClass}">
            <div class="alert-banner-header">
                <span class="alert-banner-icon">${icon}</span>
                <h2>Alertas Proativos</h2>
                <span class="alert-banner-count">${countText}</span>
            </div>
            <p class="alert-banner-desc">Situacoes que requerem acao — detectadas automaticamente.</p>
            <div class="insights-grid">${cards}</div>
        </section>
    `;
}

function renderInsightCard(insight) {
    const severityIcon = {
        critical: '🔴',
        warning: '🟡',
        info: '🔵',
        healthy: '🟢',
    }[insight.severity] || '⚪';

    let metricHtml = '';
    if (insight.value !== undefined && insight.value !== null) {
        const valueDisplay = typeof insight.value === 'number' ? 
            (insight.value > 100 ? insight.value.toFixed(0) : insight.value.toFixed(1)) : 
            insight.value;
        metricHtml = `<div class="insight-metric"><span class="metric-value">${valueDisplay}</span>`;
        if (insight.threshold !== undefined && insight.threshold !== null) {
            metricHtml += `<span class="metric-threshold">threshold: ${insight.threshold}</span>`;
        }
        metricHtml += `</div>`;
    }

    let recommendationHtml = '';
    if (insight.recommendation) {
        recommendationHtml = `
            <div class="insight-recommendation">
                <strong>Recomendacao:</strong> ${escapeHTML(insight.recommendation)}
            </div>
        `;
    }

    return `
        <div class="insight-card glass severity-${insight.severity}">
            <div class="insight-header">
                <span class="insight-icon">${severityIcon}</span>
                <h3 class="insight-title">${escapeHTML(insight.title)}</h3>
            </div>
            <p class="insight-description">${escapeHTML(insight.description)}</p>
            ${metricHtml}
            ${recommendationHtml}
        </div>
    `;
}

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
}
