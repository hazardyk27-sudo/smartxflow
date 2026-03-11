#!/usr/bin/env python3
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from smartxflow_similarity.feature_store import load_store, build_feature_entry
from smartxflow_similarity.engine_layer import run_engine


def print_section(title, char="="):
    width = 70
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def format_pct(val):
    return f"{val:.1f}%" if val else "0.0%"


def main():
    if len(sys.argv) < 3:
        print("Kullanım: python run_similarity.py <feature_store.jsonl> <query_entry.json>")
        print("  feature_store.jsonl: Geçmiş maçların feature store dosyası")
        print("  query_entry.json:    Yeni maçın feature entry dosyası")
        sys.exit(1)

    store_path = sys.argv[1]
    query_path = sys.argv[2]

    store_entries = load_store(store_path)
    if not store_entries:
        print(f"HATA: Feature store boş veya bulunamadı: {store_path}")
        sys.exit(1)

    with open(query_path, "r", encoding="utf-8") as f:
        query_entry = json.load(f)

    print(f"\nFeature store: {len(store_entries)} maç yüklendi")

    result = run_engine(query_entry, store_entries)

    print_section("BÖLÜM 1 — YENİ MAÇ ÖZETİ")
    qs = result["query_summary"]
    print(f"  Maç:          {qs.get('match_name', '?')}")
    print(f"  Lig:          {qs.get('league', '?')}")
    print(f"  Toplam Hacim: {qs.get('total_volume', '?')}")
    print(f"  Açılış Odds:  {qs.get('opening_odds', {})}")
    print(f"  Kapanış Odds: {qs.get('closing_odds', {})}")
    dr = qs.get("draw_regime", {})
    print(f"  Draw Regime:  {'EVET' if dr.get('is_draw_regime') else 'HAYIR'} (skor: {dr.get('draw_regime_score', 0)})")
    ts = qs.get("timing_signature", {})
    print(f"  Baskı Zamanı: {ts.get('dominant_timing', '?')}")

    print_section("BÖLÜM 2 — EN BENZER MAÇLAR")
    matches = result["similar_matches"]
    if not matches:
        print("  Benzer maç bulunamadı.")
    for i, m in enumerate(matches, 1):
        print(f"\n  #{i} — {m['match_name']} ({m['league']})")
        print(f"     Similarity: {m['similarity_score']:.4f}")
        print(f"     Sonuç:      {m.get('result', '?')}")
        print(f"     Pattern:    {m.get('pattern_label', '?')}")
        if m.get("top_3_similar_blocks"):
            print(f"     Benzeyen bloklar:")
            for b in m["top_3_similar_blocks"]:
                print(f"       • {b['label']}: {b['score']:.4f}")
        if m.get("top_2_divergent_blocks"):
            print(f"     Ayrışan bloklar:")
            for b in m["top_2_divergent_blocks"]:
                print(f"       • {b['label']}: {b['score']:.4f}")
        if m.get("closest_phases"):
            print(f"     En yakın fazlar:  {', '.join(m['closest_phases'])}")
        if m.get("farthest_phases"):
            print(f"     En farklı fazlar: {', '.join(m['farthest_phases'])}")

    print_section("BÖLÜM 3 — SONUÇ DAĞILIMI")
    dist = result["result_distribution"]
    simple = dist.get("simple", {})
    weighted = dist.get("weighted", {})
    print(f"\n  Simple Distribution ({simple.get('total', 0)} maç):")
    print(f"    Ev:        {format_pct(simple.get('home', 0))}")
    print(f"    Beraberlik:{format_pct(simple.get('draw', 0))}")
    print(f"    Deplasman: {format_pct(simple.get('away', 0))}")
    print(f"\n  Weighted Distribution:")
    print(f"    Ev:        {format_pct(weighted.get('home', 0))}")
    print(f"    Beraberlik:{format_pct(weighted.get('draw', 0))}")
    print(f"    Deplasman: {format_pct(weighted.get('away', 0))}")

    print_section("BÖLÜM 4 — PATTERN SUMMARY")
    overall = result["overall_explainability"]
    print(f"\n  Ana Pattern: {overall.get('main_pattern_label', '?')}")

    if overall.get("top_3_common_traits"):
        print(f"\n  Ortak Özellikler:")
        for t in overall["top_3_common_traits"]:
            print(f"    • {t['trait']} (avg: {t['avg_score']:.4f})")

    if overall.get("top_2_risk_traits"):
        print(f"\n  Risk Faktörleri:")
        for t in overall["top_2_risk_traits"]:
            print(f"    • {t['risk']} (divergence: {t['avg_divergence']:.4f})")

    print(f"\n  Draw Riski:           {'EVET' if overall.get('draw_risk') else 'HAYIR'}")
    print(f"  Market Contradiction: {'EVET' if overall.get('market_contradiction') else 'HAYIR'}")

    if overall.get("top_shared_patterns"):
        print(f"\n  En Yaygın Patternler:")
        for p in overall["top_shared_patterns"]:
            print(f"    • {p['pattern']} ({p['count']}x)")

    if overall.get("top_mismatch_patterns"):
        print(f"\n  Uyarılar:")
        for p in overall["top_mismatch_patterns"]:
            print(f"    ⚠ {p}")

    print(f"\n{'=' * 70}")
    print(f"  Toplam taranan: {result['candidates_checked']} maç | Bulunan: {result['matches_found']} benzer maç")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
