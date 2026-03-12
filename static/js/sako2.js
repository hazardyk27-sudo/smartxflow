(function(){
    var matches = [];
    var searchInput = document.getElementById('sako2SearchInput');
    var dropdown = document.getElementById('sako2Dropdown');
    var clearBtn = document.getElementById('sako2SearchClear');
    var resultsEl = document.getElementById('sako2Results');
    var loadingEl = document.getElementById('sako2Loading');
    var emptyEl = document.getElementById('sako2Empty');
    var debounceTimer = null;

    function getLicenseKey(){
        try { return localStorage.getItem('smartxflow_license_key') || ''; } catch(e){ return ''; }
    }

    function sako2Fetch(url, opts){
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
        sako2Fetch('/api/sako/matches').then(function(r){ return r.json(); }).then(function(data){
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

    window.clearSako2Search = function(){
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

        sako2Fetch('/api/sako2/run?match_id_hash=' + encodeURIComponent(hash))
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
        document.getElementById('sako2MatchCount').textContent = data.matches_found || 0;
        resultsEl.style.display = 'block';
    }

    function renderSummary(qs){
        var opening = qs.opening_odds || {};
        var closing = qs.closing_odds || {};

        var oddsOrder = ['home', '1', 'draw', 'x', 'away', '2'];
        var oddsStr = fmtOddsLine(opening, oddsOrder);
        var closingStr = fmtOddsLine(closing, oddsOrder);

        var kickoffStr = '';
        if(qs.kickoff_time){
            try {
                var d = new Date(qs.kickoff_time);
                if(!isNaN(d.getTime())){
                    kickoffStr = d.toLocaleDateString('tr-TR', {day:'2-digit',month:'short',year:'numeric'}) + ' ' + d.toLocaleTimeString('tr-TR', {hour:'2-digit',minute:'2-digit'});
                }
            } catch(e){}
        }

        var ou25Opening = qs.ou25_opening || {};
        var ou25Closing = qs.ou25_closing || {};
        var bttsOpening = qs.btts_opening || {};
        var bttsClosing = qs.btts_closing || {};

        var ou25Str = fmtOddsLine(ou25Opening, ['over','under']);
        var ou25CloseStr = fmtOddsLine(ou25Closing, ['over','under']);
        var bttsStr = fmtOddsLine(bttsOpening, ['yes','no']);
        var bttsCloseStr = fmtOddsLine(bttsClosing, ['yes','no']);

        document.getElementById('sako2Summary').innerHTML =
            '<div class="sako-sum-header">' +
                '<div><div class="sako-sum-name">' + esc(qs.match_name || '?') + '</div>' +
                '<div class="sako-sum-league">' + esc(qs.league || '') + (kickoffStr ? ' — ' + esc(kickoffStr) : '') + '</div></div>' +
            '</div>' +
            '<div class="sako2-sum-markets">' +
                marketRow('1X2', oddsStr, closingStr, fmtAmounts(qs.closing_amounts, ['home','draw','away'], ['1','X','2'])) +
                marketRow('ÜA 2.5', ou25Str, ou25CloseStr, fmtAmounts(qs.ou25_closing_amounts, ['over','under'], ['Ü','A'])) +
                marketRow('KG', bttsStr, bttsCloseStr, fmtAmounts(qs.btts_closing_amounts, ['yes','no'], ['E','H'])) +
            '</div>' +
            '<div class="sako-sum-grid">' +
                sumStat('Toplam Hacim', fmtVol(qs.total_volume)) +
            '</div>';
    }

    function fmtOddsLine(odds, order){
        if(!odds || !Object.keys(odds).length) return '';
        var parts = [];
        order.forEach(function(k){ if(odds[k] != null) parts.push(fmtOdds(odds[k])); });
        if(!parts.length) Object.keys(odds).forEach(function(k){ parts.push(fmtOdds(odds[k])); });
        return parts.join(' / ');
    }

    function marketRow(title, openStr, closeStr, amountsStr){
        return '<div class="sako2-market-row">' +
            '<div class="sako2-market-title">' + title + '</div>' +
            '<div class="sako2-market-data">' +
                '<div class="sako2-market-cell"><span class="sako2-market-cell-label">Açılış</span><span class="sako2-market-cell-val">' + (openStr || '—') + '</span></div>' +
                '<div class="sako2-market-cell"><span class="sako2-market-cell-label">Kapanış</span><span class="sako2-market-cell-val">' + (closeStr || '—') + '</span></div>' +
                '<div class="sako2-market-cell"><span class="sako2-market-cell-label">Para</span><span class="sako2-market-cell-val">' + (amountsStr || '—') + '</span></div>' +
            '</div>' +
        '</div>';
    }

    function fmtAmounts(amounts, keys, labels){
        if(!amounts || !Object.keys(amounts).length) return '—';
        var parts = [];
        for(var i = 0; i < keys.length; i++){
            var v = amounts[keys[i]];
            if(v != null) parts.push(labels[i] + ' ' + fmtVol(v));
        }
        return parts.length ? parts.join('  ') : '—';
    }

    function sumStat(label, value){
        return '<div class="sako-sum-stat"><div class="sako-sum-stat-label">' + label + '</div><div class="sako-sum-stat-value">' + value + '</div></div>';
    }

    function renderDistribution(dist){
        var simple = dist.simple || {};
        var weighted = dist.weighted || {};
        document.getElementById('sako2Distribution').innerHTML =
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
        document.getElementById('sako2Pattern').innerHTML = html;
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
            var mDateStr = '';
            if(m.kickoff){
                try {
                    var md = new Date(m.kickoff);
                    if(!isNaN(md.getTime())) mDateStr = ' — ' + md.toLocaleDateString('tr-TR', {day:'2-digit',month:'short',year:'numeric'});
                } catch(e){}
            }
            html += '<div><div class="sako-mc-name">' + esc(m.match_name) + '</div><div class="sako-mc-league">' + esc(m.league) + mDateStr + '</div></div>';
            html += '<div class="sako-mc-score">';
            html += '<span class="sako-mc-result ' + resultCls + '">' + resultLabel + '</span>';
            html += '<div class="sako-mc-score-bar"><div class="sako-mc-score-fill" style="width:' + scorePct + '%"></div></div>';
            html += '<span class="sako-mc-score-val">' + scorePct + '%</span>';
            html += '</div></div>';

            html += '<div class="sako-mc-info-row">';
            html += fmtOddsCompact('1X2', m.opening_odds, m.closing_odds, ['home','draw','away'], ['1','X','2']);
            html += fmtAmountsCompact('1X2 ₺', m.closing_amounts, ['home','draw','away'], ['1','X','2']);
            html += '</div>';
            html += '<div class="sako-mc-info-row">';
            html += fmtOddsCompact('ÜA 2.5', m.ou25_opening, m.ou25_closing, ['over','under'], ['Ü','A']);
            html += fmtAmountsCompact('ÜA ₺', m.ou25_closing_amounts, ['over','under'], ['Ü','A']);
            html += fmtOddsCompact('KG', m.btts_opening, m.btts_closing, ['yes','no'], ['E','H']);
            html += fmtAmountsCompact('KG ₺', m.btts_closing_amounts, ['yes','no'], ['E','H']);
            html += '</div>';
            html += '<div class="sako-mc-info-row">';
            html += '<div class="sako-mc-info-item"><span class="sako-mc-info-label">Hacim</span><span class="sako-mc-info-val">' + fmtVol(m.total_volume) + '</span></div>';
            html += '</div>';

            html += '<div class="sako-mc-detail" id="sako2Detail' + idx + '">';
            html += '<div class="sako-mc-blocks">';
            html += '<div><div class="sako-mc-block-group-title">En Çok Benzeyen</div>';
            (m.top_3_similar_blocks || []).forEach(function(b){
                html += '<div class="sako-mc-block-item"><span>' + esc(b.label) + '</span><span class="sako-mc-block-score">' + (b.score * 100).toFixed(0) + '%</span></div>';
            });
            html += '</div>';
            html += '<div><div class="sako-mc-block-group-title">En Çok Ayrışan</div>';
            (m.top_2_divergent_blocks || []).forEach(function(b){
                html += '<div class="sako-mc-block-item"><span>' + esc(b.label) + '</span><span class="sako-mc-block-score" style="color:#EF4444">' + (b.score * 100).toFixed(0) + '%</span></div>';
            });
            html += '</div>';
            html += '</div>';

            if(m.block_scores){
                html += '<div class="sako2-block-bars">';
                var blockLabels = {'odds_1x2':'1X2 Oranları','odds_ou':'ÜA 2.5 Oranları','odds_kg':'KG Oranları','money_distribution':'Para Dağılımı','total_volume':'Hacim'};
                for(var bk in blockLabels){
                    if(m.block_scores[bk] != null){
                        var bpct = (m.block_scores[bk] * 100).toFixed(0);
                        html += '<div class="sako2-block-bar-item">';
                        html += '<span class="sako2-block-bar-label">' + blockLabels[bk] + '</span>';
                        html += '<div class="sako2-block-bar-track"><div class="sako2-block-bar-fill" style="width:' + bpct + '%"></div></div>';
                        html += '<span class="sako2-block-bar-val">' + bpct + '%</span>';
                        html += '</div>';
                    }
                }
                html += '</div>';
            }

            html += '</div>';

            html += '<div class="sako-mc-toggle"><button class="sako-mc-toggle-btn" onclick="toggleSako2Detail(' + idx + ', this)">Detay Göster ▼</button></div>';
            html += '</div>';
        });

        document.getElementById('sako2Matches').innerHTML = html || '<div class="sako-dd-empty">Benzer maç bulunamadı</div>';
    }

    window.toggleSako2Detail = function(idx, btn){
        var el = document.getElementById('sako2Detail' + idx);
        if(el.classList.contains('open')){
            el.classList.remove('open');
            btn.textContent = 'Detay Göster ▼';
        } else {
            el.classList.add('open');
            btn.textContent = 'Detay Gizle ▲';
        }
    };

    function fmtAmountsCompact(title, amounts, keys, labels){
        if(!amounts || !Object.keys(amounts).length) return '';
        var parts = [];
        for(var i = 0; i < keys.length; i++){
            var v = amounts[keys[i]];
            if(v != null) parts.push(labels[i] + ' ' + fmtVol(v));
        }
        if(!parts.length) return '';
        return '<div class="sako-mc-info-item"><span class="sako-mc-info-label">' + title + '</span><span class="sako-mc-info-val">' + parts.join('  ') + '</span></div>';
    }

    function fmtOddsCompact(title, opening, closing, keys, labels){
        if(!opening || !Object.keys(opening).length) return '<div class="sako-mc-info-item"><span class="sako-mc-info-label">' + title + '</span><span class="sako-mc-info-val">—</span></div>';
        var parts = [];
        for(var i = 0; i < keys.length; i++){
            var k = keys[i];
            var op = (opening[k] != null) ? fmtOdds(opening[k]) : '—';
            var cl = (closing && closing[k] != null) ? fmtOdds(closing[k]) : null;
            parts.push(labels[i] + ' ' + op + (cl ? '→' + cl : ''));
        }
        return '<div class="sako-mc-info-item"><span class="sako-mc-info-label">' + title + '</span><span class="sako-mc-info-val">' + parts.join('  ') + '</span></div>';
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
