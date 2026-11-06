document.addEventListener('DOMContentLoaded', () => {
    const titleEl = document.getElementById('issue-title');
    const descEl = document.getElementById('issue-description');
    const timelineContainer = document.getElementById('timeline-container');

    // Pega a issue key da URL (?issue=REYK-123)
    const urlParams = new URLSearchParams(window.location.search);
    const issueKey = urlParams.get('issue');

    if (!issueKey) {
        titleEl.textContent = 'Nenhuma issue selecionada';
        descEl.textContent = 'Use ?issue=CHAVE na URL ou acesse o dashboard para selecionar uma issue.';
        timelineContainer.innerHTML = '<p style="text-align:center; color: var(--text-secondary);">Acesse <a href="/dashboard.html">o dashboard</a> para ver a lista de issues.</p>';
        return;
    }

    titleEl.textContent = `${issueKey} - Carregando...`;
    descEl.textContent = 'Buscando timeline...';

    // Busca timeline da API
    fetch(`/api/issues/${issueKey}/timeline`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const events = data.events;
            const metrics = data.metrics;
            renderHeader(issueKey, events);
            renderTimeline(issueKey, events, metrics);
        })
        .catch(error => {
            console.error('Error loading timeline:', error);
            titleEl.textContent = 'Erro ao carregar os dados';
            descEl.textContent = `Não foi possível carregar a timeline de ${issueKey}. Verifique se a issue existe no banco.`;
        });

    function renderHeader(key, events) {
        titleEl.textContent = `${key} - Timeline`;
        descEl.textContent = `${events.length} eventos registrados`;
    }

    function renderTimeline(key, events, metrics) {
        if (!events || events.length === 0) {
            timelineContainer.innerHTML = '<p>Nenhum histórico encontrado para esta issue.</p>';
            return;
        }

        // Blacklist já é aplicada server-side, mas filtramos localmente como fallback
        let filteredEvents = events;

        // Detecta intervalos e transições problemáticas para exibição visual
        detectIntervalsAndWarnings(key, filteredEvents, metrics);

        // Ordena por data (mais recente primeiro)
        filteredEvents.sort((a, b) => new Date(b.event_date) - new Date(a.event_date));

        if (filteredEvents.length === 0) {
            timelineContainer.innerHTML = '<p>Nenhum histórico encontrado após aplicar o filtro.</p>';
            return;
        }

        filteredEvents.forEach((event, index) => {
            const item = createTimelineItem(event, index);
            timelineContainer.appendChild(item);
        });
    }

    function detectIntervalsAndWarnings(key, events, metrics) {
        // Filtra apenas transições de status, ordena cronologicamente
        const statusChanges = events
            .filter(e => e.field === 'status')
            .sort((a, b) => new Date(a.event_date) - new Date(b.event_date));

        let intervals = [];
        let inProgressStart = null;
        let hasBeenInProgress = false;
        let skippedTransitions = [];

        statusChanges.forEach(event => {
            const date = new Date(event.event_date);
            const toStatus = event.to_value;
            const fromStatus = event.from_value;

            if (toStatus === 'In Progress') {
                inProgressStart = date;
                hasBeenInProgress = true;
            }

            if (fromStatus === 'In Progress' && inProgressStart) {
                const durationMs = date - inProgressStart;
                intervals.push({
                    phase: `Intervalo ${intervals.length + 1}`,
                    transition: `In Progress \u27F6 ${toStatus}`,
                    start: inProgressStart,
                    end: date,
                    durationMs: durationMs
                });
                inProgressStart = null;
            }

            // Detecta transições para Blocked/Done sem ter passado por In Progress
            if ((toStatus === 'Blocked' || toStatus === 'Done') && !hasBeenInProgress) {
                skippedTransitions.push({ from: fromStatus, to: toStatus, date: date });
            }
        });

        // Se ainda está In Progress (intervalo aberto)
        if (inProgressStart) {
            const now = new Date();
            const durationMs = now - inProgressStart;
            intervals.push({
                phase: `Intervalo ${intervals.length + 1}`,
                transition: `In Progress \u27F6 (Atual)`,
                start: inProgressStart,
                end: now,
                durationMs: durationMs
            });
        }

        // Usa métricas do banco (fonte única de verdade)
        const cycleTimeMs = metrics.cycle_time_ms || 0;
        const leadTimeMs = metrics.lead_time_ms || 0;

        renderMetricsTable(intervals, cycleTimeMs, leadTimeMs, skippedTransitions);
    }

    function formatDuration(ms) {
        if (ms < 0) return '0m';
        const totalMin = Math.floor(ms / 60000);
        const days = Math.floor(totalMin / (24 * 60));
        const hours = Math.floor((totalMin % (24 * 60)) / 60);
        const mins = totalMin % 60;

        let parts = [];
        if (days > 0) parts.push(`${days}d`);
        if (hours > 0) parts.push(`${hours}h`);
        if (mins > 0 || parts.length === 0) parts.push(`${mins}m`);

        return parts.join(' ');
    }

    function renderMetricsTable(intervals, cycleTimeMs, leadTimeMs, skippedTransitions) {
        const container = document.getElementById('metrics-container');
        const tbody = document.getElementById('metrics-tbody');
        const ctVal = document.getElementById('cycle-time-val');
        const ltVal = document.getElementById('lead-time-val');

        if (intervals.length === 0 && cycleTimeMs === 0 && leadTimeMs === 0 && (!skippedTransitions || skippedTransitions.length === 0)) {
            return;
        }

        container.style.display = 'block';
        tbody.innerHTML = '';

        intervals.forEach(inv => {
            const tr = document.createElement('tr');

            const startStr = inv.start.toLocaleDateString('pt-BR') + ' ' + inv.start.toLocaleTimeString('pt-BR', {hour: '2-digit', minute:'2-digit'});
            const endStr = inv.end.toLocaleDateString('pt-BR') + ' ' + inv.end.toLocaleTimeString('pt-BR', {hour: '2-digit', minute:'2-digit'});

            tr.innerHTML = `
                <td>${inv.phase}</td>
                <td>${inv.transition}</td>
                <td>${startStr}</td>
                <td>${endStr}</td>
                <td>${formatDuration(inv.durationMs)}</td>
            `;
            tbody.appendChild(tr);
        });

        if (intervals.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="5" style="text-align: center; color: var(--text-secondary);">Nenhum intervalo "In Progress" registrado.</td>`;
            tbody.appendChild(tr);
        }

        ctVal.textContent = cycleTimeMs > 0 ? formatDuration(cycleTimeMs) : '--';
        ltVal.textContent = leadTimeMs > 0 ? formatDuration(leadTimeMs) : 'N\u00E3o conclu\u00EDda';

        // Exibe nota de transição não recomendada
        if (skippedTransitions && skippedTransitions.length > 0) {
            let warningEl = document.getElementById('skipped-transition-warning');
            if (!warningEl) {
                warningEl = document.createElement('div');
                warningEl.id = 'skipped-transition-warning';
                container.appendChild(warningEl);
            }
            const transitions = skippedTransitions.map(t => `${t.from} \u2192 ${t.to}`).join(', ');
            warningEl.style.cssText = 'background: rgba(251,191,36,0.1); border: 1px solid rgba(251,191,36,0.3); border-left: 3px solid #f59e0b; border-radius: 6px; padding: 0.8rem 1rem; margin-top: 1rem;';
            warningEl.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem;">
                    <span style="font-size: 1rem;">\u26A0\uFE0F</span>
                    <strong style="color: #fbbf24; font-size: 0.85rem;">Transi\u00E7\u00E3o de status n\u00E3o recomendada</strong>
                </div>
                <p style="color: #fde68a; font-size: 0.8rem; margin: 0;">
                    Esta issue foi movida para <strong>${transitions}</strong> sem passar por "In Progress". 
                    Por esse motivo, o Cycle Time n\u00E3o foi computado nos c\u00E1lculos. 
                    O fluxo recomendado \u00E9: abrir a issue \u2192 mover para In Progress \u2192 ent\u00E3o Blocked ou Done.
                </p>
            `;
        } else {
            const warningEl = document.getElementById('skipped-transition-warning');
            if (warningEl) warningEl.remove();
        }
    }

    function createTimelineItem(event, index) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'timeline-item';
        itemDiv.style.animationDelay = `${index * 0.05}s`;

        const authorName = event.author_name || 'Usu\u00E1rio Desconhecido';
        const avatarUrl = event.author_avatar_url || `https://ui-avatars.com/api/?name=${encodeURIComponent(authorName)}&background=random`;

        const dateObj = new Date(event.event_date);
        const dateStr = dateObj.toLocaleDateString('pt-BR', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });

        const field = event.field || 'Desconhecido';
        const fromVal = event.from_value ? escapeHTML(event.from_value) : '<span class="value-box empty">Vazio</span>';
        const toVal = event.to_value ? escapeHTML(event.to_value) : '<span class="value-box empty">Vazio</span>';

        const changeHTML = `
            <div class="change-item">
                <span class="change-field">${escapeHTML(field)}</span>
                <div class="change-values">
                    ${event.from_value ? `<span class="value-box">${fromVal}</span>` : fromVal}
                    <span class="arrow">\u27F6</span>
                    ${event.to_value ? `<span class="value-box">${toVal}</span>` : toVal}
                </div>
            </div>
        `;

        itemDiv.innerHTML = `
            <div class="timeline-card">
                <div class="card-header">
                    <img src="${avatarUrl}" alt="${escapeHTML(authorName)}" class="author-avatar" onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(authorName)}'">
                    <div class="author-info">
                        <span class="author-name">${escapeHTML(authorName)}</span>
                        <span class="event-time">${dateStr}</span>
                    </div>
                </div>
                <div class="card-content">
                    <div class="changes-list">
                        ${changeHTML}
                    </div>
                </div>
            </div>
        `;

        return itemDiv;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g,
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }
});
