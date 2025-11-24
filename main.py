"""
SmartXFlow - Odds & Volume Monitor
Professional Tkinter GUI with real-time scraping and charting
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import queue
import os
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from scraper.core import run_scraper, get_cookie_string
from services.supabase_client import LocalDatabase


MARKET_LABELS = {
    "moneyway_1x2": "Moneyway 1X2",
    "moneyway_ou25": "Moneyway O/U 2.5",
    "moneyway_btts": "Moneyway BTTS",
    "dropping_1x2": "Dropping 1X2",
    "dropping_ou25": "Dropping O/U 2.5",
    "dropping_btts": "Dropping BTTS"
}

MARKET_COLUMNS = {
    "moneyway_1x2": ["Odds1", "OddsX", "Odds2", "Pct1", "PctX", "Pct2"],
    "moneyway_ou25": ["Under", "Over", "PctUnder", "PctOver"],
    "moneyway_btts": ["Yes", "No", "PctYes", "PctNo"],
    "dropping_1x2": ["1", "X", "2"],
    "dropping_ou25": ["Under", "Over"],
    "dropping_btts": ["Yes", "No"]
}


class SmartXFlowApp:
    """Main application class with modern two-tab interface"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SmartXFlow – Odds & Volume Monitor")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)
        
        self.auto_scrape_running = False
        self.auto_scrape_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        
        self.db = LocalDatabase()
        self.current_matches = []
        self.selected_match = None
        self.selected_market = "moneyway_1x2"
        
        self.setup_styles()
        self.create_notebook()
        self.process_log_queue()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_styles(self):
        """Configure modern ttk styles"""
        self.style = ttk.Style()
        
        self.root.configure(bg='#f0f0f0')
        
        self.style.configure('Title.TLabel', 
                            font=('Segoe UI', 16, 'bold'),
                            background='#f0f0f0',
                            foreground='#1a1a2e')
        
        self.style.configure('Header.TLabel',
                            font=('Segoe UI', 11, 'bold'),
                            background='#f0f0f0',
                            foreground='#16213e')
        
        self.style.configure('Status.TLabel',
                            font=('Segoe UI', 10),
                            background='#f0f0f0')
        
        self.style.configure('TFrame', background='#f0f0f0')
        
        self.style.configure('Card.TFrame', 
                            background='#ffffff',
                            relief='solid')
        
        self.style.configure('Action.TButton',
                            font=('Segoe UI', 10),
                            padding=(15, 8))
        
        self.style.configure('TLabelframe', 
                            background='#f0f0f0',
                            font=('Segoe UI', 10, 'bold'))
        self.style.configure('TLabelframe.Label', 
                            background='#f0f0f0',
                            foreground='#16213e',
                            font=('Segoe UI', 10, 'bold'))
        
        self.style.configure('TNotebook', background='#f0f0f0')
        self.style.configure('TNotebook.Tab', 
                            font=('Segoe UI', 10, 'bold'),
                            padding=(20, 8))
        
    def create_notebook(self):
        """Create main notebook with two tabs"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.control_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.control_tab, text="  Kontrol Paneli  ")
        
        self.graph_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.graph_tab, text="  Veri & Grafik  ")
        
        self.create_control_tab()
        self.create_graph_tab()
        
    def create_control_tab(self):
        """Create the control panel tab"""
        main_frame = ttk.Frame(self.control_tab, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, sticky='ew', pady=(0, 15))
        
        title_label = ttk.Label(
            title_frame,
            text="SmartXFlow – Odds & Volume Monitor",
            style='Title.TLabel'
        )
        title_label.pack(side=tk.LEFT)
        
        cookie_status = "Cookie: OK" if get_cookie_string() else "Cookie: Yok"
        cookie_color = "#27ae60" if get_cookie_string() else "#e74c3c"
        self.cookie_label = ttk.Label(
            title_frame,
            text=cookie_status,
            foreground=cookie_color,
            font=('Segoe UI', 9)
        )
        self.cookie_label.pack(side=tk.RIGHT, padx=10)
        
        controls_frame = ttk.LabelFrame(main_frame, text="Kontroller", padding=15)
        controls_frame.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        controls_frame.columnconfigure((0, 1, 2), weight=1)
        
        self.manual_scrape_btn = ttk.Button(
            controls_frame,
            text="Simdi Scrape Et",
            command=self.manual_scrape,
            style='Action.TButton'
        )
        self.manual_scrape_btn.grid(row=0, column=0, padx=5, pady=5, sticky='ew')
        
        self.refresh_data_btn = ttk.Button(
            controls_frame,
            text="Veriyi Yenile",
            command=self.refresh_match_list,
            style='Action.TButton'
        )
        self.refresh_data_btn.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        
        self.clear_log_btn = ttk.Button(
            controls_frame,
            text="Log Temizle",
            command=self.clear_log,
            style='Action.TButton'
        )
        self.clear_log_btn.grid(row=0, column=2, padx=5, pady=5, sticky='ew')
        
        auto_frame = ttk.LabelFrame(main_frame, text="Otomatik Scrape", padding=15)
        auto_frame.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        auto_frame.columnconfigure(1, weight=1)
        
        ttk.Label(auto_frame, text="Aralık:", 
                 font=('Segoe UI', 10)).grid(row=0, column=0, padx=(0, 10))
        
        interval_frame = ttk.Frame(auto_frame)
        interval_frame.grid(row=0, column=1, sticky='w')
        
        self.interval_var = tk.StringVar(value="5")
        interval_combo = ttk.Combobox(
            interval_frame,
            textvariable=self.interval_var,
            values=["1", "2", "5", "10", "15", "30"],
            state="readonly",
            width=8,
            font=('Segoe UI', 10)
        )
        interval_combo.pack(side=tk.LEFT)
        
        ttk.Label(interval_frame, text=" dakika", 
                 font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        
        btn_frame = ttk.Frame(auto_frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(15, 5))
        btn_frame.columnconfigure((0, 1), weight=1)
        
        self.auto_start_btn = ttk.Button(
            btn_frame,
            text="Otomatik Scrape Baslat",
            command=self.start_auto_scrape,
            style='Action.TButton'
        )
        self.auto_start_btn.grid(row=0, column=0, padx=5, sticky='ew')
        
        self.stop_btn = ttk.Button(
            btn_frame,
            text="Durdur",
            command=self.stop_auto_scrape,
            style='Action.TButton',
            state=tk.DISABLED
        )
        self.stop_btn.grid(row=0, column=1, padx=5, sticky='ew')
        
        status_frame = ttk.Frame(auto_frame)
        status_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        
        self.status_indicator = tk.Canvas(status_frame, width=12, height=12, 
                                          bg='#f0f0f0', highlightthickness=0)
        self.status_indicator.pack(side=tk.LEFT, padx=(0, 8))
        self.status_indicator.create_oval(2, 2, 10, 10, fill='#95a5a6', outline='')
        
        self.status_label = ttk.Label(
            status_frame,
            text="Beklemede",
            style='Status.TLabel'
        )
        self.status_label.pack(side=tk.LEFT)
        
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding=10)
        log_frame.grid(row=3, column=0, sticky='nsew')
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            font=('Consolas', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white',
            state=tk.DISABLED,
            wrap=tk.WORD,
            relief='flat',
            padx=10,
            pady=10
        )
        self.log_text.grid(row=0, column=0, sticky='nsew')
        
        self.log_text.tag_configure('timestamp', foreground='#569cd6')
        self.log_text.tag_configure('success', foreground='#4ec9b0')
        self.log_text.tag_configure('error', foreground='#f14c4c')
        self.log_text.tag_configure('warning', foreground='#dcdcaa')
        
        self.add_log("Uygulama baslatildi. Scrape islemlerine hazir.")
        
    def create_graph_tab(self):
        """Create the data & graph tab"""
        main_frame = ttk.Frame(self.graph_tab, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        main_frame.columnconfigure(1, weight=3)
        main_frame.rowconfigure(0, weight=1)
        
        filter_frame = ttk.LabelFrame(main_frame, text="Filtreler", padding=15)
        filter_frame.grid(row=0, column=0, sticky='ns', padx=(0, 10))
        
        ttk.Label(filter_frame, text="Market:", 
                 style='Header.TLabel').pack(anchor='w', pady=(0, 5))
        
        self.market_var = tk.StringVar(value="moneyway_1x2")
        for key, label in MARKET_LABELS.items():
            rb = ttk.Radiobutton(
                filter_frame,
                text=label,
                value=key,
                variable=self.market_var,
                command=self.on_market_change
            )
            rb.pack(anchor='w', pady=2)
        
        ttk.Separator(filter_frame, orient='horizontal').pack(fill='x', pady=15)
        
        ttk.Label(filter_frame, text="Mac Listesi:", 
                 style='Header.TLabel').pack(anchor='w', pady=(0, 5))
        
        list_frame = ttk.Frame(filter_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.match_listbox = tk.Listbox(
            list_frame,
            font=('Segoe UI', 9),
            bg='#ffffff',
            fg='#1a1a2e',
            selectbackground='#3498db',
            selectforeground='white',
            height=15,
            width=30,
            yscrollcommand=scrollbar.set,
            relief='flat',
            highlightthickness=1,
            highlightcolor='#3498db',
            highlightbackground='#ddd'
        )
        self.match_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.match_listbox.yview)
        
        self.match_listbox.bind('<<ListboxSelect>>', self.on_match_select)
        
        ttk.Button(
            filter_frame,
            text="Verileri Yukle",
            command=self.refresh_match_list,
            style='Action.TButton'
        ).pack(fill='x', pady=(10, 0))
        
        graph_container = ttk.Frame(main_frame)
        graph_container.grid(row=0, column=1, sticky='nsew')
        graph_container.columnconfigure(0, weight=1)
        graph_container.rowconfigure(1, weight=1)
        
        self.graph_title = ttk.Label(
            graph_container,
            text="Mac ve market secin",
            style='Header.TLabel'
        )
        self.graph_title.pack(anchor='w', pady=(0, 10))
        
        chart_frame = ttk.Frame(graph_container)
        chart_frame.pack(fill=tk.BOTH, expand=True)
        
        if MATPLOTLIB_AVAILABLE:
            self.fig = Figure(figsize=(8, 5), dpi=100, facecolor='#f0f0f0')
            self.ax = self.fig.add_subplot(111)
            self.ax.set_facecolor('#ffffff')
            self.ax.grid(True, linestyle='--', alpha=0.3)
            self.ax.set_xlabel('Zaman', fontsize=10)
            self.ax.set_ylabel('Oran', fontsize=10)
            self.ax.set_title('Grafik icin mac secin', fontsize=11)
            
            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            no_chart_label = ttk.Label(
                chart_frame,
                text="Matplotlib yuklu degil.\nGrafik gosterimi icin matplotlib gerekli.",
                font=('Segoe UI', 12),
                foreground='#7f8c8d',
                justify='center'
            )
            no_chart_label.pack(expand=True)
            
    def on_market_change(self):
        """Handle market selection change"""
        self.selected_market = self.market_var.get()
        self.refresh_match_list()
        if self.selected_match:
            self.update_graph()
            
    def on_match_select(self, event):
        """Handle match selection from listbox"""
        selection = self.match_listbox.curselection()
        if selection and self.current_matches:
            idx = selection[0]
            if idx < len(self.current_matches):
                self.selected_match = self.current_matches[idx]
                self.update_graph()
                
    def refresh_match_list(self):
        """Refresh the match list from database"""
        self.match_listbox.delete(0, tk.END)
        self.current_matches = self.db.get_all_matches()
        
        for match in self.current_matches:
            display = f"{match.get('home_team', '')} vs {match.get('away_team', '')}"
            self.match_listbox.insert(tk.END, display)
            
        if self.current_matches:
            self.add_log(f"{len(self.current_matches)} mac yuklendi.")
        else:
            self.add_log("Veritabaninda mac bulunamadi. Once scrape yapin.")
            
    def update_graph(self):
        """Update the matplotlib graph with selected match data"""
        if not MATPLOTLIB_AVAILABLE or not self.selected_match:
            return
            
        home = self.selected_match.get('home_team', '')
        away = self.selected_match.get('away_team', '')
        market_key = self.selected_market
        
        history = self.db.get_match_history(home, away, market_key)
        
        self.ax.clear()
        self.ax.set_facecolor('#ffffff')
        self.ax.grid(True, linestyle='--', alpha=0.3)
        
        market_label = MARKET_LABELS.get(market_key, market_key)
        title = f"{home} vs {away} - {market_label}"
        self.graph_title.config(text=title)
        
        if not history:
            self.ax.set_title("Bu mac/market icin veri yok", fontsize=11)
            self.ax.set_xlabel('Zaman', fontsize=10)
            self.ax.set_ylabel('Oran', fontsize=10)
            self.canvas.draw()
            return
        
        timestamps = []
        for h in history:
            scraped = h.get('ScrapedAt', '')
            try:
                ts = datetime.fromisoformat(scraped)
                timestamps.append(ts)
            except:
                timestamps.append(datetime.now())
        
        colors = ['#e74c3c', '#3498db', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c']
        columns = MARKET_COLUMNS.get(market_key, [])
        
        for i, col in enumerate(columns[:3]):
            values = []
            for h in history:
                val = h.get(col, '')
                try:
                    v = float(val.split('\n')[0] if '\n' in str(val) else val)
                    values.append(v)
                except:
                    values.append(None)
            
            valid_ts = [t for t, v in zip(timestamps, values) if v is not None]
            valid_vals = [v for v in values if v is not None]
            
            if valid_vals:
                color = colors[i % len(colors)]
                self.ax.plot(valid_ts, valid_vals, 
                           marker='o', markersize=4,
                           linewidth=2, label=col, color=color)
        
        self.ax.set_xlabel('Zaman', fontsize=10)
        self.ax.set_ylabel('Oran', fontsize=10)
        self.ax.set_title(title, fontsize=11, fontweight='bold')
        self.ax.legend(loc='upper left', fontsize=9)
        
        self.fig.autofmt_xdate()
        self.fig.tight_layout()
        self.canvas.draw()
        
    def add_log(self, message, level='info'):
        """Thread-safe log adding"""
        self.log_queue.put((message, level))
        
    def process_log_queue(self):
        """Process log queue on main thread"""
        try:
            while True:
                message, level = self.log_queue.get_nowait()
                self._add_log_to_ui(message, level)
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_log_queue)
        
    def _add_log_to_ui(self, message, level='info'):
        """Actually add log to UI"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.log_text.config(state=tk.NORMAL)
        
        self.log_text.insert(tk.END, f"[{timestamp}] ", 'timestamp')
        
        tag = level if level in ('success', 'error', 'warning') else None
        self.log_text.insert(tk.END, f"{message}\n", tag)
        
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def clear_log(self):
        """Clear log window"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.add_log("Log temizlendi.")
        
    def manual_scrape(self):
        """Start manual scrape"""
        self.add_log("Manuel scrape baslatiliyor...")
        self.manual_scrape_btn.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self._run_scrape_task, args=("Manuel",))
        thread.daemon = True
        thread.start()
        
    def _run_scrape_task(self, scrape_type="Manuel"):
        """Run scrape task in thread"""
        try:
            def progress_cb(msg, current, total):
                self.add_log(f"[{current}/{total}] {msg}")
            
            result = run_scraper(progress_callback=progress_cb)
            
            if result.get('status') == 'ok':
                self.add_log(
                    f"{scrape_type} scrape tamamlandi! "
                    f"Maclar: {result.get('matches', 0)}, "
                    f"Sure: {result.get('duration_sec', 0)}s",
                    'success'
                )
            else:
                self.add_log(
                    f"Scrape hatasi: {result.get('error', 'Bilinmeyen hata')}",
                    'error'
                )
        except Exception as e:
            self.add_log(f"HATA: {str(e)}", 'error')
        finally:
            self.root.after(0, lambda: self.manual_scrape_btn.config(state=tk.NORMAL))
            
    def start_auto_scrape(self):
        """Start automatic scrape loop"""
        if self.auto_scrape_running:
            self.add_log("Otomatik scrape zaten calisiyor!", 'warning')
            return
            
        try:
            interval_minutes = int(self.interval_var.get())
        except ValueError:
            messagebox.showerror("Hata", "Gecerli bir zaman araligi secin!")
            return
        
        if self.auto_scrape_thread and self.auto_scrape_thread.is_alive():
            self.add_log("Onceki islem bitmesi bekleniyor...", 'warning')
            return
            
        self.auto_scrape_running = True
        self.stop_event.clear()
        
        self.auto_start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.manual_scrape_btn.config(state=tk.DISABLED)
        
        self.auto_scrape_thread = threading.Thread(
            target=self._auto_scrape_loop,
            args=(interval_minutes,)
        )
        self.auto_scrape_thread.daemon = True
        self.auto_scrape_thread.start()
        
        self.add_log(f"Otomatik scrape baslatildi (her {interval_minutes} dk)", 'success')
        self.update_status("Calisiyor", "#27ae60")
        
    def _auto_scrape_loop(self, interval_minutes):
        """Auto scrape loop"""
        interval_seconds = interval_minutes * 60
        
        while not self.stop_event.is_set():
            self.add_log("Otomatik scrape islemi...")
            self._run_scrape_task("Otomatik")
            
            for _ in range(interval_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
                
        self.add_log("Otomatik scrape durduruldu.")
        
    def stop_auto_scrape(self):
        """Stop automatic scrape"""
        if not self.auto_scrape_running:
            return
            
        self.add_log("Durduruluyor...")
        self.stop_event.set()
        self.auto_scrape_running = False
        
        if self.auto_scrape_thread and self.auto_scrape_thread.is_alive():
            self.auto_scrape_thread.join(timeout=3.0)
        
        self.auto_start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.manual_scrape_btn.config(state=tk.NORMAL)
        
        self.update_status("Durduruldu", "#e74c3c")
        self.add_log("Otomatik scrape durduruldu.", 'warning')
        
    def update_status(self, text, color):
        """Update status indicator"""
        self.status_label.config(text=text)
        self.status_indicator.delete("all")
        self.status_indicator.create_oval(2, 2, 10, 10, fill=color, outline='')
        
    def on_closing(self):
        """Cleanup on close"""
        self.stop_event.set()
        self.auto_scrape_running = False
        
        if self.auto_scrape_thread and self.auto_scrape_thread.is_alive():
            self.auto_scrape_thread.join(timeout=2.0)
        
        self.root.destroy()


def main():
    """Main entry point"""
    root = tk.Tk()
    
    try:
        root.iconbitmap(default='')
    except:
        pass
    
    app = SmartXFlowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
