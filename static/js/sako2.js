(function(){
    var matches = [];
    var searchInput = document.getElementById('sako2SearchInput');
    var dropdown = document.getElementById('sako2Dropdown');
    var clearBtn = document.getElementById('sako2SearchClear');
    var resultsEl = document.getElementById('sako2Results');
    var loadingEl = document.getElementById('sako2Loading');
    var emptyEl = document.getElementById('sako2Empty');
    var debounceTimer = null;
    var selectedMarket = 'all';
    var lastSelectedHash = null;

    document.querySelectorAll('.s2-mf-btn').forEach(function(btn){
        btn.addEventListener('click', function(){
            document.querySelectorAll('.s2-mf-btn').forEach(function(b){ b.classList.remove('active'); });
            this.classList.add('active');
            selectedMarket = this.getAttribute('data-market');
            if(lastSelectedHash){
                runSimilarity(lastSelectedHash);
            }
        });
    });

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
        lastSelectedHash = hash;
        emptyEl.style.display = 'none';
        resultsEl.style.display = 'none';
        loadingEl.style.display = 'block';

        var url = '/api/sako2/run?match_id_hash=' + encodeURIComponent(hash);
        if(selectedMarket && selectedMarket !== 'all'){
            url += '&market_filter=' + encodeURIComponent(selectedMarket);
        }
        sako2Fetch(url)
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
        renderSummary(data.query_summary, selectedMarket);
        renderDistribution(data.result_distribution);
        renderPattern(data.overall_explainability);
        renderMatches(data.similar_matches, selectedMarket);
        document.getElementById('sako2MatchCount').textContent = data.matches_found || 0;
        resultsEl.style.display = 'block';
    }

    function renderSummary(qs, mf){
        var kickoffStr = '';
        if(qs.kickoff_time){
            try {
                var d = new Date(qs.kickoff_time);
                if(!isNaN(d.getTime())){
                    kickoffStr = d.toLocaleDateString('tr-TR', {day:'2-digit',month:'short',year:'numeric'}) + ' ' + d.toLocaleTimeString('tr-TR', {hour:'2-digit',minute:'2-digit'});
                }
            } catch(e){}
        }

        var rows = '';
        if(!mf || mf === 'all' || mf === '1x2')
            rows += summaryMarketRow('1X2', qs.opening_odds, qs.closing_odds, qs.closing_amounts, ['home','draw','away'], ['1','X','2']);
        if(!mf || mf === 'all' || mf === 'ou25')
            rows += summaryMarketRow('ÜA 2.5', qs.ou25_opening, qs.ou25_closing, qs.ou25_closing_amounts, ['over','under'], ['Ü','A']);
        if(!mf || mf === 'all' || mf === 'kg')
            rows += summaryMarketRow('KG', qs.btts_opening, qs.btts_closing, qs.btts_closing_amounts, ['yes','no'], ['E','H']);

        document.getElementById('sako2Summary').innerHTML =
            '<div class="sako-sum-header">' +
                '<div><div class="sako-sum-name">' + esc(qs.match_name || '?') + '</div>' +
                '<div class="sako-sum-league">' + esc(qs.league || '') + (kickoffStr ? ' — ' + esc(kickoffStr) : '') + '</div></div>' +
                '<div class="s2-vol-badge"><span class="s2-vol-icon">V</span>' + fmtVol(qs.total_volume) + '</div>' +
            '</div>' +
            '<div class="s2-market-table">' +
                '<div class="s2-mt-header"><span class="s2-mt-h-market">Market</span><span class="s2-mt-h-col">Açılış</span><span class="s2-mt-h-col">Kapanış</span><span class="s2-mt-h-col">Hareket</span><span class="s2-mt-h-col">Para</span></div>' +
                rows +
            '</div>';
    }

    function summaryMarketRow(title, opening, closing, amounts, keys, labels){
        opening = opening || {};
        closing = closing || {};
        amounts = amounts || {};
        var cells = '';
        for(var i = 0; i < keys.length; i++){
            var k = keys[i];
            var op = opening[k];
            var cl = closing[k];
            var amt = amounts[k];
            var driftCls = '';
            if(op != null && cl != null){
                if(cl < op - 0.01) driftCls = 'down';
                else if(cl > op + 0.01) driftCls = 'up';
            }
            cells += '<div class="s2-mt-sel">' +
                '<span class="s2-mt-sel-label">' + labels[i] + '</span>' +
                '<span class="s2-mt-sel-val">' + fmtOdds(op) + '</span>' +
                '<span class="s2-mt-sel-val">' + fmtOdds(cl) + '</span>' +
                '<span class="s2-mt-drift ' + driftCls + '">' + fmtDrift(op, cl) + '</span>' +
                '<span class="s2-mt-sel-amt">' + (amt != null ? fmtVol(amt) : '—') + '</span>' +
            '</div>';
        }
        return '<div class="s2-mt-row"><div class="s2-mt-market">' + title + '</div><div class="s2-mt-sels">' + cells + '</div></div>';
    }

    function fmtDrift(op, cl){
        if(op == null || cl == null || op === 0) return '—';
        var pct = ((cl - op) / op * 100);
        var sign = pct > 0 ? '+' : '';
        return sign + pct.toFixed(1) + '%';
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

    function renderMatches(matches, mf){
        var html = '';
        (matches || []).forEach(function(m, idx){
            var resultCls = 'unknown';
            var resultLabel = m.result || '?';
            if(m.result){
                var r = m.result.toUpperCase();
                var scoreStr = m.score ? ' ' + m.score : '';
                if(r === 'HOME' || r === '1' || r === 'H'){ resultCls = 'home'; resultLabel = 'Ev' + scoreStr; }
                else if(r === 'DRAW' || r === 'X' || r === 'D'){ resultCls = 'draw'; resultLabel = 'Beraberlik' + scoreStr; }
                else if(r === 'AWAY' || r === '2' || r === 'A'){ resultCls = 'away'; resultLabel = 'Deplasman' + scoreStr; }
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

            html += '<div class="s2-mc-markets">';
            if(!mf || mf === 'all' || mf === '1x2')
                html += mcMarketRow('1X2', m.opening_odds, m.closing_odds, m.closing_amounts, ['home','draw','away'], ['1','X','2']);
            if(!mf || mf === 'all' || mf === 'ou25')
                html += mcMarketRow('ÜA', m.ou25_opening, m.ou25_closing, m.ou25_closing_amounts, ['over','under'], ['Ü','A']);
            if(!mf || mf === 'all' || mf === 'kg')
                html += mcMarketRow('KG', m.btts_opening, m.btts_closing, m.btts_closing_amounts, ['yes','no'], ['E','H']);
            html += '<div class="s2-mc-vol"><span class="s2-mc-vol-label">Hacim</span><span class="s2-mc-vol-val">' + fmtVol(m.total_volume) + '</span></div>';
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
                var blockLabels = {'odds_1x2':'1X2 Oranları','odds_1x2_drift':'1X2 Oran Değişimi','odds_ou':'ÜA 2.5 Oranları','odds_ou_drift':'ÜA 2.5 Oran Değişimi','odds_kg':'KG Oranları','odds_kg_drift':'KG Oran Değişimi','money_distribution':'Para Dağılımı','total_volume':'Hacim'};
                for(var bk in blockLabels){
                    if(m.block_scores[bk] != null){
                        var bpct = (m.block_scores[bk] * 100).toFixed(0);
                        html += '<div class="sako2-block-bar-item">';
                        html += '<span class="sako2-block-bar-label">' + blockLabels[bk] + '</span>';
                        html += '<div class="sako2-block-bar-track"><div class="sako2-block-bar-fill" style="width:' + bpct + '%"></div></div>';
                        html += '<span class="sako2-block-bar-val">' + bpct + '%</span>';
                        html += '</div>';
                        var detailKey = bk + '_detail';
                        if(m.block_scores[detailKey]){
                            var d = m.block_scores[detailKey];
                            html += '<div class="s2-block-sub">';
                            html += '<span class="s2-block-sub-item">Açılış <b>' + (d.opening * 100).toFixed(0) + '%</b></span>';
                            html += '<span class="s2-block-sub-item">Kapanış <b>' + (d.closing * 100).toFixed(0) + '%</b></span>';
                            html += '<span class="s2-block-sub-item s2-block-sub-drift">Drift <b>' + (d.drift * 100).toFixed(0) + '%</b></span>';
                            html += '</div>';
                        }
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

    function mcMarketRow(title, opening, closing, amounts, keys, labels){
        opening = opening || {};
        closing = closing || {};
        amounts = amounts || {};
        var hasData = false;
        var sels = '';
        for(var i = 0; i < keys.length; i++){
            var k = keys[i];
            var op = opening[k];
            var cl = closing[k];
            var amt = amounts[k];
            if(op != null || cl != null) hasData = true;
            var driftCls = '';
            if(op != null && cl != null){
                if(cl < op - 0.01) driftCls = 'down';
                else if(cl > op + 0.01) driftCls = 'up';
            }
            var driftStr = fmtDrift(op, cl);
            sels += '<div class="s2-mc-sel">' +
                '<span class="s2-mc-sel-lbl">' + labels[i] + '</span>' +
                '<span class="s2-mc-odds">' + fmtOdds(op) + '<span class="s2-mc-arrow ' + driftCls + '">' + (driftCls === 'down' ? '↓' : driftCls === 'up' ? '↑' : '→') + '</span>' + fmtOdds(cl) + '</span>' +
                '<span class="s2-mc-drift-pct ' + driftCls + '">' + driftStr + '</span>' +
                (amt != null ? '<span class="s2-mc-amt">' + fmtVol(amt) + '</span>' : '') +
            '</div>';
        }
        if(!hasData) return '';
        return '<div class="s2-mc-mrow"><span class="s2-mc-mrow-title">' + title + '</span><div class="s2-mc-mrow-sels">' + sels + '</div></div>';
    }

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
