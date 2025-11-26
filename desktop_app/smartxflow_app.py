"""
SmartXFlow Alarm V1.01 - Desktop Application
Masaüstü uygulaması - Supabase'den veri okur ve gösterir
"""

import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import requests

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

VERSION = "1.01"
REFRESH_INTERVAL = 60000

MARKETS = {
    "Moneyway 1X2": "moneyway_1x2",
    "Moneyway O/U 2.5": "moneyway_ou25",
    "Moneyway BTTS": "moneyway_btts",
    "Dropping 1X2": "dropping_1x2",
    "Dropping O/U 2.5": "dropping_ou25",
    "Dropping BTTS": "dropping_btts",
}

MONEYWAY_1X2_COLS = ["League", "Date", "Home", "Away", "Odds1", "OddsX", "Odds2", "Pct1", "Amt1", "Volume"]
MONEYWAY_OU25_COLS = ["League", "Date", "Home", "Away", "Under", "Line", "Over", "PctUnder", "AmtUnder", "Volume"]
MONEYWAY_BTTS_COLS = ["League", "Date", "Home", "Away", "Yes", "No", "PctYes", "AmtYes", "Volume"]
DROPPING_1X2_COLS = ["League", "Date", "Home", "Away", "Odds1", "Odds1_prev", "Trend1", "OddsX", "Odds2", "Volume"]
DROPPING_OU25_COLS = ["League", "Date", "Home", "Away", "Under", "Under_prev", "TrendUnder", "Over", "Over_prev", "Volume"]
DROPPING_BTTS_COLS = ["League", "Date", "Home", "Away", "OddsYes", "OddsYes_prev", "TrendYes", "OddsNo", "Volume"]

MARKET_COLUMNS = {
    "moneyway_1x2": MONEYWAY_1X2_COLS,
    "moneyway_ou25": MONEYWAY_OU25_COLS,
    "moneyway_btts": MONEYWAY_BTTS_COLS,
    "dropping_1x2": DROPPING_1X2_COLS,
    "dropping_ou25": DROPPING_OU25_COLS,
    "dropping_btts": DROPPING_BTTS_COLS,
}


def get_turkey_time():
    if TURKEY_TZ:
        return datetime.now(TURKEY_TZ).strftime('%H:%M:%S')
    return datetime.now().strftime('%H:%M:%S')


def load_config():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(base_dir, 'config.json')
    
    if not os.path.exists(config_path):
        config_path = 'config.json'
    
    if not os.path.exists(config_path):
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except:
        return None


class SupabaseClient:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.key = key
    
    def _headers(self):
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}"
        }
    
    def fetch_table(self, table):
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/{table}?select=*&order=date.desc",
                headers=self._headers(),
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"Fetch error: {e}")
            return []
    
    def get_row_count(self, table):
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/{table}?select=id",
                headers={**self._headers(), "Prefer": "count=exact"},
                timeout=10
            )
            count = resp.headers.get('content-range', '').split('/')[-1]
            return int(count) if count.isdigit() else 0
        except:
            return 0


class SmartXFlowApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"SmartXFlow Alarm V{VERSION}")
        self.root.geometry("1400x800")
        self.root.configure(bg='#0d1117')
        
        self.config = load_config()
        if not self.config:
            messagebox.showerror("Hata", "config.json bulunamadı!\nLütfen config.json dosyasını uygulama ile aynı klasöre koyun.")
            sys.exit(1)
        
        self.client = SupabaseClient(
            self.config.get('SUPABASE_URL', ''),
            self.config.get('SUPABASE_ANON_KEY', '')
        )
        
        self.current_market = "moneyway_1x2"
        self.data = []
        
        self.setup_styles()
        self.create_widgets()
        self.load_data()
        self.auto_refresh()
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('TFrame', background='#0d1117')
        style.configure('TLabel', background='#0d1117', foreground='#c9d1d9', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'), foreground='#58a6ff')
        style.configure('Status.TLabel', font=('Segoe UI', 9), foreground='#8b949e')
        
        style.configure('TButton', 
                       background='#21262d', 
                       foreground='#c9d1d9',
                       font=('Segoe UI', 10),
                       padding=8)
        style.map('TButton',
                 background=[('active', '#30363d')],
                 foreground=[('active', '#58a6ff')])
        
        style.configure('Market.TButton',
                       background='#21262d',
                       foreground='#c9d1d9',
                       font=('Segoe UI', 9),
                       padding=6)
        style.map('Market.TButton',
                 background=[('active', '#238636'), ('selected', '#238636')],
                 foreground=[('active', '#ffffff')])
        
        style.configure('Treeview',
                       background='#161b22',
                       foreground='#c9d1d9',
                       fieldbackground='#161b22',
                       font=('Consolas', 9),
                       rowheight=28)
        style.configure('Treeview.Heading',
                       background='#21262d',
                       foreground='#58a6ff',
                       font=('Segoe UI', 9, 'bold'))
        style.map('Treeview',
                 background=[('selected', '#388bfd')],
                 foreground=[('selected', '#ffffff')])
    
    def create_widgets(self):
        header = ttk.Frame(self.root, padding=15)
        header.pack(fill=tk.X)
        
        title_label = ttk.Label(header, text=f"SmartXFlow Alarm V{VERSION}", style='Title.TLabel')
        title_label.pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(header, text="Yükleniyor...", style='Status.TLabel')
        self.status_label.pack(side=tk.RIGHT)
        
        self.time_label = ttk.Label(header, text="", style='Status.TLabel')
        self.time_label.pack(side=tk.RIGHT, padx=20)
        
        market_frame = ttk.Frame(self.root, padding=(15, 5))
        market_frame.pack(fill=tk.X)
        
        ttk.Label(market_frame, text="Market:", style='TLabel').pack(side=tk.LEFT, padx=(0, 10))
        
        self.market_buttons = {}
        for name, key in MARKETS.items():
            btn = ttk.Button(
                market_frame,
                text=name,
                style='Market.TButton',
                command=lambda k=key: self.select_market(k)
            )
            btn.pack(side=tk.LEFT, padx=3)
            self.market_buttons[key] = btn
        
        refresh_btn = ttk.Button(market_frame, text="🔄 Yenile", command=self.load_data)
        refresh_btn.pack(side=tk.RIGHT)
        
        table_frame = ttk.Frame(self.root, padding=15)
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(table_frame, show='headings')
        
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        stats_frame = ttk.Frame(self.root, padding=10)
        stats_frame.pack(fill=tk.X)
        
        self.stats_label = ttk.Label(stats_frame, text="", style='Status.TLabel')
        self.stats_label.pack(side=tk.LEFT)
        
        self.update_market_buttons()
        self.update_time()
    
    def update_time(self):
        self.time_label.config(text=f"🕐 {get_turkey_time()} (TR)")
        self.root.after(1000, self.update_time)
    
    def update_market_buttons(self):
        for key, btn in self.market_buttons.items():
            if key == self.current_market:
                btn.configure(style='TButton')
            else:
                btn.configure(style='Market.TButton')
    
    def select_market(self, market):
        self.current_market = market
        self.update_market_buttons()
        self.load_data()
    
    def setup_columns(self, columns):
        self.tree.delete(*self.tree.get_children())
        self.tree['columns'] = columns
        
        for col in columns:
            width = 120
            if col in ['League', 'Home', 'Away']:
                width = 150
            elif col in ['Date']:
                width = 130
            elif col in ['Volume']:
                width = 100
            elif col in ['Pct1', 'PctX', 'Pct2', 'PctUnder', 'PctOver', 'PctYes', 'PctNo']:
                width = 70
            
            self.tree.heading(col, text=col, anchor='w')
            self.tree.column(col, width=width, anchor='w')
    
    def load_data(self):
        self.status_label.config(text="Yükleniyor...")
        
        def fetch():
            data = self.client.fetch_table(self.current_market)
            self.root.after(0, lambda: self.display_data(data))
        
        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
    
    def display_data(self, data):
        columns = MARKET_COLUMNS.get(self.current_market, [])
        self.setup_columns(columns)
        
        for row in data:
            values = []
            for col in columns:
                col_lower = col.lower()
                val = row.get(col_lower, row.get(col, ''))
                if val is None:
                    val = ''
                values.append(str(val))
            
            self.tree.insert('', 'end', values=values)
        
        count = len(data)
        market_name = [k for k, v in MARKETS.items() if v == self.current_market][0]
        self.status_label.config(text=f"✓ {count} maç yüklendi")
        self.stats_label.config(text=f"Market: {market_name} | Toplam: {count} maç | Son güncelleme: {get_turkey_time()}")
    
    def auto_refresh(self):
        self.load_data()
        self.root.after(REFRESH_INTERVAL, self.auto_refresh)


def main():
    root = tk.Tk()
    
    try:
        root.iconbitmap('icon.ico')
    except:
        pass
    
    app = SmartXFlowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
