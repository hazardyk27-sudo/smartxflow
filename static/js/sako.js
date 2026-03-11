(function(){
    var matches = [];
    var searchInput = document.getElementById('sakoSearchInput');
    var dropdown = document.getElementById('sakoDropdown');
    var clearBtn = document.getElementById('sakoSearchClear');
    var resultsEl = document.getElementById('sakoResults');
    var loadingEl = document.getElementById('sakoLoading');
    var emptyEl = document.getElementById('sakoEmpty');
    var debounceTimer = null;

    function getLicenseKey(){
        try { return localStorage.getItem('smartxflow_license_key') || ''; } catch(e){ return ''; }
    }

    function sakoFetch(url, opts){
        opts = opts || {};
        opts.headers = opts.headers || {};
        var k = getLicenseKey();
        if(k) opts.headers['X-License-Key'] = k;
        return fetch(url, opts).then(function(r){
            if(r.status === 403){
                window.location.href = '/app';
                throw new Error('LICENSE_REQUIRED');
            }
            return r;
        });
    }

    function loadMatches(){
        sakoFetch('/api/sako/matches').then(function(r){ return r.json(); }).then(function(data){
            matches = data.matches || [];
        }).catch(function(){});
    }

    searchInput.addEventListener('input', function(){
        var v = this.value.trim();
        clearBtn.style.display = v ? 'block' : 'none';
        clearTimeout(debounceTimer);
        if(!v){ closeDropdown(); return; }
        debounceTimer = setTimeout(function(){ filterMatches(v); }, 150);
    });

    searchInput.addEventListener('focus', function(){
        if(this.value.trim()) filterMatches(this.value.trim());
    });

    document.addEventListener('click', function(e){
        if(!e.target.closest('.sako-search-card')) closeDropdown();
    });

    window.clearSakoSearch = function(){
        searchInput.value = '';
        clearBtn.style.display = 'none';
        closeDropdown();
    };

    function closeDropdown(){
        dropdown.classList.remove('open');
    }

    function filterMatches(q){
        var lower = q.toLowerCase();
        var filtered = matches.filter(function(m){
            return (m.name && m.name.toLowerCase().indexOf(lower) !== -1) ||
                   (m.league && m.league.toLowerCase().indexOf(lower) !== -1);
        }).slice(0, 15);

        if(!filtered.length){
            dropdown.innerHTML = '<div class="sako-dd-empty">Sonuç bulunamadı</div>';
            dropdown.classList.add('open');
            return;
        }

        var html = '';
        filtered.forEach(function(m){
            html += '<div class="sako-dd-item" data-hash="' + m.hash + '">';
            html += '<div class="sako-dd-match">' + esc(m.name) + '</div>';
            html += '<div class="sako-dd-league">' + esc(m.league) + '</div>';
            html += '</div>';
        });
        dropdown.innerHTML = html;
        dropdown.classList.add('open');

        dropdown.querySelectorAll('.sako-dd-item').forEach(function(el){
            el.addEventListener('click', function(){
                var hash = this.getAttribute('data-hash');
                var name = this.querySelector('.sako-dd-match').textContent;
                searchInput.value = name;
                clearBtn.style.display = 'block';
                closeDropdown();
                runSimilarity(hash);
            });
        });
    }

    function runSimilarity(hash){
        emptyEl.style.display = 'none';
        resultsEl.style.display = 'none';
        loadingEl.style.display = 'block';

        sakoFetch('/api/sako/run?match_id_hash=' + encodeURIComponent(hash))
            .then(function(r){ return r.json(); })
            .then(function(data){
                loadingEl.style.display = 'none';
                if(data.error){
                    emptyEl.querySelector('.sako-empty-title').textContent = 'Hata';
                    emptyEl.querySelector('.sako-empty-desc').textContent = data.error;
                    emptyEl.style.display = 'block';
                    return;
                }
                renderResults(data);
            })
            .catch(function(err){
                loadingEl.style.display = 'none';
                emptyEl.querySelector('.sako-empty-title').textContent = 'Bağlantı Hatası';
                emptyEl.querySelector('.sako-empty-desc').textContent = 'Lütfen tekrar deneyin';
                emptyEl.style.display = 'block';
            });
    }

    function renderResults(data){
        renderSummary(data.query_summary);
        renderDistribution(data.result_distribution);
        renderPattern(data.overall_explainability);
        renderMatches(data.similar_matches);
        document.getElementById('sakoMatchCount').textContent = data.matches_found || 0;
        resultsEl.style.display = 'block';
    }

    function renderSummary(qs){
        var dr = qs.draw_regime || {};
        var ts = qs.timing_signature || {};
        var opening = qs.opening_odds || {};
        var closing = qs.closing_odds || {};

        var drawBadge = dr.is_draw_regime
            ? '<span class="sako-sum-draw-badge">Draw Regime Aktif (' + (dr.draw_regime_score || 0).toFixed(2) + ')</span>'
            : '';

        var oddsOrder = ['home', '1', 'draw', 'x', 'away', '2'];
        var oddsStr = '';
        if(Object.keys(opening).length){
            var parts = [];
            oddsOrder.forEach(function(k){ if(opening[k] != null) parts.push(fmtOdds(opening[k])); });
            if(!parts.length) Object.keys(opening).forEach(function(k){ parts.push(fmtOdds(opening[k])); });
            oddsStr = parts.join(' / ');
        }
        var closingStr = '';
        if(Object.keys(closing).length){
            var cp = [];
            oddsOrder.forEach(function(k){ if(closing[k] != null) cp.push(fmtOdds(closing[k])); });
            if(!cp.length) Object.keys(closing).forEach(function(k){ cp.push(fmtOdds(closing[k])); });
            closingStr = cp.join(' / ');
        }

        var timingLabel = {
            'late_driven': 'Son Saatler',
            'early_driven': 'Erken Saatler',
            'mid_driven': 'Orta Dönem',
            'balanced': 'Dengeli'
        };

        var kickoffStr = '';
        if(qs.kickoff_time){
            try {
                var d = new Date(qs.kickoff_time);
                if(!isNaN(d.getTime())){
                    kickoffStr = d.toLocaleDateString('tr-TR', {day:'2-digit',month:'short',year:'numeric'}) + ' ' + d.toLocaleTimeString('tr-TR', {hour:'2-digit',minute:'2-digit'});
                }
            } catch(e){}
        }

        document.getElementById('sakoSummary').innerHTML =
            '<div class="sako-sum-header">' +
                '<div><div class="sako-sum-name">' + esc(qs.match_name || '?') + '</div>' +
                '<div class="sako-sum-league">' + esc(qs.league || '') + (kickoffStr ? ' — ' + esc(kickoffStr) : '') + '</div></div>' +
                drawBadge +
            '</div>' +
            '<div class="sako-sum-grid">' +
                sumStat('Açılış Odds', oddsStr || '—') +
                sumStat('Kapanış Odds', closingStr || '—') +
                sumStat('Toplam Hacim', fmtVol(qs.total_volume)) +
                sumStat('Baskı Zamanı', timingLabel[ts.dominant_timing] || ts.dominant_timing || '—') +
            '</div>';
    }

    function sumStat(label, value){
        return '<div class="sako-sum-stat"><div class="sako-sum-stat-label">' + label + '</div><div class="sako-sum-stat-value">' + value + '</div></div>';
    }

    function renderDistribution(dist){
        var simple = dist.simple || {};
        var weighted = dist.weighted || {};
        document.getElementById('sakoDistribution').innerHTML =
            '<div class="sako-dist-card">' +
                '<div class="sako-dist-title">Simple (' + (simple.total || 0) + ' maç)</div>' +
                distBar('Ev', simple.home || 0, 'home') +
                distBar('Beraberlik', simple.draw || 0, 'draw') +
                distBar('Deplasman', simple.away || 0, 'away') +
            '</div>' +
            '<div class="sako-dist-card">' +
                '<div class="sako-dist-title">Weighted</div>' +
                distBar('Ev', weighted.home || 0, 'home') +
                distBar('Beraberlik', weighted.draw || 0, 'draw') +
                distBar('Deplasman', weighted.away || 0, 'away') +
            '</div>';
    }

    function distBar(label, pct, cls){
        var color = cls === 'home' ? '#22C55E' : cls === 'draw' ? '#FACC15' : '#EF4444';
        return '<div class="sako-dist-bar-wrap">' +
            '<div class="sako-dist-label">' +
                '<span class="sako-dist-label-name">' + label + '</span>' +
                '<span class="sako-dist-label-pct" style="color:' + color + '">' + pct.toFixed(1) + '%</span>' +
            '</div>' +
            '<div class="sako-dist-bar"><div class="sako-dist-fill ' + cls + '" style="width:' + Math.min(pct, 100) + '%"></div></div>' +
        '</div>';
    }

    function renderPattern(overall){
        var html = '<div class="sako-pat-main">' + esc(overall.main_pattern_label || '—') + '</div>';
        html += '<div class="sako-pat-row">';

        html += '<div class="sako-pat-block"><div class="sako-pat-block-title">Ortak Özellikler</div>';
        (overall.top_3_common_traits || []).forEach(function(t){
            html += '<div class="sako-pat-item">' + esc(t.trait) + ' <span style="color:#8B5CF6;font-family:JetBrains Mono,monospace;font-size:12px">(' + t.avg_score.toFixed(3) + ')</span></div>';
        });
        html += '</div>';

        html += '<div class="sako-pat-block"><div class="sako-pat-block-title">Risk Faktörleri</div>';
        (overall.top_2_risk_traits || []).forEach(function(t){
            html += '<div class="sako-pat-item">' + esc(t.risk) + '</div>';
        });
        html += '</div>';

        html += '</div>';

        if(overall.top_mismatch_patterns && overall.top_mismatch_patterns.length){
            overall.top_mismatch_patterns.forEach(function(p){
                html += '<div class="sako-pat-warn">' + esc(p) + '</div>';
            });
        }

        html += '<div class="sako-pat-tags">';
        if(overall.draw_risk) html += '<span class="sako-pat-tag risk">Draw Riski</span>';
        else html += '<span class="sako-pat-tag ok">Draw Riski Düşük</span>';
        if(overall.market_contradiction) html += '<span class="sako-pat-tag risk">Market Çelişkisi</span>';
        else html += '<span class="sako-pat-tag ok">Market Uyumlu</span>';
        html += '</div>';

        document.getElementById('sakoPattern').innerHTML = html;
    }

    function renderMatches(matches){
        var html = '';
        (matches || []).forEach(function(m, idx){
            var resultCls = 'unknown';
            var resultLabel = m.result || '?';
            if(m.result){
                var r = m.result.toUpperCase();
                if(r === 'HOME' || r === '1' || r === 'H'){ resultCls = 'home'; resultLabel = 'Ev'; }
                else if(r === 'DRAW' || r === 'X' || r === 'D'){ resultCls = 'draw'; resultLabel = 'Beraberlik'; }
                else if(r === 'AWAY' || r === '2' || r === 'A'){ resultCls = 'away'; resultLabel = 'Deplasman'; }
            }

            var scorePct = Math.round((m.similarity_score || 0) * 100);

            html += '<div class="sako-match-card">';
            html += '<div class="sako-mc-top">';
            html += '<div><div class="sako-mc-name">' + esc(m.match_name) + '</div><div class="sako-mc-league">' + esc(m.league) + '</div></div>';
            html += '<div class="sako-mc-score">';
            html += '<span class="sako-mc-result ' + resultCls + '">' + resultLabel + '</span>';
            html += '<div class="sako-mc-score-bar"><div class="sako-mc-score-fill" style="width:' + scorePct + '%"></div></div>';
            html += '<span class="sako-mc-score-val">' + scorePct + '%</span>';
            html += '</div></div>';

            if(m.pattern_label) html += '<div class="sako-mc-pattern">' + esc(m.pattern_label) + '</div>';

            html += '<div class="sako-mc-odds-grid">';
            html += fmtOddsBlock('1X2', m.opening_odds, m.closing_odds, m.closing_amounts, ['home','draw','away'], ['1','X','2']);
            html += fmtOddsBlock('2.5 KG', m.ou25_opening, m.ou25_closing, m.ou25_closing_amounts, ['over','under'], ['Üst','Alt']);
            html += '<div class="sako-mc-odds-block"><div class="sako-mc-odds-block-title">Hacim</div><div class="sako-mc-odds-block-val">' + fmtVol(m.total_volume) + '</div></div>';
            html += '</div>';

            html += '<div class="sako-mc-detail" id="sakoDetail' + idx + '">';

            html += '<div class="sako-mc-blocks">';
            html += '<div><div class="sako-mc-block-group-title">En Çok Benzeyen Bloklar</div>';
            (m.top_3_similar_blocks || []).forEach(function(b){
                html += '<div class="sako-mc-block-item"><span>' + esc(shortBlock(b.label)) + '</span><span class="sako-mc-block-score">' + (b.score * 100).toFixed(0) + '%</span></div>';
            });
            html += '</div>';
            html += '<div><div class="sako-mc-block-group-title">En Çok Ayrışan Bloklar</div>';
            (m.top_2_divergent_blocks || []).forEach(function(b){
                html += '<div class="sako-mc-block-item"><span>' + esc(shortBlock(b.label)) + '</span><span class="sako-mc-block-score" style="color:#EF4444">' + (b.score * 100).toFixed(0) + '%</span></div>';
            });
            html += '</div>';
            html += '</div>';

            html += '<div class="sako-mc-phases">';
            if(m.closest_phases && m.closest_phases.length){
                html += '<div class="sako-mc-phase-group"><div class="sako-mc-phase-title">En Yakın Fazlar</div><div class="sako-mc-phase-list">';
                m.closest_phases.forEach(function(p){ html += '<span class="sako-mc-phase-tag close">' + shortPhase(p) + '</span>'; });
                html += '</div></div>';
            }
            if(m.farthest_phases && m.farthest_phases.length){
                html += '<div class="sako-mc-phase-group"><div class="sako-mc-phase-title">En Farklı Fazlar</div><div class="sako-mc-phase-list">';
                m.farthest_phases.forEach(function(p){ html += '<span class="sako-mc-phase-tag far">' + shortPhase(p) + '</span>'; });
                html += '</div></div>';
            }
            html += '</div>';

            html += '</div>';

            html += '<div class="sako-mc-toggle"><button class="sako-mc-toggle-btn" onclick="toggleSakoDetail(' + idx + ', this)">Detay Göster ▼</button></div>';
            html += '</div>';
        });

        document.getElementById('sakoMatches').innerHTML = html || '<div class="sako-dd-empty">Benzer maç bulunamadı</div>';
    }

    window.toggleSakoDetail = function(idx, btn){
        var el = document.getElementById('sakoDetail' + idx);
        if(el.classList.contains('open')){
            el.classList.remove('open');
            btn.textContent = 'Detay Göster ▼';
        } else {
            el.classList.add('open');
            btn.textContent = 'Detay Gizle ▲';
        }
    };

    function shortBlock(label){
        if(!label) return '';
        var idx = label.indexOf('(');
        return idx > 0 ? label.substring(0, idx).trim() : label;
    }

    function shortPhase(p){
        if(!p) return '';
        var phaseMap = {
            'P1_0to1h': 'Son 1 saat',
            'P2_1to2h': '1-2 saat',
            'P3_2to4h': '2-4 saat',
            'P4_4to8h': '4-8 saat',
            'P5_8to12h': '8-12 saat',
            'P6_12to16h': '12-16 saat',
            'P7_16to20h': '16-20 saat',
            'P8_20to30h': '20-30 saat',
            'P9_30to40h': '30-40 saat',
            'P10_40plus': '40+ saat'
        };
        return phaseMap[p] || p;
    }

    function fmtOddsBlock(title, opening, closing, amounts, keys, labels){
        var h = '<div class="sako-mc-odds-block"><div class="sako-mc-odds-block-title">' + title + '</div>';
        h += '<table class="sako-mc-odds-table"><thead><tr><th></th><th>Açılış</th><th>Kapanış</th><th>Para</th></tr></thead><tbody>';
        for(var i = 0; i < keys.length; i++){
            var k = keys[i];
            var lbl = labels[i];
            var op = (opening && opening[k] != null) ? fmtOdds(opening[k]) : '—';
            var cl = (closing && closing[k] != null) ? fmtOdds(closing[k]) : '—';
            var am = (amounts && amounts[k] != null) ? fmtVol(amounts[k]) : '—';
            h += '<tr><td class="sako-mc-odds-lbl">' + lbl + '</td><td>' + op + '</td><td>' + cl + '</td><td>' + am + '</td></tr>';
        }
        h += '</tbody></table></div>';
        return h;
    }

    function fmtMatchOdds(opening, closing){
        if(!opening || !Object.keys(opening).length) return '—';
        var oddsOrder = ['home', '1', 'draw', 'x', 'away', '2'];
        var op = [], cl = [];
        oddsOrder.forEach(function(k){ if(opening[k] != null) op.push(fmtOdds(opening[k])); });
        if(!op.length) Object.keys(opening).forEach(function(k){ op.push(fmtOdds(opening[k])); });
        if(closing && Object.keys(closing).length){
            oddsOrder.forEach(function(k){ if(closing[k] != null) cl.push(fmtOdds(closing[k])); });
            if(!cl.length) Object.keys(closing).forEach(function(k){ cl.push(fmtOdds(closing[k])); });
        }
        var s = op.join('/');
        if(cl.length) s += ' → ' + cl.join('/');
        return s;
    }

    function fmtMatchOu(opening, closing){
        if(!opening || !Object.keys(opening).length) return '—';
        var ouOrder = ['over', 'under'];
        var op = [], cl = [];
        ouOrder.forEach(function(k){ if(opening[k] != null) op.push(fmtOdds(opening[k])); });
        if(!op.length) Object.keys(opening).forEach(function(k){ op.push(fmtOdds(opening[k])); });
        if(closing && Object.keys(closing).length){
            ouOrder.forEach(function(k){ if(closing[k] != null) cl.push(fmtOdds(closing[k])); });
            if(!cl.length) Object.keys(closing).forEach(function(k){ cl.push(fmtOdds(closing[k])); });
        }
        var s = op.join('/');
        if(cl.length) s += ' → ' + cl.join('/');
        return s;
    }

    function fmtOdds(v){
        if(v == null) return '—';
        return Number(v).toFixed(2);
    }

    function fmtVol(v){
        if(v == null) return '—';
        if(v >= 1000000) return (v/1000000).toFixed(1) + 'M';
        if(v >= 1000) return (v/1000).toFixed(0) + 'K';
        return v.toString();
    }

    function esc(s){
        if(!s) return '';
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    loadMatches();

    var urlParams = new URLSearchParams(window.location.search);
    var preHash = urlParams.get('match');
    if(preHash) runSimilarity(preHash);
})();
