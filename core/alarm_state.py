"""
Alarm State Management - Prevents duplicate alarms for the same movement.

Tracks which alarms have been fired for each match/market/side combination
to avoid re-firing alarms for the same price movement across scrapes.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from core.timezone import now_turkey_iso

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'alarm_state.db')

COOLDOWN_MINUTES = 15
MIN_MONEY_INCREMENT = 5000


def _get_connection():
    """Get SQLite connection for alarm state."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_alarm_state_db():
    """Initialize the alarm_state table if it doesn't exist."""
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS alarm_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                market TEXT NOT NULL,
                side TEXT NOT NULL,
                alarm_type TEXT NOT NULL,
                window_start TEXT,
                window_end TEXT,
                baseline_money REAL DEFAULT 0,
                baseline_odds REAL DEFAULT 0,
                fired_at TEXT NOT NULL,
                UNIQUE(match_id, market, side, alarm_type, window_start)
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_alarm_state_match ON alarm_state(match_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_alarm_state_fired ON alarm_state(fired_at)')
        conn.commit()
    finally:
        conn.close()


def should_fire_alarm(
    match_id: str,
    market: str,
    side: str,
    alarm_type: str,
    current_money: float,
    current_odds: float,
    window_start: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Check if an alarm should be fired based on deduplication rules.
    
    Returns:
        Tuple of (should_fire: bool, reason: str)
    """
    init_alarm_state_db()
    conn = _get_connection()
    try:
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM alarm_state 
            WHERE match_id = ? AND market = ? AND side = ? AND alarm_type = ?
            ORDER BY fired_at DESC
            LIMIT 1
        ''', (match_id, market, side, alarm_type))
        
        last_alarm = cur.fetchone()
        
        if not last_alarm:
            return True, "first_alarm"
        
        last_fired = last_alarm['fired_at']
        last_money = last_alarm['baseline_money'] or 0
        last_window = last_alarm['window_start']
        
        try:
            last_fired_dt = datetime.fromisoformat(last_fired.replace('Z', '+00:00'))
            now_dt = datetime.fromisoformat(now_turkey_iso().replace('Z', '+00:00'))
            time_diff = (now_dt - last_fired_dt).total_seconds() / 60
        except:
            time_diff = 0
        
        if time_diff < COOLDOWN_MINUTES:
            money_increment = current_money - last_money
            
            if money_increment >= MIN_MONEY_INCREMENT:
                return True, f"new_increment_{money_increment:.0f}"
            else:
                return False, f"cooldown_active_{time_diff:.1f}min"
        
        if window_start and window_start == last_window:
            money_increment = current_money - last_money
            if money_increment < MIN_MONEY_INCREMENT:
                return False, "same_window_no_increment"
        
        return True, "cooldown_expired"
        
    finally:
        conn.close()


def record_alarm_fired(
    match_id: str,
    market: str,
    side: str,
    alarm_type: str,
    baseline_money: float,
    baseline_odds: float,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None
):
    """Record that an alarm was fired to prevent duplicates."""
    init_alarm_state_db()
    conn = _get_connection()
    try:
        cur = conn.cursor()
        fired_at = now_turkey_iso()
        
        cur.execute('''
            INSERT OR REPLACE INTO alarm_state 
            (match_id, market, side, alarm_type, window_start, window_end, 
             baseline_money, baseline_odds, fired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (match_id, market, side, alarm_type, window_start, window_end,
              baseline_money, baseline_odds, fired_at))
        
        conn.commit()
    finally:
        conn.close()


def get_last_alarm_state(
    match_id: str,
    market: str,
    side: str,
    alarm_type: str
) -> Optional[Dict[str, Any]]:
    """Get the last alarm state for a specific combination."""
    init_alarm_state_db()
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT * FROM alarm_state 
            WHERE match_id = ? AND market = ? AND side = ? AND alarm_type = ?
            ORDER BY fired_at DESC
            LIMIT 1
        ''', (match_id, market, side, alarm_type))
        
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def cleanup_old_alarm_states(hours: int = 48):
    """Remove alarm states older than specified hours."""
    init_alarm_state_db()
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        cur.execute('DELETE FROM alarm_state WHERE fired_at < ?', (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        if deleted > 0:
            print(f"[AlarmState] Cleaned up {deleted} old alarm states")
    finally:
        conn.close()


def clear_match_alarm_states(match_id: str):
    """Clear all alarm states for a specific match (when match ends)."""
    init_alarm_state_db()
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM alarm_state WHERE match_id = ?', (match_id,))
        conn.commit()
    finally:
        conn.close()
