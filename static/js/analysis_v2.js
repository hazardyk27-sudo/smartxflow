(() => {
    'use strict';

    const feed = document.getElementById('signalFeed');
    const feedStatus = document.getElementById('feedStatus');
    const refreshBtn = document.getElementById('refreshBtn');
    const lastRefresh = document.getElementById('lastRefresh');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const signalSearch = document.getElementById('signalSearch');
    const marketFilter = document.getElementById('marketFilter');
    const filterButtons = Array.from(document.querySelectorAll('.filter-btn'));
    const scopeButtons = Array.from(document.querySelectorAll('.scope-btn'));
    const drawer = document.getElementById('signalDetailDrawer');
    const drawerBackdrop = document.getElementById('signalDetailBackdrop');
    const drawerClose = document.getElementById('detailDrawerClose');
    const drawerTitle = document.getElementById('detailDrawerTitle');
    const drawerBody = document.getElementById('detailDrawerBody');

    const counters = {
        all: document.getElementById('countAll'),
        FIRSAT: document.getElementById('countOpportunity'),
        IZLE: document.getElementById('countWatch'),
        UZAK_DUR: document.getElementById('countAvoid'),
    };

    const PAGE_SIZE = 100;
    let cards = [];
    let activeFilter = 'ALL';
    let activeScope = 'active';
    let activeMarket = '';
    let searchQuery = '';
    let nextOffset = 0;
    let hasMore = false;
    let loading = false;
    let searchTimer = null;

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
        return Number.isFinite(n)
            ? `${n.toFixed(n % 1 === 0 ? 0 : 1)}%`
            : '—';
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

    const fmtDate = (iso, includeYear = false) => {
        if (!iso) return 'Saat bilgisi yok';
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) return String(iso);
        return new Intl.DateTimeFormat('tr-TR', {
            day: '2-digit',
            month: 'short',
            ...(includeYear ? { year: 'numeric' } : {}),
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

    const outcomeLabel = (outcome) => ({
        WIN: 'Kazandı',
        LOSS: 'Kaybetti',
        PUSH: 'İade',
        VOID: 'Geçersiz',
        UNKNOWN: 'Bilinmiyor',
    }[outcome] || outcome || '—');

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

    const renderCounters = () => {
        const counts = { FIRSAT: 0, IZLE: 0, UZAK_DUR: 0, UNKNOWN: 0 };
        cards.forEach((card) => {
            const state = counts[card.state] != null ? card.state : 'UNKNOWN';
            counts[state] += 1;
        });
        counters.all.textContent = String(cards.length);
        counters.FIRSAT.textContent = String(counts.FIRSAT);
        counters.IZLE.textContent = String(counts.IZLE);
        counters.UZAK_DUR.textContent = String(counts.UZAK_DUR);
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
        if (!lines.length) {
            return '<div class="detail-body">Bu kart için ek açıklama bulunmuyor.</div>';
        }
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

                    <button
                        class="signal-card-open"
                        type="button"
                        data-signal-id="${esc(card.signal_id)}"
                    >
                        SİNYAL GEÇMİŞİ
                        <span aria-hidden="true">→</span>
                    </button>
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

    const visibleCards = () => (
        activeFilter === 'ALL'
            ? cards
            : cards.filter((card) => card.state === activeFilter)
    );

    const renderFeed = () => {
        const visible = visibleCards();
        if (!visible.length) {
            feed.innerHTML = emptyState(
                activeFilter === 'ALL' ? 'Bu görünümde V2 sinyali yok' : 'Bu durumda sinyal yok',
                activeScope === 'history'
                    ? 'Geçmiş ve sonuçlanmış sinyaller immutable ledger üzerinde biriktikçe burada görünecek.'
                    : 'Filtreleri değiştirebilir veya veriyi yenileyebilirsiniz.',
                '◇'
            );
            loadMoreBtn.hidden = true;
            return;
        }
        feed.innerHTML = visible.map(renderCard).join('');
        loadMoreBtn.hidden = !hasMore;
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

    const apiHeaders = () => {
        const licKey = localStorage.getItem('smartxflow_web_license') || '';
        return licKey ? { 'X-License-Key': licKey } : {};
    };

    const buildFeedUrl = (offset = 0) => {
        const params = new URLSearchParams({
            limit: String(PAGE_SIZE),
            offset: String(offset),
            scope: activeScope,
        });
        if (activeMarket) params.set('market', activeMarket);
        if (searchQuery) params.set('q', searchQuery);
        return `/api/analysis-v2/signals?${params.toString()}`;
    };

    const fetchFeed = async ({ append = false } = {}) => {
        if (loading) return;
        loading = true;
        showStatus('');
        refreshBtn.classList.add('loading');
        refreshBtn.disabled = true;
        loadMoreBtn.disabled = true;

        if (!append) {
            renderLoading();
            nextOffset = 0;
        }

        try {
            const offset = append ? nextOffset : 0;
            const response = await fetch(buildFeedUrl(offset), {
                headers: apiHeaders(),
            });

            if (response.status === 401 || response.status === 403) {
                cards = [];
                renderCounters();
                feed.innerHTML = emptyState(
                    'Erişim doğrulanamadı',
                    'Analizler V2 verisini görmek için hesabınızla giriş yapın veya aktif lisansınızı doğrulayın.',
                    '🔒'
                );
                loadMoreBtn.hidden = true;
                return;
            }

            const payload = await response.json();
            if (!payload.available) {
                cards = [];
                renderCounters();
                showStatus(reasonMessage(payload.reason), true);
                feed.innerHTML = emptyState(
                    'V2 veri akışı bekleniyor',
                    'Arayüz sahte/demo sinyal üretmez. Gerçek immutable ledger verisi geldiğinde kartlar burada oluşacak.',
                    '◎'
                );
                loadMoreBtn.hidden = true;
                return;
            }

            const incoming = Array.isArray(payload.signals) ? payload.signals : [];
            cards = append ? cards.concat(incoming) : incoming;
            hasMore = Boolean(payload.has_more);
            nextOffset = offset + PAGE_SIZE;

            renderCounters();
            renderFeed();
            lastRefresh.textContent = `Güncellendi · ${new Intl.DateTimeFormat('tr-TR', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
            }).format(new Date())}`;
        } catch (error) {
            if (!append) cards = [];
            renderCounters();
            showStatus('V2 sinyal akışına bağlanılamadı.', true);
            if (!append) {
                feed.innerHTML = emptyState(
                    'Bağlantı kurulamadı',
                    'Veri kaynağına erişim yeniden sağlandığında sayfayı yenileyin.',
                    '!'
                );
            }
            loadMoreBtn.hidden = true;
        } finally {
            loading = false;
            refreshBtn.classList.remove('loading');
            refreshBtn.disabled = false;
            loadMoreBtn.disabled = false;
        }
    };

    const openDrawerShell = () => {
        drawerBackdrop.hidden = false;
        drawer.classList.add('open');
        drawer.setAttribute('aria-hidden', 'false');
        document.body.classList.add('drawer-open');
    };

    const closeDrawer = () => {
        drawer.classList.remove('open');
        drawer.setAttribute('aria-hidden', 'true');
        drawerBackdrop.hidden = true;
        document.body.classList.remove('drawer-open');
    };

    const timelineHtml = (items) => {
        if (!Array.isArray(items) || !items.length) {
            return '<div class="drawer-error">Lifecycle kaydı bulunamadı.</div>';
        }
        return `
            <ol class="timeline">
                ${items.map((item) => `
                    <li class="timeline-item ${esc(String(item.state || '').toLowerCase())}">
                        <span class="timeline-dot"></span>
                        <div class="timeline-head">
                            <strong>${esc(item.label || item.state || 'Durum')}</strong>
                            <time>${esc(fmtDate(item.state_at, true))}</time>
                        </div>
                        <div class="timeline-metrics">
                            Oran ${esc(fmtOdds(item.current_odds))}
                            · Para ${esc(fmtMoney(item.current_amount))}
                            · Pay ${esc(fmtPct(item.current_pct))}
                            ${item.reason_code ? ` · ${esc(item.reason_code)}` : ''}
                        </div>
                    </li>
                `).join('')}
            </ol>
        `;
    };

    const settlementHtml = (settlement) => {
        if (!settlement) {
            return '<div class="drawer-error">Sinyal henüz sonuçlanmadı.</div>';
        }
        const score = (
            settlement.final_home_score != null && settlement.final_away_score != null
                ? `${settlement.final_home_score} - ${settlement.final_away_score}`
                : '—'
        );
        return `
            <div class="settlement-box">
                <div class="settlement-cell"><span>Sonuç</span><strong>${esc(outcomeLabel(settlement.outcome))}</strong></div>
                <div class="settlement-cell"><span>Skor</span><strong>${esc(score)}</strong></div>
                <div class="settlement-cell"><span>Entry</span><strong>${esc(fmtOdds(settlement.entry_odds))}</strong></div>
                <div class="settlement-cell"><span>PnL</span><strong>${esc(fmtSigned(settlement.pnl_units, 'u'))}</strong></div>
                <div class="settlement-cell"><span>Settled</span><strong>${esc(fmtDate(settlement.settled_at, true))}</strong></div>
                <div class="settlement-cell"><span>Kaynak</span><strong>${esc(settlement.settlement_source || '—')}</strong></div>
            </div>
        `;
    };

    const auditHtml = (audit = {}) => `
        <div class="audit-grid">
            <span>Signal ID</span><span>${esc(audit.signal_id || '—')}</span>
            <span>Match hash</span><span>${esc(audit.match_id_hash || '—')}</span>
            <span>Engine</span><span>${esc(audit.engine_key || '—')} @ ${esc(audit.engine_version || '—')}</span>
            <span>Trigger</span><span>${esc(fmtDate(audit.trigger_at, true))}</span>
            <span>Kaynak</span><span>${esc(audit.source_market || '—')} · ${esc(audit.source_selection || '—')}</span>
            <span>Trigger odds</span><span>${esc(fmtOdds(audit.trigger_odds))}</span>
            <span>Trigger para</span><span>${esc(fmtMoney(audit.trigger_amount))}</span>
            <span>Öneri</span><span>${esc(audit.recommended_market || '—')} · ${esc(audit.recommended_selection || '—')} @ ${esc(fmtOdds(audit.recommended_odds))}</span>
        </div>
    `;

    const renderDrawer = (payload) => {
        const card = payload.card || {};
        const reco = card.recommendation || {};
        const audit = { ...(payload.audit || {}), signal_id: payload.signal_id };
        drawerTitle.textContent = card.match || 'Sinyal Detayı';
        drawerBody.innerHTML = `
            <section class="drawer-section">
                <div class="drawer-reco">
                    <div>
                        <span class="drawer-state ${esc(card.state_tone || 'muted')}">${esc(card.state_label || '—')}</span>
                        <strong>${esc(reco.selection || '—')} @ ${esc(fmtOdds(reco.odds))}</strong>
                        <small>${esc(reco.market || '—')} · ${esc(reco.direction_copy || '')}</small>
                    </div>
                    <small>${esc(fmtDate(card.kickoff_utc, true))}</small>
                </div>
            </section>
            <section class="drawer-section">
                <h3 class="drawer-section-title">Lifecycle</h3>
                ${timelineHtml(payload.timeline)}
            </section>
            <section class="drawer-section">
                <h3 class="drawer-section-title">Settlement</h3>
                ${settlementHtml(payload.settlement)}
            </section>
            <section class="drawer-section">
                <h3 class="drawer-section-title">Immutable Audit</h3>
                ${auditHtml(audit)}
            </section>
        `;
    };

    const openSignalDetail = async (signalId) => {
        if (!/^sig_[0-9a-f]{32}$/.test(signalId || '')) return;
        drawerTitle.textContent = 'Sinyal Detayı';
        drawerBody.innerHTML = '<div class="drawer-loading">Immutable lifecycle yükleniyor…</div>';
        openDrawerShell();

        try {
            const response = await fetch(
                `/api/analysis-v2/signals/${encodeURIComponent(signalId)}`,
                { headers: apiHeaders() }
            );
            const payload = await response.json();
            if (!payload.available || !payload.found) {
                drawerBody.innerHTML = `<div class="drawer-error">${esc(
                    payload.reason === 'V2_LEDGER_NOT_DEPLOYED'
                        ? 'V2 ledger henüz deploy edilmedi.'
                        : 'Sinyal detayı bulunamadı.'
                )}</div>`;
                return;
            }
            renderDrawer(payload);
        } catch (error) {
            drawerBody.innerHTML = '<div class="drawer-error">Sinyal detayı yüklenemedi.</div>';
        }
    };

    filterButtons.forEach((button) => {
        button.addEventListener('click', () => {
            activeFilter = button.dataset.filter || 'ALL';
            filterButtons.forEach((item) => item.classList.toggle('active', item === button));
            renderFeed();
        });
    });

    scopeButtons.forEach((button) => {
        button.addEventListener('click', () => {
            activeScope = button.dataset.scope || 'active';
            scopeButtons.forEach((item) => item.classList.toggle('active', item === button));
            fetchFeed();
        });
    });

    marketFilter.addEventListener('change', () => {
        activeMarket = marketFilter.value || '';
        fetchFeed();
    });

    signalSearch.addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            searchQuery = signalSearch.value.trim();
            fetchFeed();
        }, 280);
    });

    feed.addEventListener('click', (event) => {
        const button = event.target.closest('.signal-card-open');
        if (!button) return;
        openSignalDetail(button.dataset.signalId || '');
    });

    loadMoreBtn.addEventListener('click', () => fetchFeed({ append: true }));
    refreshBtn.addEventListener('click', () => fetchFeed());
    drawerClose.addEventListener('click', closeDrawer);
    drawerBackdrop.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && drawer.classList.contains('open')) {
            closeDrawer();
        }
    });

    document.addEventListener('DOMContentLoaded', () => fetchFeed());
})();
