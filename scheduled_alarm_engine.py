#!/usr/bin/env python3
"""
SmartXFlow Scheduled Alarm Engine
Runs alarm_calculator.py on Replit as a scheduled job
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_standalone.alarm_calculator import AlarmCalculator

def main():
    print("=" * 60)
    print("SmartXFlow Alarm Engine - Scheduled Run")
    print("=" * 60)
    
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')
    
    if not supabase_url or not supabase_key:
        print("[ERROR] SUPABASE_URL or SUPABASE_ANON_KEY not set")
        sys.exit(1)
    
    print(f"[Config] Supabase URL: {supabase_url[:50]}...")
    print(f"[Config] Supabase Key: {supabase_key[:20]}...")
    
    def logger(msg):
        print(msg)
    
    try:
        calculator = AlarmCalculator(supabase_url, supabase_key, logger_callback=logger)
        total_alarms = calculator.run_all_calculations()
        print("=" * 60)
        print(f"Completed: {total_alarms} total alarms calculated")
        print("=" * 60)
    except Exception as e:
        print(f"[ERROR] Alarm calculation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
