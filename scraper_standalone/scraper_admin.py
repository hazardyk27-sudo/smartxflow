"""
SmartXFlow Monitor - Admin Panel + Scraper + Alarm Settings
Ana ekran: Admin Panel (ayarlar, durum, alarm config)
Ek pencere: Scraper konsolu
"""

import os
import sys
import json
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import requests

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

VERSION = "1.04"
CONFIG_FILE = "config.json"

ALARM_TYPES = [
    ('sharp', 'Sharp'),
    ('publicmove', 'Public Move'),
    ('insider', 'Insider'),
    ('bigmoney', 'Big Money'),
    ('dropping', 'Dropping'),
    ('volumeshock', 'Hacim Şoku'),
    ('volumeleader', 'Hacim Lideri')
]

ALARM_CONFIG_FIELDS = {
    'sharp': [
        ('min_sharp_score', 'Min Sharp Skor', 100),
        ('min_volume_1x2', 'Min Hacim 1X2', 3000),
        ('min_volume_ou25', 'Min Hacim O/U', 1000),
        ('min_volume_btts', 'Min Hacim BTTS', 500),
        ('volume_multiplier', 'Hacim Çarpanı', 1),
        ('min_amount_change', 'Min Para Değişimi', 500),
    ],
    'publicmove': [
        ('min_sharp_score', 'Min Trap Skor', 70),
        ('min_volume_1x2', 'Min Hacim 1X2', 3000),
        ('min_volume_ou25', 'Min Hacim O/U', 1000),
        ('min_volume_btts', 'Min Hacim BTTS', 500),
    ],
    'insider': [
        ('insider_hacim_sok_esigi', 'Hacim Şok Eşiği', 5),
        ('insider_oran_dusus_esigi', 'Oran Düşüş %', 3),
        ('insider_sure_dakika', 'Süre (dk)', 60),
        ('insider_max_para', 'Max Para', 5000),
    ],
    'bigmoney': [
        ('big_money_limit', 'Big Money Limiti (£)', 15000),
    ],
    'dropping': [
        ('min_drop_l1', 'L1 Min %', 10),
        ('max_drop_l1', 'L1 Max %', 17),
        ('min_drop_l2', 'L2 Min %', 17),
        ('max_drop_l2', 'L2 Max %', 20),
        ('min_drop_l3', 'L3 Min %', 20),
    ],
    'volumeshock': [
        ('volume_shock_multiplier', 'Şok Çarpanı', 5),
        ('min_hours_to_kickoff', 'Min Saat', 3),
    ],
    'volumeleader': [
        ('leader_threshold', 'Lider Eşiği %', 50),
        ('min_volume_1x2', 'Min Hacim 1X2', 2000),
        ('min_volume_ou25', 'Min Hacim O/U', 1000),
        ('min_volume_btts', 'Min Hacim BTTS', 500),
    ],
}

ALARM_TABLES = {
    'sharp': 'sharp_alarms',
    'publicmove': 'publicmove_alarms',
    'insider': 'insider_alarms',
    'bigmoney': 'big_money_alarms',
    'dropping': 'dropping_alarms',
    'volumeshock': 'volume_shock_alarms',
    'volumeleader': 'volume_leader_alarms',
}

def get_turkey_now():
    if TURKEY_TZ:
        return datetime.now(TURKEY_TZ)
    return datetime.now()


def get_config_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), CONFIG_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)


def load_config():
    config_path = get_config_path()
    default_config = {
        'SUPABASE_URL': '',
        'SUPABASE_ANON_KEY': '',
        'SCRAPE_INTERVAL_MINUTES': 10
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
                if content.startswith('\ufeff'):
                    content = content[1:]
                config = json.loads(content)
                for key in default_config:
                    if key not in config:
                        config[key] = default_config[key]
                return config
        except Exception as e:
            print(f"Config load error: {e}")
    
    return default_config


def save_config(config):
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Config save error: {e}")
        return False


class SupabaseClient:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
    
    def get_alarm_settings(self):
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/alarm_settings?select=*",
                headers=self.headers,
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"Get alarm settings error: {e}")
            return []
    
    def save_alarm_setting(self, alarm_type, enabled, config):
        try:
            data = {
                'alarm_type': alarm_type,
                'enabled': enabled,
                'config': config
            }
            headers = self.headers.copy()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            
            resp = requests.post(
                f"{self.url}/rest/v1/alarm_settings",
                headers=headers,
                json=data,
                timeout=10
            )
            return resp.status_code in [200, 201]
        except Exception as e:
            print(f"Save alarm setting error: {e}")
            return False
    
    def get_alarms(self, table_name, limit=50):
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/{table_name}?select=*&order=created_at.desc&limit={limit}",
                headers=self.headers,
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"Get alarms error: {e}")
            return []


class ScraperThread(threading.Thread):
    def __init__(self, config, log_queue, status_callback):
        super().__init__(daemon=True)
        self.config = config
        self.log_queue = log_queue
        self.status_callback = status_callback
        self.running = False
        self.paused = False
        self.interval_minutes = config.get('SCRAPE_INTERVAL_MINUTES', 10)
        self.last_scrape_time = None
        self.next_scrape_time = None
        self.total_scrapes = 0
        self.total_rows = 0
    
    def log(self, msg):
        timestamp = get_turkey_now().strftime('%H:%M:%S')
        self.log_queue.put(f"[{timestamp}] {msg}")
    
    def run(self):
        self.running = True
        self.log("Scraper thread baslatildi")
        
        try:
            from standalone_scraper import SupabaseWriter, run_scrape, SCRAPE_INTERVAL_MINUTES
            from alarm_calculator import AlarmCalculator
        except ImportError as e:
            self.log(f"Import hatasi: {e}")
            self.running = False
            return
        
        try:
            writer = SupabaseWriter(
                self.config['SUPABASE_URL'], 
                self.config['SUPABASE_ANON_KEY']
            )
            self.log("Supabase baglantisi hazir")
        except Exception as e:
            self.log(f"Supabase baglanti hatasi: {e}")
            self.running = False
            return
        
        while self.running:
            if not self.paused:
                self.status_callback('scraping')
                self.log("Scrape basladi...")
                
                try:
                    from standalone_scraper import run_scrape as do_scrape
                    rows = do_scrape(writer)
                    self.total_rows += rows
                    self.total_scrapes += 1
                    self.last_scrape_time = get_turkey_now()
                    self.log(f"Scrape tamamlandi - {rows} satir")
                except Exception as e:
                    self.log(f"Scrape hatasi: {e}")
                
                self.status_callback('calculating')
                
                try:
                    calculator = AlarmCalculator(
                        self.config['SUPABASE_URL'],
                        self.config['SUPABASE_ANON_KEY'],
                        logger_callback=self.log
                    )
                    calculator.run_all_calculations()
                except Exception as e:
                    self.log(f"Alarm hesaplama hatasi: {e}")
                
                self.next_scrape_time = get_turkey_now()
                wait_seconds = self.interval_minutes * 60
                self.status_callback('waiting')
                self.log(f"{self.interval_minutes} dakika bekleniyor...")
                
                for i in range(wait_seconds):
                    if not self.running:
                        break
                    if self.paused:
                        break
                    time.sleep(1)
            else:
                self.status_callback('paused')
                time.sleep(1)
        
        self.log("Scraper thread durduruldu")
        self.status_callback('stopped')
    
    def stop(self):
        self.running = False
    
    def pause(self):
        self.paused = True
    
    def resume(self):
        self.paused = False
    
    def set_interval(self, minutes):
        self.interval_minutes = minutes


class ScraperConsoleWindow(tk.Toplevel):
    def __init__(self, parent, log_queue):
        super().__init__(parent)
        self.title("SmartXFlow Scraper Console")
        self.geometry("700x500")
        self.configure(bg='#1e1e1e')
        
        self.log_queue = log_queue
        
        self.console = scrolledtext.ScrolledText(
            self,
            wrap=tk.WORD,
            bg='#1e1e1e',
            fg='#00ff00',
            font=('Consolas', 10),
            insertbackground='#00ff00'
        )
        self.console.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.console.tag_configure('error', foreground='#ff6b6b')
        self.console.tag_configure('success', foreground='#51cf66')
        self.console.tag_configure('info', foreground='#74c0fc')
        
        self.update_console()
    
    def update_console(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.console.insert(tk.END, msg + '\n')
                self.console.see(tk.END)
        except queue.Empty:
            pass
        
        self.after(100, self.update_console)
    
    def add_log(self, msg):
        self.console.insert(tk.END, msg + '\n')
        self.console.see(tk.END)


class AlarmSettingsTab(ttk.Frame):
    def __init__(self, parent, alarm_type, alarm_name, config_fields, get_supabase_client):
        super().__init__(parent)
        self.alarm_type = alarm_type
        self.alarm_name = alarm_name
        self.config_fields = config_fields
        self.get_supabase_client = get_supabase_client
        self.field_vars = {}
        self.enabled_var = tk.BooleanVar(value=True)
        
        self.create_widgets()
    
    def create_widgets(self):
        config_frame = ttk.LabelFrame(self, text=f" {self.alarm_name} Ayarları ", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        enabled_cb = ttk.Checkbutton(config_frame, text="Aktif", variable=self.enabled_var)
        enabled_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        for idx, (field_key, field_label, default_value) in enumerate(self.config_fields):
            ttk.Label(config_frame, text=f"{field_label}:").grid(row=idx+1, column=0, sticky=tk.W, pady=3, padx=5)
            
            var = tk.StringVar(value=str(default_value))
            self.field_vars[field_key] = var
            
            entry = ttk.Entry(config_frame, textvariable=var, width=15)
            entry.grid(row=idx+1, column=1, sticky=tk.W, pady=3, padx=5)
        
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=len(self.config_fields)+1, column=0, columnspan=2, pady=10)
        
        save_btn = ttk.Button(btn_frame, text="💾 Kaydet", command=self.save_config)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        refresh_btn = ttk.Button(btn_frame, text="🔄 Yenile", command=self.load_config)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(config_frame, text="")
        self.status_label.grid(row=len(self.config_fields)+2, column=0, columnspan=2, pady=5)
        
        alarms_frame = ttk.LabelFrame(self, text=f" {self.alarm_name} Alarmları ", padding=10)
        alarms_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ('home', 'away', 'market', 'score', 'time')
        self.alarms_tree = ttk.Treeview(alarms_frame, columns=columns, show='headings', height=8)
        
        self.alarms_tree.heading('home', text='Ev Sahibi')
        self.alarms_tree.heading('away', text='Deplasman')
        self.alarms_tree.heading('market', text='Market')
        self.alarms_tree.heading('score', text='Skor')
        self.alarms_tree.heading('time', text='Zaman')
        
        self.alarms_tree.column('home', width=120)
        self.alarms_tree.column('away', width=120)
        self.alarms_tree.column('market', width=80)
        self.alarms_tree.column('score', width=60)
        self.alarms_tree.column('time', width=100)
        
        scrollbar = ttk.Scrollbar(alarms_frame, orient=tk.VERTICAL, command=self.alarms_tree.yview)
        self.alarms_tree.configure(yscrollcommand=scrollbar.set)
        
        self.alarms_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        refresh_alarms_btn = ttk.Button(self, text="🔄 Alarmları Yenile", command=self.load_alarms)
        refresh_alarms_btn.pack(pady=5)
        
        self.alarm_count_label = ttk.Label(self, text="Toplam: 0 alarm")
        self.alarm_count_label.pack(pady=5)
    
    def load_config(self):
        client = self.get_supabase_client()
        if not client:
            self.status_label.config(text="❌ Supabase bağlantısı yok")
            return
        
        self.status_label.config(text="Yükleniyor...")
        self.update()
        
        def do_load():
            settings = client.get_alarm_settings()
            for setting in settings:
                if setting.get('alarm_type') == self.alarm_type:
                    self.enabled_var.set(setting.get('enabled', True))
                    config = setting.get('config', {})
                    for field_key, var in self.field_vars.items():
                        if field_key in config:
                            var.set(str(config[field_key]))
                    self.after(0, lambda: self.status_label.config(text="✅ Yüklendi"))
                    return
            self.after(0, lambda: self.status_label.config(text="ℹ️ Varsayılan ayarlar"))
        
        threading.Thread(target=do_load, daemon=True).start()
    
    def save_config(self):
        client = self.get_supabase_client()
        if not client:
            self.status_label.config(text="❌ Supabase bağlantısı yok")
            return
        
        self.status_label.config(text="Kaydediliyor...")
        self.update()
        
        config = {}
        for field_key, var in self.field_vars.items():
            try:
                val = var.get()
                if '.' in val:
                    config[field_key] = float(val)
                else:
                    config[field_key] = int(val)
            except ValueError:
                config[field_key] = var.get()
        
        def do_save():
            success = client.save_alarm_setting(self.alarm_type, self.enabled_var.get(), config)
            if success:
                self.after(0, lambda: self.status_label.config(text="✅ Kaydedildi!"))
            else:
                self.after(0, lambda: self.status_label.config(text="❌ Kaydetme hatası"))
        
        threading.Thread(target=do_save, daemon=True).start()
    
    def load_alarms(self):
        client = self.get_supabase_client()
        if not client:
            return
        
        self.alarm_count_label.config(text="Yükleniyor...")
        self.update()
        
        def do_load():
            table = ALARM_TABLES.get(self.alarm_type, f"{self.alarm_type}_alarms")
            alarms = client.get_alarms(table, limit=50)
            
            self.after(0, lambda: self._populate_alarms(alarms))
        
        threading.Thread(target=do_load, daemon=True).start()
    
    def _populate_alarms(self, alarms):
        for item in self.alarms_tree.get_children():
            self.alarms_tree.delete(item)
        
        for alarm in alarms:
            home = alarm.get('home', alarm.get('home_team', ''))[:15]
            away = alarm.get('away', alarm.get('away_team', ''))[:15]
            market = alarm.get('market', '')
            
            if self.alarm_type == 'sharp':
                score = alarm.get('sharp_score', alarm.get('score', 0))
            elif self.alarm_type == 'publicmove':
                score = alarm.get('trap_score', alarm.get('sharp_score', 0))
            elif self.alarm_type == 'bigmoney':
                score = alarm.get('volume', 0)
            elif self.alarm_type == 'dropping':
                score = f"{alarm.get('drop_pct', 0)}%"
            elif self.alarm_type == 'volumeshock':
                score = f"{alarm.get('shock_multiplier', 0)}x"
            elif self.alarm_type == 'volumeleader':
                score = alarm.get('new_leader', '')
            else:
                score = alarm.get('score', 0)
            
            event_time = alarm.get('event_time', alarm.get('created_at', ''))
            if event_time and 'T' in str(event_time):
                try:
                    event_time = event_time.split('T')[1][:5]
                except:
                    pass
            
            self.alarms_tree.insert('', tk.END, values=(home, away, market, score, event_time))
        
        self.alarm_count_label.config(text=f"Toplam: {len(alarms)} alarm")


class AdminPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title(f"SmartXFlow Admin Panel v{VERSION}")
        self.geometry("800x900")
        self.configure(bg='#2d2d2d')
        
        self.config = load_config()
        self.log_queue = queue.Queue()
        self.scraper_thread = None
        self.console_window = None
        self.supabase_client = None
        self.alarm_tabs = {}
        
        self.setup_styles()
        self.create_widgets()
        self.update_status_display()
        
        self.after(500, self.load_all_alarm_settings)
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('TFrame', background='#2d2d2d')
        style.configure('TLabel', background='#2d2d2d', foreground='#ffffff', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'), foreground='#4fc3f7')
        style.configure('Status.TLabel', font=('Segoe UI', 11))
        style.configure('TEntry', font=('Segoe UI', 10))
        style.configure('TSpinbox', font=('Segoe UI', 10))
        style.configure('TNotebook', background='#2d2d2d')
        style.configure('TNotebook.Tab', font=('Segoe UI', 9), padding=[10, 5])
    
    def get_supabase_client(self):
        url = self.url_entry.get().strip()
        key = self.key_entry.get().strip()
        
        if not url or not key:
            return None
        
        if not self.supabase_client or self.supabase_client.url != url:
            self.supabase_client = SupabaseClient(url, key)
        
        return self.supabase_client
    
    def create_widgets(self):
        main_notebook = ttk.Notebook(self)
        main_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scraper_tab = ttk.Frame(main_notebook)
        main_notebook.add(scraper_tab, text="🔧 Scraper")
        self.create_scraper_tab(scraper_tab)
        
        alarms_tab = ttk.Frame(main_notebook)
        main_notebook.add(alarms_tab, text="🔔 Alarm Ayarları")
        self.create_alarms_tab(alarms_tab)
    
    def create_scraper_tab(self, parent):
        main_frame = ttk.Frame(parent, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        header = ttk.Label(main_frame, text="SmartXFlow Scraper", style='Header.TLabel')
        header.pack(pady=(0, 20))
        
        config_frame = ttk.LabelFrame(main_frame, text=" Supabase Ayarları ", padding=15)
        config_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(config_frame, text="Supabase URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(config_frame, width=50)
        self.url_entry.insert(0, self.config.get('SUPABASE_URL', ''))
        self.url_entry.grid(row=0, column=1, pady=5, padx=5)
        
        ttk.Label(config_frame, text="Supabase Key:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.key_entry = ttk.Entry(config_frame, width=50, show='*')
        self.key_entry.insert(0, self.config.get('SUPABASE_ANON_KEY', ''))
        self.key_entry.grid(row=1, column=1, pady=5, padx=5)
        
        scrape_frame = ttk.LabelFrame(main_frame, text=" Scrape Ayarları ", padding=15)
        scrape_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(scrape_frame, text="Scrape Aralığı (dakika):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.interval_var = tk.IntVar(value=self.config.get('SCRAPE_INTERVAL_MINUTES', 10))
        self.interval_spin = ttk.Spinbox(
            scrape_frame, 
            from_=1, 
            to=60, 
            width=10,
            textvariable=self.interval_var
        )
        self.interval_spin.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        save_btn = ttk.Button(scrape_frame, text="💾 Ayarları Kaydet", command=self.save_settings)
        save_btn.grid(row=1, column=0, columnspan=2, pady=10)
        
        status_frame = ttk.LabelFrame(main_frame, text=" Durum ", padding=15)
        status_frame.pack(fill=tk.X, pady=10)
        
        self.status_label = ttk.Label(status_frame, text="Durum: Durduruldu", style='Status.TLabel')
        self.status_label.pack(anchor=tk.W, pady=2)
        
        self.last_scrape_label = ttk.Label(status_frame, text="Son Scrape: -")
        self.last_scrape_label.pack(anchor=tk.W, pady=2)
        
        self.total_scrapes_label = ttk.Label(status_frame, text="Toplam Scrape: 0")
        self.total_scrapes_label.pack(anchor=tk.W, pady=2)
        
        self.total_rows_label = ttk.Label(status_frame, text="Toplam Satır: 0")
        self.total_rows_label.pack(anchor=tk.W, pady=2)
        
        control_frame = ttk.LabelFrame(main_frame, text=" Kontroller ", padding=15)
        control_frame.pack(fill=tk.X, pady=10)
        
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ Başlat", command=self.start_scraper, width=15)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.pause_btn = ttk.Button(btn_frame, text="⏸ Duraklat", command=self.pause_scraper, width=15, state=tk.DISABLED)
        self.pause_btn.grid(row=0, column=1, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ Durdur", command=self.stop_scraper, width=15, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=2, padx=5)
        
        console_btn = ttk.Button(control_frame, text="📋 Konsol Penceresi Aç", command=self.open_console)
        console_btn.pack(pady=10)
        
        alarm_frame = ttk.LabelFrame(main_frame, text=" Alarm Hesaplama ", padding=15)
        alarm_frame.pack(fill=tk.X, pady=10)
        
        alarm_btn = ttk.Button(alarm_frame, text="🔔 Manuel Alarm Hesapla", command=self.calculate_alarms)
        alarm_btn.pack(pady=5)
        
        self.alarm_status_label = ttk.Label(alarm_frame, text="")
        self.alarm_status_label.pack(pady=5)
    
    def create_alarms_tab(self, parent):
        alarm_notebook = ttk.Notebook(parent)
        alarm_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        for alarm_type, alarm_name in ALARM_TYPES:
            config_fields = ALARM_CONFIG_FIELDS.get(alarm_type, [])
            tab = AlarmSettingsTab(
                alarm_notebook, 
                alarm_type, 
                alarm_name, 
                config_fields,
                self.get_supabase_client
            )
            alarm_notebook.add(tab, text=alarm_name)
            self.alarm_tabs[alarm_type] = tab
        
        refresh_all_btn = ttk.Button(parent, text="🔄 Tüm Ayarları Yenile", command=self.load_all_alarm_settings)
        refresh_all_btn.pack(pady=10)
    
    def load_all_alarm_settings(self):
        for alarm_type, tab in self.alarm_tabs.items():
            tab.load_config()
            tab.load_alarms()
    
    def save_settings(self):
        self.config['SUPABASE_URL'] = self.url_entry.get().strip()
        self.config['SUPABASE_ANON_KEY'] = self.key_entry.get().strip()
        self.config['SCRAPE_INTERVAL_MINUTES'] = self.interval_var.get()
        
        if save_config(self.config):
            messagebox.showinfo("Başarılı", "Ayarlar kaydedildi!")
            
            if self.scraper_thread and self.scraper_thread.running:
                self.scraper_thread.set_interval(self.interval_var.get())
        else:
            messagebox.showerror("Hata", "Ayarlar kaydedilemedi!")
    
    def start_scraper(self):
        if not self.config.get('SUPABASE_URL') or not self.config.get('SUPABASE_ANON_KEY'):
            messagebox.showwarning("Uyarı", "Supabase ayarlarını girin!")
            return
        
        self.save_settings()
        
        self.scraper_thread = ScraperThread(
            self.config,
            self.log_queue,
            self.update_status
        )
        self.scraper_thread.start()
        
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        
        if not self.console_window or not self.console_window.winfo_exists():
            self.open_console()
    
    def pause_scraper(self):
        if self.scraper_thread:
            if self.scraper_thread.paused:
                self.scraper_thread.resume()
                self.pause_btn.config(text="⏸ Duraklat")
            else:
                self.scraper_thread.pause()
                self.pause_btn.config(text="▶ Devam")
    
    def stop_scraper(self):
        if self.scraper_thread:
            self.scraper_thread.stop()
            self.scraper_thread = None
        
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self.pause_btn.config(text="⏸ Duraklat")
    
    def open_console(self):
        if self.console_window and self.console_window.winfo_exists():
            self.console_window.lift()
            return
        
        self.console_window = ScraperConsoleWindow(self, self.log_queue)
    
    def update_status(self, status):
        status_texts = {
            'scraping': '🔄 Scrape yapılıyor...',
            'calculating': '🧮 Alarm hesaplanıyor...',
            'waiting': '⏳ Bekliyor...',
            'paused': '⏸ Duraklatıldı',
            'stopped': '⏹ Durduruldu'
        }
        self.status_label.config(text=f"Durum: {status_texts.get(status, status)}")
    
    def update_status_display(self):
        if self.scraper_thread and self.scraper_thread.running:
            if self.scraper_thread.last_scrape_time:
                self.last_scrape_label.config(
                    text=f"Son Scrape: {self.scraper_thread.last_scrape_time.strftime('%H:%M:%S')}"
                )
            self.total_scrapes_label.config(text=f"Toplam Scrape: {self.scraper_thread.total_scrapes}")
            self.total_rows_label.config(text=f"Toplam Satır: {self.scraper_thread.total_rows}")
        
        self.after(1000, self.update_status_display)
    
    def calculate_alarms(self):
        if not self.config.get('SUPABASE_URL') or not self.config.get('SUPABASE_ANON_KEY'):
            messagebox.showwarning("Uyarı", "Supabase ayarlarını girin!")
            return
        
        self.alarm_status_label.config(text="Alarm hesaplanıyor...")
        self.update()
        
        def run_calc():
            try:
                from alarm_calculator import AlarmCalculator
                calc = AlarmCalculator(
                    self.config['SUPABASE_URL'],
                    self.config['SUPABASE_ANON_KEY']
                )
                calc.run_all_calculations()
                self.after(0, lambda: self.alarm_status_label.config(text="✅ Alarm hesaplama tamamlandı!"))
                self.after(0, self.load_all_alarm_settings)
            except Exception as e:
                self.after(0, lambda: self.alarm_status_label.config(text=f"❌ Hata: {e}"))
        
        threading.Thread(target=run_calc, daemon=True).start()
    
    def on_closing(self):
        if self.scraper_thread and self.scraper_thread.running:
            if messagebox.askyesno("Çıkış", "Scraper çalışıyor. Çıkmak istediğinize emin misiniz?"):
                self.scraper_thread.stop()
                self.destroy()
        else:
            self.destroy()


def main():
    app = AdminPanel()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
