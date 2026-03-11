import re
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from smartxflow_similarity.parser_layer import build_canonical_match
from smartxflow_similarity.feature_store import build_feature_entry, load_store, save_store

MONTH_MAP = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def convert_short_date(date_str, year="2026"):
    m = re.match(r"(\d{1,2})\.(\w{3})\s+(\d{2}:\d{2}:\d{2})", date_str.strip())
    if m:
        day, mon, time = m.groups()
        month_num = MONTH_MAP.get(mon)
        if month_num:
            return f"{year}-{month_num}-{day.zfill(2)}T{time}+03:00"
    return date_str


TABLE_MAP = {
    "MONEYWAY_1X2": "moneyway_1x2_history",
    "MONEYWAY_OU25": "moneyway_ou25_history",
    "MONEYWAY_BTTS": "moneyway_btts_history",
    "DROPPING_1X2": "dropping_1x2_history",
    "DROPPING_OU25": "dropping_ou25_history",
    "DROPPING_BTTS": "dropping_btts_history",
}

ALL_TABLES = list(TABLE_MAP.values())


def parse_value(val):
    val = val.strip()
    if val.startswith("£"):
        val = val[1:].strip().replace(" ", "").replace(",", "")
    val = val.replace("%", "").strip()
    if not val or val == "-":
        return None
    return val


def parse_snapshot_line(line, table_key):
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        return None

    timestamp = parts[0].strip()
    row = {"scraped_at": timestamp}

    for part in parts[1:]:
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip()
        val = parse_value(val)
        row[key] = val

    return row


def parse_txt_file(filepath):
    matches = {}
    current_match = None
    current_table = None
    in_data = False

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            m = re.match(r"^MAC:\s*(.+?)\s*vs\s*(.+)$", line.strip())
            if m:
                current_match = {
                    "home": m.group(1).strip(),
                    "away": m.group(2).strip(),
                    "league": "",
                    "date": "",
                    "match_id_hash": "",
                    "tables": {t: [] for t in ALL_TABLES},
                }
                current_table = None
                in_data = False
                continue

            if current_match is None:
                continue

            m = re.match(r"^LIG:\s*(.+)$", line.strip())
            if m:
                current_match["league"] = m.group(1).strip()
                continue

            m = re.match(r"^TARIH:\s*(.+)$", line.strip())
            if m:
                raw_date = m.group(1).strip()
                current_match["date"] = convert_short_date(raw_date)
                continue

            m = re.match(r"^ID:\s*(\S+)", line.strip())
            if m:
                current_match["match_id_hash"] = m.group(1).strip()
                mid = current_match["match_id_hash"]
                if mid not in matches:
                    matches[mid] = current_match
                else:
                    current_match = matches[mid]
                continue

            m = re.match(r"^\s*\[(\w+)\]\s*\((\d+)\s*snapshot\)", line)
            if m:
                table_key = m.group(1).upper()
                table_name = TABLE_MAP.get(table_key)
                if table_name:
                    current_table = table_name
                    in_data = False
                else:
                    current_table = None
                continue

            if "----" in line:
                if current_table:
                    in_data = True
                continue

            if re.match(r"^={5,}", line.strip()):
                if current_match and current_match.get("match_id_hash"):
                    mid = current_match["match_id_hash"]
                    if mid not in matches:
                        matches[mid] = current_match
                current_match = None
                current_table = None
                in_data = False
                continue

            if in_data and current_table and line.strip():
                row = parse_snapshot_line(line.strip(), current_table)
                if row:
                    row["league"] = current_match["league"]
                    row["home"] = current_match["home"]
                    row["away"] = current_match["away"]
                    row["date"] = current_match["date"]
                    row["match_id_hash"] = current_match["match_id_hash"]
                    current_match["tables"][current_table].append(row)

    return matches


def build_store_from_txt(txt_files, output_path, append=False):
    existing = []
    existing_hashes = set()
    if append and os.path.exists(output_path):
        existing = load_store(output_path)
        for e in existing:
            if e.get("match_id_hash"):
                existing_hashes.add(e["match_id_hash"])

    all_matches = {}
    for fp in txt_files:
        print(f"[TXT Parser] Parsing {fp}...")
        parsed = parse_txt_file(fp)
        print(f"[TXT Parser]   Found {len(parsed)} matches")
        for mid, mdata in parsed.items():
            if mid in all_matches:
                for t in ALL_TABLES:
                    all_matches[mid]["tables"][t].extend(mdata["tables"].get(t, []))
            else:
                all_matches[mid] = mdata

    new_entries = []
    skipped = 0
    errors = 0
    for mid, mdata in all_matches.items():
        if mid in existing_hashes:
            skipped += 1
            continue
        try:
            table_rows = mdata["tables"]
            total = sum(len(v) for v in table_rows.values())
            if total < 5:
                skipped += 1
                continue

            canonical = build_canonical_match(table_rows)
            entry = build_feature_entry(canonical)
            new_entries.append(entry)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"[TXT Parser] Error processing {mid} ({mdata.get('home', '?')} vs {mdata.get('away', '?')}): {e}")

    all_entries = existing + new_entries

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_store(all_entries, output_path)

    print(f"[TXT Parser] Done: {len(new_entries)} new, {skipped} skipped, {errors} errors")
    print(f"[TXT Parser] Total store: {len(all_entries)} entries -> {output_path}")
    return len(new_entries)


if __name__ == "__main__":
    store_path = os.path.join(os.path.dirname(__file__), "data", "feature_store.jsonl")

    txt_files = []
    for arg in sys.argv[1:]:
        if os.path.exists(arg):
            txt_files.append(arg)

    if not txt_files:
        base = os.path.join(os.path.dirname(__file__), "..")
        for f in ["march9_all_data.txt", "march10_all_data.txt"]:
            fp = os.path.join(base, f)
            if os.path.exists(fp):
                txt_files.append(fp)

    if not txt_files:
        print("No TXT files found")
        sys.exit(1)

    build_store_from_txt(txt_files, store_path, append=True)
