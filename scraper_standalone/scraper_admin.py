"""
SmartXFlow Monitor - Admin Panel + Scraper
Ana ekran: Admin Panel (ayarlar, durum)
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

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

VERSION = "1.03"
CONFIG_FILE = "config.json"

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
                self.log("Alarm hesaplamalari basliyor...")
                
                try:
                    calculator = AlarmCalculator(
                        self.config['SUPABASE_URL'],
                        self.config['SUPABASE_ANON_KEY']
                    )
                    calculator.run_all_calculations()
                    self.log("Alarm hesaplamalari tamamlandi")
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


class AdminPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title(f"SmartXFlow Admin Panel v{VERSION}")
        self.geometry("600x700")
        self.configure(bg='#2d2d2d')
        
        self.config = load_config()
        self.log_queue = queue.Queue()
        self.scraper_thread = None
        self.console_window = None
        
        self.setup_styles()
        self.create_widgets()
        self.update_status_display()
    
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
    
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        header = ttk.Label(main_frame, text="SmartXFlow Admin Panel", style='Header.TLabel')
        header.pack(pady=(0, 20))
        
        config_frame = ttk.LabelFrame(main_frame, text=" Supabase Ayarlari ", padding=15)
        config_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(config_frame, text="Supabase URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(config_frame, width=50)
        self.url_entry.insert(0, self.config.get('SUPABASE_URL', ''))
        self.url_entry.grid(row=0, column=1, pady=5, padx=5)
        
        ttk.Label(config_frame, text="Supabase Key:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.key_entry = ttk.Entry(config_frame, width=50, show='*')
        self.key_entry.insert(0, self.config.get('SUPABASE_ANON_KEY', ''))
        self.key_entry.grid(row=1, column=1, pady=5, padx=5)
        
        scrape_frame = ttk.LabelFrame(main_frame, text=" Scrape Ayarlari ", padding=15)
        scrape_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(scrape_frame, text="Scrape Araligi (dakika):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.interval_var = tk.IntVar(value=self.config.get('SCRAPE_INTERVAL_MINUTES', 10))
        self.interval_spin = ttk.Spinbox(
            scrape_frame, 
            from_=1, 
            to=60, 
            width=10,
            textvariable=self.interval_var
        )
        self.interval_spin.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        save_btn = ttk.Button(scrape_frame, text="Ayarlari Kaydet", command=self.save_settings)
        save_btn.grid(row=1, column=0, columnspan=2, pady=10)
        
        status_frame = ttk.LabelFrame(main_frame, text=" Durum ", padding=15)
        status_frame.pack(fill=tk.X, pady=10)
        
        self.status_label = ttk.Label(status_frame, text="Durum: Durduruldu", style='Status.TLabel')
        self.status_label.pack(anchor=tk.W, pady=2)
        
        self.last_scrape_label = ttk.Label(status_frame, text="Son Scrape: -")
        self.last_scrape_label.pack(anchor=tk.W, pady=2)
        
        self.total_scrapes_label = ttk.Label(status_frame, text="Toplam Scrape: 0")
        self.total_scrapes_label.pack(anchor=tk.W, pady=2)
        
        self.total_rows_label = ttk.Label(status_frame, text="Toplam Satir: 0")
        self.total_rows_label.pack(anchor=tk.W, pady=2)
        
        control_frame = ttk.LabelFrame(main_frame, text=" Kontroller ", padding=15)
        control_frame.pack(fill=tk.X, pady=10)
        
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ Baslat", command=self.start_scraper, width=15)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.pause_btn = ttk.Button(btn_frame, text="⏸ Duraklat", command=self.pause_scraper, width=15, state=tk.DISABLED)
        self.pause_btn.grid(row=0, column=1, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ Durdur", command=self.stop_scraper, width=15, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=2, padx=5)
        
        console_btn = ttk.Button(control_frame, text="📋 Konsol Penceresi Ac", command=self.open_console)
        console_btn.pack(pady=10)
        
        alarm_frame = ttk.LabelFrame(main_frame, text=" Alarm Hesaplama ", padding=15)
        alarm_frame.pack(fill=tk.X, pady=10)
        
        alarm_btn = ttk.Button(alarm_frame, text="🔔 Manuel Alarm Hesapla", command=self.calculate_alarms)
        alarm_btn.pack(pady=5)
        
        self.alarm_status_label = ttk.Label(alarm_frame, text="")
        self.alarm_status_label.pack(pady=5)
        
        footer = ttk.Label(main_frame, text=f"SmartXFlow Monitor v{VERSION} - PC Scraper + Admin Panel")
        footer.pack(side=tk.BOTTOM, pady=10)
    
    def save_settings(self):
        self.config['SUPABASE_URL'] = self.url_entry.get().strip()
        self.config['SUPABASE_ANON_KEY'] = self.key_entry.get().strip()
        self.config['SCRAPE_INTERVAL_MINUTES'] = self.interval_var.get()
        
        if save_config(self.config):
            messagebox.showinfo("Basarili", "Ayarlar kaydedildi!")
            
            if self.scraper_thread and self.scraper_thread.running:
                self.scraper_thread.set_interval(self.interval_var.get())
        else:
            messagebox.showerror("Hata", "Ayarlar kaydedilemedi!")
    
    def start_scraper(self):
        if not self.config.get('SUPABASE_URL') or not self.config.get('SUPABASE_ANON_KEY'):
            messagebox.showwarning("Uyari", "Supabase ayarlarini girin!")
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
            'scraping': '🔄 Scrape yapiliyor...',
            'calculating': '🧮 Alarm hesaplaniyor...',
            'waiting': '⏳ Bekliyor...',
            'paused': '⏸ Duraklatildi',
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
            self.total_rows_label.config(text=f"Toplam Satir: {self.scraper_thread.total_rows}")
        
        self.after(1000, self.update_status_display)
    
    def calculate_alarms(self):
        if not self.config.get('SUPABASE_URL') or not self.config.get('SUPABASE_ANON_KEY'):
            messagebox.showwarning("Uyari", "Supabase ayarlarini girin!")
            return
        
        self.alarm_status_label.config(text="Alarm hesaplaniyor...")
        self.update()
        
        def run_calc():
            try:
                from alarm_calculator import AlarmCalculator
                calc = AlarmCalculator(
                    self.config['SUPABASE_URL'],
                    self.config['SUPABASE_ANON_KEY']
                )
                calc.run_all_calculations()
                self.after(0, lambda: self.alarm_status_label.config(text="✅ Alarm hesaplama tamamlandi!"))
            except Exception as e:
                self.after(0, lambda: self.alarm_status_label.config(text=f"❌ Hata: {e}"))
        
        threading.Thread(target=run_calc, daemon=True).start()
    
    def on_closing(self):
        if self.scraper_thread and self.scraper_thread.running:
            if messagebox.askyesno("Cikis", "Scraper calisiyor. Cikmak istediginize emin misiniz?"):
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
