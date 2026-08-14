document.addEventListener('DOMContentLoaded', () => {
    const titleEl = document.getElementById('issue-title');
    const descEl = document.getElementById('issue-description');
    const timelineContainer = document.getElementById('timeline-container');

    // Fetch the changelog JSON
    fetch('../example_largest_changelog.json')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            renderHeader(data);
            renderTimeline(data);
        })
        .catch(error => {
            console.error('Error loading changelog:', error);
            titleEl.textContent = 'Erro ao carregar os dados';
            descEl.textContent = 'Verifique se o arquivo JSON está acessível.';
        });

    function renderHeader(data) {
        const urlParams = new URLSearchParams(window.location.search);
        const issueKey = urlParams.get('issue');
        
        if (issueKey) {
            titleEl.textContent = issueKey + ' (Timeline Mockada)';
            descEl.textContent = 'Nota: Exibindo eventos estáticos de exemplo. Quando integrarmos o Python, os eventos reais desta chave serão carregados do banco de dados.';
        } else if (data.meta) {
            titleEl.textContent = data.meta.key || 'Changelog';
            descEl.textContent = data.meta.description || 'Histórico de alterações';
        }
    }

    function renderTimeline(data) {
        if (!data.issues || data.issues.length === 0 || !data.issues[0].changelog) {
            timelineContainer.innerHTML = '<p>Nenhum histórico encontrado.</p>';
            return;
        }

        let histories = data.issues[0].changelog.histories;
        
        // Blacklist de autores para ignorar eventos gerados por plugins ou bots específicos
        const BLACKLISTED_AUTHORS = [
            'Checklists for Jira (Pro) by HeroCoders'
        ];

        // Blacklist de campos para ignorar alterações irrelevantes
        const BLACKLISTED_FIELDS = [
            'Attachment',
            'labels',
            'IssueParentAssociation'
        ];

        // Filtra o histórico removendo autores da blacklist e campos ignorados
        histories = histories.filter(history => {
            const authorName = history.author ? history.author.displayName : '';
            if (BLACKLISTED_AUTHORS.includes(authorName)) {
                return false;
            }

            if (history.items) {
                history.items = history.items.filter(item => !BLACKLISTED_FIELDS.includes(item.field));
                // Se após remover os campos ignorados não sobrar nada, descarta o evento inteiro
                if (history.items.length === 0) {
                    return false;
                }
            }

            return true;
        });

        // Sort histories by date (newest first)
        histories.sort((a, b) => new Date(b.created) - new Date(a.created));

        if (histories.length === 0) {
            timelineContainer.innerHTML = '<p>Nenhum histórico encontrado após aplicar o filtro.</p>';
            return;
        }

        // Calcula métricas antes de ordenar para exibição da timeline
        calculateMetrics(data, histories);

        // Sort histories by date (newest first)
        histories.sort((a, b) => new Date(b.created) - new Date(a.created));

        histories.forEach((history, index) => {
            const item = createTimelineItem(history, index);
            timelineContainer.appendChild(item);
        });
    }

    function calculateMetrics(data, validHistories) {
        const fields = data.issues[0].fields;
        const issueCreatedDate = fields && fields.created ? new Date(fields.created) : null;
        
        // Clone and sort oldest first for state machine
        const chronological = [...validHistories].sort((a, b) => new Date(a.created) - new Date(b.created));

        let cycleTimeTotalMs = 0;
        let inProgressStart = null;
        let intervals = [];
        let doneDate = null;

        chronological.forEach(history => {
            if (!history.items) return;
            const statusChange = history.items.find(item => item.field === 'status');
            
            if (statusChange) {
                const date = new Date(history.created);
                const toStatus = statusChange.toString;

                // Rule 1 & 3: transition to In Progress
                if (toStatus === 'In Progress') {
                    inProgressStart = date;
                }
                
                // Rule 2 & 4: transition from In Progress to Blocked or Done
                if ((toStatus === 'Blocked' || toStatus === 'Done') && inProgressStart) {
                    const durationMs = date - inProgressStart;
                    cycleTimeTotalMs += durationMs;
                    intervals.push({
                        phase: `Intervalo ${intervals.length + 1}`,
                        transition: `In Progress ➔ ${toStatus}`,
                        start: inProgressStart,
                        end: date,
                        durationMs: durationMs
                    });
                    inProgressStart = null; // stop the clock
                }

                if (toStatus === 'Done') {
                    doneDate = date;
                }
            }
        });

        // Caso a issue ainda esteja "In Progress" no momento da extração
        if (inProgressStart && !doneDate) {
            // Assume the timestamp of the last history event as 'now' for the export, or just don't calculate.
            // Para maior precisão em arquivos exportados, usaremos a data atual se não estiver fechada.
            const now = new Date();
            const durationMs = now - inProgressStart;
            cycleTimeTotalMs += durationMs;
            intervals.push({
                phase: `Intervalo ${intervals.length + 1}`,
                transition: `In Progress ➔ (Atual)`,
                start: inProgressStart,
                end: now,
                durationMs: durationMs
            });
        }

        renderMetricsTable(intervals, cycleTimeTotalMs, issueCreatedDate, doneDate);
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

    function renderMetricsTable(intervals, cycleTimeTotalMs, createdDate, doneDate) {
        const container = document.getElementById('metrics-container');
        const tbody = document.getElementById('metrics-tbody');
        const ctVal = document.getElementById('cycle-time-val');
        const ltVal = document.getElementById('lead-time-val');

        if (intervals.length === 0 && !doneDate) {
            return; // Nada para mostrar
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

        ctVal.textContent = formatDuration(cycleTimeTotalMs);

        if (createdDate && doneDate) {
            const leadTimeMs = doneDate - createdDate;
            ltVal.textContent = formatDuration(leadTimeMs);
        } else {
            ltVal.textContent = 'Não concluída';
        }
    }

    function createTimelineItem(history, index) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'timeline-item';
        // Add staggered animation delay
        itemDiv.style.animationDelay = `${index * 0.1}s`;

        const author = history.author;
        const authorName = author ? author.displayName : 'Usuário Desconhecido';
        const avatarUrl = author && author.avatarUrls ? author.avatarUrls['48x48'] : 'https://ui-avatars.com/api/?name=' + encodeURIComponent(authorName) + '&background=random';
        
        const dateObj = new Date(history.created);
        const dateStr = dateObj.toLocaleDateString('pt-BR', { 
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });

        let changesHTML = '';
        if (history.items && history.items.length > 0) {
            changesHTML = `<div class="changes-list">
                ${history.items.map(change => createChangeHTML(change)).join('')}
            </div>`;
        }

        itemDiv.innerHTML = `
            <div class="timeline-card">
                <div class="card-header">
                    <img src="${avatarUrl}" alt="${authorName}" class="author-avatar" onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(authorName)}'">
                    <div class="author-info">
                        <span class="author-name">${authorName}</span>
                        <span class="event-time">${dateStr}</span>
                    </div>
                </div>
                <div class="card-content">
                    ${changesHTML}
                </div>
            </div>
        `;

        return itemDiv;
    }

    function createChangeHTML(change) {
        const field = change.field || 'Desconhecido';
        const fromVal = change.fromString ? escapeHTML(change.fromString) : '<span class="value-box empty">Vazio</span>';
        const toVal = change.toString ? escapeHTML(change.toString) : '<span class="value-box empty">Vazio</span>';

        return `
            <div class="change-item">
                <span class="change-field">${field}</span>
                <div class="change-values">
                    ${change.fromString ? `<span class="value-box">${fromVal}</span>` : fromVal}
                    <span class="arrow">➔</span>
                    ${change.toString ? `<span class="value-box">${toVal}</span>` : toVal}
                </div>
            </div>
        `;
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
