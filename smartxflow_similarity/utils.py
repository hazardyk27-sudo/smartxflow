import re
import hashlib
from datetime import datetime, timezone


def parse_number(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in ("-", "—", "N/A", "n/a", "null", "None", ""):
        return None
    s = re.sub(r"[£€$¥₺]", "", s).strip()
    s = s.replace("\u00a0", "").replace(" ", "")
    if re.match(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$", s):
        s = s.replace(",", "")
    elif re.match(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def compute_no_vig(odds_list):
    probs = []
    for o in odds_list:
        if o is None or o <= 1.0:
            return None
        probs.append(1.0 / o)
    total = sum(probs)
    if total == 0:
        return None
    return [p / total for p in probs]


def odds_to_implied(odds):
    if odds is None or odds <= 1.0:
        return None
    return 1.0 / odds


def safe_div(a, b, default=0.0):
    if b is None or b == 0:
        return default
    if a is None:
        return default
    return a / b


def match_id_hash(league, home, away):
    raw = f"{league}|{home}|{away}".strip().lower()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def parse_datetime(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    import re
    m = re.match(r'^(\d{1,2})\.(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{2}:\d{2}:\d{2})$', s)
    if m:
        day, mon, time_str = m.groups()
        now = datetime.now()
        try:
            dt = datetime.strptime(f"{day}.{mon}.{now.year} {time_str}", "%d.%b.%Y %H:%M:%S")
            return dt
        except ValueError:
            pass
    return None


def hours_before_kickoff(snapshot_time, kickoff_time):
    if snapshot_time is None or kickoff_time is None:
        return None
    if isinstance(snapshot_time, str):
        snapshot_time = parse_datetime(snapshot_time)
    if isinstance(kickoff_time, str):
        kickoff_time = parse_datetime(kickoff_time)
    if snapshot_time is None or kickoff_time is None:
        return None
    if snapshot_time.tzinfo is None and kickoff_time.tzinfo is not None:
        snapshot_time = snapshot_time.replace(tzinfo=kickoff_time.tzinfo)
    elif kickoff_time.tzinfo is None and snapshot_time.tzinfo is not None:
        kickoff_time = kickoff_time.replace(tzinfo=snapshot_time.tzinfo)
    diff = (kickoff_time - snapshot_time).total_seconds() / 3600.0
    return max(diff, 0.0)


def clamp(val, min_val=0.0, max_val=1.0):
    if val is None:
        return min_val
    return max(min_val, min(max_val, val))


def normalize_0_1(val, min_val, max_val):
    if val is None:
        return 0.0
    if max_val == min_val:
        return 0.5
    return clamp((val - min_val) / (max_val - min_val))


def is_placeholder_odds(odds_val):
    if odds_val is None:
        return True
    return odds_val <= 1.001 or odds_val > 100.0
