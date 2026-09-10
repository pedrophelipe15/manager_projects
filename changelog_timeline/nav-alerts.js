// Nav Alert Badge — carrega contagem de alertas e mostra badge no link Insights
(function() {
    async function loadAlertBadge() {
        try {
            const r = await fetch('/api/insights/alert-count');
            const data = await r.json();
            if (data.total > 0) {
                const insightsLink = document.querySelector('a[href="/insights.html"]');
                if (insightsLink) {
                    const badge = document.createElement('span');
                    badge.className = 'nav-alert-badge' + (data.critical > 0 ? ' critical' : '');
                    badge.textContent = data.total;
                    badge.title = data.critical > 0 
                        ? `${data.critical} alerta(s) critico(s)` 
                        : `${data.total} alerta(s)`;
                    insightsLink.style.position = 'relative';
                    insightsLink.appendChild(badge);
                }
            }
        } catch (e) { /* silently fail */ }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadAlertBadge);
    } else {
        loadAlertBadge();
    }
})();
