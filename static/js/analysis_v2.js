(() => {
    'use strict';

    const feed = document.getElementById('signalFeed');
    const feedStatus = document.getElementById('feedStatus');
    const refreshBtn = document.getElementById('refreshBtn');
    const lastRefresh = document.getElementById('lastRefresh');
    const filterButtons = Array.from(document.querySelectorAll('.filter-btn'));

    const counters = {
        all: document.getElementById('countAll'),
        FIRSAT: document.getElementById('countOpportunity'),
        IZLE: document.getElementById('countWatch'),
        UZAK_DUR: document.getElementById('countAvoid'),
    };

    let cards = [];
    let activeFilter = 'ALL';

    const esc = (value) => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');

    const fmtOdds = (value) => {
        const n = Number(value);
        return Number.isFinite(n) ? n.toFixed(2) : '—';
    };

    const fmtPct = (value) => {
        const n = Number(value);
        return Number.isFinite(n) ? `${n.toFixed(n % 1 === 0 ? 0 : 1)}%` : '—';
    };

    const fmtSigned = (value, suffix = '') => {
        const n = Number(value);
        if (!Number.isFinite(n)) return '—';
        const sign = n > 0 ? '+' : '';
        return `${sign}${n.toFixed(Math.abs(n) >= 10 ? 0 : 1)}${suffix}`;
    };

    const fmtMoney = (value, signed = false) => {
        const n = Number(value);
        if (!Number.isFinite(n)) return '—';
        const sign = signed && n > 0 ? '+' : (n < 0 ? '−' : '');
        const abs = Math.abs(n);
        let body;
        if (abs >= 1_000_000) body = `${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
        else if (abs >= 1_000) body = `${(abs / 1_000).toFixed(abs >= 100_000 ? 0 : 1)}K`;
        else body = abs.toFixed(abs >= 100 ? 0 : 1);
        return `${sign}£${body}`;
    };

    const fmtDate = (iso) => {
        if (!iso) return 'Saat bilgisi yok';
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) return String(iso);
        return new Intl.DateTimeFormat('tr-TR', {
            day: '2-digit',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit',
        }).format(date);
    };

    const windowLabel = (windowKey) => ({
        '30m': 'Son 30 dk',
        '2h': 'Son 2 saat',
        '6h': 'Son 6 saat',
        'open': 'Açılıştan beri',
    }[windowKey] || 'Karar penceresi');

    const levelClass = (level) => String(level || 'UNKNOWN').toLowerCase().replaceAll('_', '-');

    const severityLabel = (severity) => ({
        HARD: 'Ciddi',
        MEDIUM: 'Orta',
        LOW: 'Düşük',
    }[severity] || severity || '—');

    const emptyState = (title, copy, icon = '○') => `
        <div class="empty-state">
            <div class="empty-icon">${esc(icon)}</div>
            <h3>${esc(title)}</h3>
            <p>${esc(copy)}</p>
        </div>
    `;

    const renderLoading = () => {
        const template = document.getElementById('loadingTemplate');
        feed.innerHTML = '';
        for (let i = 0; i < 3; i += 1) {
            feed.appendChild(template.content.cloneNode(true));
        }
    };

    const renderCounters = (counts = {}) => {
        counters.all.textContent = String(cards.length);
        counters.FIRSAT.textContent = String(counts.FIRSAT || 0);
        counters.IZLE.textContent = String(counts.IZLE || 0);
        counters.UZAK_DUR.textContent = String(counts.UZAK_DUR || 0);
    };

    const metricCells = (movement) => {
        const money = fmtMoney(movement.money_added, true);
        const odds = (
            movement.base_odds != null || movement.current_odds != null
                ? `${fmtOdds(movement.base_odds)} → ${fmtOdds(movement.current_odds)}`
                : '—'
        );
        return `
            <div class="metric-cell">
                <span class="metric-label">Pencere</span>
                <span class="metric-value">${esc(windowLabel(movement.window))}</span>
            </div>
            <div class="metric-cell">
                <span class="metric-label">Eklenen Para</span>
                <span class="metric-value accent">${esc(money)}</span>
            </div>
            <div class="metric-cell">
                <span class="metric-label">Oran Hareketi</span>
                <span class="metric-value">${esc(odds)}</span>
            </div>
            <div class="metric-cell">
                <span class="metric-label">Para Payı</span>
                <span class="metric-value">${esc(fmtPct(movement.current_pct))} · ${esc(fmtSigned(movement.pct_delta, ' puan'))}</span>
            </div>
        `;
    };

    const renderComponents = (components) => (components || []).map((item) => `
        <div class="component-card" title="${esc((item.reason_codes || []).join(' · '))}">
            <span class="component-label">${esc(item.label)}</span>
            <span class="component-level ${esc(levelClass(item.level))}">
                ${esc(item.level_label)}
            </span>
        </div>
    `).join('');

    const renderWhy = (card) => {
        const lines = card.why || [];
        if (!lines.length) return '<div class="detail-body">Bu kart için ek açıklama bulunmuyor.</div>';
        return `
            <div class="detail-body">
                <ul class="detail-list">
                    ${lines.map((line) => `<li>${esc(line)}</li>`).join('')}
                </ul>
            </div>
        `;
    };

    const renderRisks = (card) => {
        const risks = card.risks || [];
        if (!risks.length) {
            return '<div class="detail-body no-risk">Bu kartta kayıtlı materyal risk yok.</div>';
        }
        return `
            <div class="detail-body">
                ${risks.map((risk) => `
                    <div class="risk-chip">
                        <span>${esc(String(risk.code || '').replaceAll('_', ' '))}</span>
                        <small>${esc(severityLabel(risk.severity))}</small>
                    </div>
                `).join('')}
            </div>
        `;
    };

    const renderDetails = (card) => {
        const d = card.details || {};
        return `
            <div class="detail-body detail-kv">
                <span>Primary class</span><span>${esc(d.primary_class || '—')}</span>
                <span>Karar penceresi</span><span>${esc(windowLabel(d.decision_window))}</span>
                <span>Kaynak market</span><span>${esc(d.source_market || '—')} · ${esc(d.source_selection || '—')}</span>
                <span>Engine</span><span>${esc(d.engine_key || '—')} @ ${esc(d.engine_version || '—')}</span>
                <span>Risk sayısı</span><span>${esc(d.risk_count ?? 0)}</span>
                <span>Ledger durumu</span><span>${esc(card.current_state || '—')}</span>
            </div>
        `;
    };

    const renderCard = (card) => {
        const reco = card.recommendation || {};
        const movement = card.movement || {};
        const flow = card.flow || [];
        const odds = reco.odds != null ? `@${fmtOdds(reco.odds)}` : 'oran yok';
        return `
            <article class="signal-card" data-tone="${esc(card.state_tone || 'muted')}">
                <div class="signal-main">
                    <div class="signal-topline">
                        <div>
                            <div class="signal-meta">
                                <span class="state-badge ${esc(card.state_tone || 'muted')}">${esc(card.state_label)}</span>
                                <span class="league">${esc(card.league || 'Lig bilgisi yok')}</span>
                                <span class="kickoff">${esc(fmtDate(card.kickoff_utc))}</span>
                            </div>
                            <h2 class="match-title">${esc(card.match)}</h2>
                            <p class="signal-state-summary">${esc(card.state_summary || '')}</p>
                        </div>
                        <div class="reco-box">
                            <span class="reco-kicker">Piyasanın en sağlıklı ifadesi</span>
                            <div class="reco-main">
                                <span class="reco-selection">${esc(reco.selection || '—')}</span>
                                <span class="reco-odds">${esc(odds)}</span>
                            </div>
                            <span class="reco-market">${esc(reco.market || '—')} marketi</span>
                        </div>
                    </div>

                    <p class="direction-copy">${esc(reco.direction_copy || '')}</p>

                    <div class="flow-row" aria-label="Piyasa teyit zinciri">
                        ${flow.map((step, index) => `
                            ${index ? '<span class="flow-arrow">→</span>' : ''}
                            <span class="flow-step ${esc(step.tone || 'muted')}">${esc(step.label)}</span>
                        `).join('')}
                    </div>

                    <div class="metric-strip">
                        ${metricCells(movement)}
                    </div>
                </div>

                <div class="component-grid">
                    ${renderComponents(card.components)}
                </div>

                <div class="signal-details">
                    <details>
                        <summary>NEDEN?</summary>
                        ${renderWhy(card)}
                    </details>
                    <details>
                        <summary>RİSKLER</summary>
                        ${renderRisks(card)}
                    </details>
                    <details>
                        <summary>DETAYLAR</summary>
                        ${renderDetails(card)}
                    </details>
                </div>
            </article>
        `;
    };

    const renderFeed = () => {
        const visible = activeFilter === 'ALL'
            ? cards
            : cards.filter((card) => card.state === activeFilter);

        if (!visible.length) {
            feed.innerHTML = emptyState(
                activeFilter === 'ALL' ? 'Henüz V2 sinyali yok' : 'Bu filtrede sinyal yok',
                activeFilter === 'ALL'
                    ? 'Immutable V2 ledger veri üretmeye başladığında açıklanabilir sinyal kartları burada görünecek.'
                    : 'Başka bir durum filtresi seçebilir veya veriyi yenileyebilirsiniz.',
                '◇'
            );
            return;
        }
        feed.innerHTML = visible.map(renderCard).join('');
    };

    const showStatus = (message, warning = false) => {
        if (!message) {
            feedStatus.className = 'feed-status';
            feedStatus.textContent = '';
            return;
        }
        feedStatus.textContent = message;
        feedStatus.className = `feed-status show${warning ? ' warning' : ''}`;
    };

    const reasonMessage = (reason) => ({
        V2_LEDGER_NOT_DEPLOYED: 'Analizler V2 arayüzü hazır. Immutable V2 ledger migrationı henüz bu veritabanına uygulanmadığı için gerçek sinyal kartı gösterilmiyor.',
        SUPABASE_UNAVAILABLE: 'V2 veri kaynağına şu anda erişilemiyor.',
        V2_LEDGER_READ_FAILED: 'V2 ledger okunamadı. Veri kaynağı hazır olduğunda kartlar otomatik görünecek.',
        V2_FEED_ERROR: 'V2 sinyal akışı yüklenirken beklenmeyen bir hata oluştu.',
    }[reason] || 'V2 sinyal akışı şu anda kullanılamıyor.');

    const fetchFeed = async () => {
        renderLoading();
        showStatus('');
        refreshBtn.classList.add('loading');
        refreshBtn.disabled = true;

        try {
            const licKey = localStorage.getItem('smartxflow_web_license') || '';
            const response = await fetch('/api/analysis-v2/signals?limit=100', {
                headers: licKey ? { 'X-License-Key': licKey } : {},
            });

            if (response.status === 401 || response.status === 403) {
                cards = [];
                renderCounters({});
                feed.innerHTML = emptyState(
                    'Erişim doğrulanamadı',
                    'Analizler V2 verisini görmek için hesabınızla giriş yapın veya aktif lisansınızı doğrulayın.',
                    '🔒'
                );
                return;
            }

            const payload = await response.json();
            if (!payload.available) {
                cards = [];
                renderCounters(payload.counts || {});
                showStatus(reasonMessage(payload.reason), true);
                feed.innerHTML = emptyState(
                    'V2 veri akışı bekleniyor',
                    'Arayüz sahte/demo sinyal üretmez. Gerçek immutable ledger verisi geldiğinde kartlar burada oluşacak.',
                    '◎'
                );
                return;
            }

            cards = Array.isArray(payload.signals) ? payload.signals : [];
            renderCounters(payload.counts || {});
            renderFeed();
            lastRefresh.textContent = `Güncellendi · ${new Intl.DateTimeFormat('tr-TR', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
            }).format(new Date())}`;
        } catch (error) {
            cards = [];
            renderCounters({});
            showStatus('V2 sinyal akışına bağlanılamadı.', true);
            feed.innerHTML = emptyState(
                'Bağlantı kurulamadı',
                'Veri kaynağına erişim yeniden sağlandığında sayfayı yenileyin.',
                '!'
            );
        } finally {
            refreshBtn.classList.remove('loading');
            refreshBtn.disabled = false;
        }
    };

    filterButtons.forEach((button) => {
        button.addEventListener('click', () => {
            activeFilter = button.dataset.filter || 'ALL';
            filterButtons.forEach((item) => item.classList.toggle('active', item === button));
            renderFeed();
        });
    });

    refreshBtn.addEventListener('click', fetchFeed);
    document.addEventListener('DOMContentLoaded', fetchFeed);
})();
