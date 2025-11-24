"""
SmartXFlow - Odds & Volume Monitor
Main application entry point with tkinter GUI
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import queue
from datetime import datetime

# Scraper fonksiyonunu import et (kullanıcı sonradan ekleyecek)
try:
    from scraper.core import run_scraper
except ImportError:
    # Eğer scraper henüz hazır değilse dummy fonksiyon kullan
    def run_scraper():
        return "Dummy scraper çalıştı"


class SmartXFlowApp:
    """Ana uygulama sınıfı"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SmartXFlow – Odds & Volume Monitor")
        self.root.geometry("700x500")
        self.root.resizable(True, True)
        
        # Otomatik scrape için değişkenler
        self.auto_scrape_running = False
        self.auto_scrape_thread = None
        self.stop_event = threading.Event()
        
        # Thread-safe logging için queue
        self.log_queue = queue.Queue()
        
        # UI oluştur
        self.create_widgets()
        
        # Log queue'sunu işle (her 100ms'de bir)
        self.process_log_queue()
        
        # Uygulama kapanırken temizlik
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_widgets(self):
        """Tüm UI bileşenlerini oluştur"""
        
        # Ana frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Grid ağırlıkları
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Başlık
        title_label = ttk.Label(
            main_frame, 
            text="SmartXFlow – Odds & Volume Monitor",
            font=("Arial", 14, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        
        # Buton frame
        button_frame = ttk.LabelFrame(main_frame, text="Kontroller", padding="10")
        button_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)
        
        # "Şimdi Scrape Et" butonu
        self.manual_scrape_btn = ttk.Button(
            button_frame,
            text="Şimdi Scrape Et",
            command=self.manual_scrape
        )
        self.manual_scrape_btn.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        # Otomatik scrape frame
        auto_frame = ttk.LabelFrame(main_frame, text="Otomatik Scrape", padding="10")
        auto_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        auto_frame.columnconfigure(1, weight=1)
        
        # Zaman aralığı seçimi
        ttk.Label(auto_frame, text="Aralık:").grid(row=0, column=0, padx=5, pady=5)
        
        self.interval_var = tk.StringVar(value="5")
        interval_combo = ttk.Combobox(
            auto_frame,
            textvariable=self.interval_var,
            values=["1", "5", "10", "15", "30"],
            state="readonly",
            width=10
        )
        interval_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(auto_frame, text="dakika").grid(row=0, column=2, padx=5, pady=5)
        
        # "Otomatik Scrape Başlat" butonu
        self.auto_start_btn = ttk.Button(
            auto_frame,
            text="Otomatik Scrape Başlat",
            command=self.start_auto_scrape
        )
        self.auto_start_btn.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        # "Durdur" butonu
        self.stop_btn = ttk.Button(
            auto_frame,
            text="Durdur",
            command=self.stop_auto_scrape,
            state=tk.DISABLED
        )
        self.stop_btn.grid(row=1, column=2, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        # Durum göstergesi
        self.status_label = ttk.Label(
            auto_frame,
            text="Durum: Beklemede",
            foreground="gray"
        )
        self.status_label.grid(row=2, column=0, columnspan=3, pady=5)
        
        # Log penceresi
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            width=80,
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Log temizleme butonu
        clear_log_btn = ttk.Button(
            main_frame,
            text="Log'u Temizle",
            command=self.clear_log
        )
        clear_log_btn.grid(row=4, column=0, columnspan=3, pady=5)
        
        # İlk log mesajı
        self.add_log("Uygulama başlatıldı.")
        
    def add_log(self, message):
        """
        Thread-safe log ekleme
        Worker thread'lerden çağrılabilir, queue'ya ekler
        """
        self.log_queue.put(message)
        
    def process_log_queue(self):
        """
        Log queue'sunu işle (main thread'de çalışır)
        Periyodik olarak queue'yu kontrol edip UI'ı günceller
        """
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._add_log_to_ui(message)
        except queue.Empty:
            pass
        
        # Her 100ms'de bir tekrar çağır
        self.root.after(100, self.process_log_queue)
        
    def _add_log_to_ui(self, message):
        """
        Log'u gerçekten UI'a ekle (sadece main thread'den çağrılır)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Console'a da yaz
        print(log_entry.strip())
        
    def clear_log(self):
        """Log penceresini temizle"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.add_log("Log temizlendi.")
        
    def manual_scrape(self):
        """Manuel scrape işlemini başlat"""
        self.add_log("Manuel scrape başlatıldı...")
        
        # Scrape işlemini ayrı thread'de çalıştır (UI donmasın)
        thread = threading.Thread(target=self._run_scrape_task, args=("Manuel",))
        thread.daemon = True
        thread.start()
        
    def _run_scrape_task(self, scrape_type="Manuel"):
        """Scrape işlemini çalıştır (thread-safe)"""
        try:
            result = run_scraper()
            self.add_log(f"{scrape_type} scrape tamamlandı. Sonuç: {result}")
        except Exception as e:
            self.add_log(f"HATA: {scrape_type} scrape sırasında hata oluştu: {str(e)}")
            
    def start_auto_scrape(self):
        """Otomatik scrape döngüsünü başlat"""
        if self.auto_scrape_running:
            self.add_log("Otomatik scrape zaten çalışıyor!")
            return
            
        try:
            interval_minutes = int(self.interval_var.get())
        except ValueError:
            messagebox.showerror("Hata", "Geçerli bir zaman aralığı seçin!")
            return
        
        # Önceki thread'in tamamen durduğundan emin ol
        if self.auto_scrape_thread and self.auto_scrape_thread.is_alive():
            self.add_log("Önceki scrape işlemi bitmesi bekleniyor...")
            self.auto_scrape_thread.join(timeout=5.0)
            if self.auto_scrape_thread.is_alive():
                messagebox.showerror(
                    "Hata", 
                    "Önceki scrape işlemi henüz bitmedi. Lütfen bekleyin ve tekrar deneyin."
                )
                return
            
        self.auto_scrape_running = True
        self.stop_event.clear()
        
        # Butonları güncelle
        self.auto_start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.manual_scrape_btn.config(state=tk.DISABLED)
        
        # Thread başlat
        self.auto_scrape_thread = threading.Thread(
            target=self._auto_scrape_loop,
            args=(interval_minutes,)
        )
        self.auto_scrape_thread.daemon = True
        self.auto_scrape_thread.start()
        
        self.add_log(f"Otomatik scrape başlatıldı. Aralık: {interval_minutes} dakika")
        self.update_status(f"Çalışıyor (Her {interval_minutes} dakikada)", "green")
        
    def _auto_scrape_loop(self, interval_minutes):
        """Otomatik scrape döngüsü (thread içinde çalışır)"""
        interval_seconds = interval_minutes * 60
        
        while not self.stop_event.is_set():
            # İlk scrape'i hemen çalıştır
            self.add_log("Otomatik scrape işlemi başlıyor...")
            self._run_scrape_task("Otomatik")
            
            # Sonraki scrape için bekle (her saniye kontrol et, böylece durdurma hızlı çalışır)
            for _ in range(interval_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
                
        self.add_log("Otomatik scrape döngüsü durduruldu.")
        
    def stop_auto_scrape(self):
        """Otomatik scrape döngüsünü durdur"""
        if not self.auto_scrape_running:
            return
            
        self.add_log("Otomatik scrape durduruluyor...")
        self.stop_event.set()
        self.auto_scrape_running = False
        
        # Thread'in bitmesini bekle (max 3 saniye)
        if self.auto_scrape_thread and self.auto_scrape_thread.is_alive():
            self.auto_scrape_thread.join(timeout=3.0)
            if self.auto_scrape_thread.is_alive():
                self.add_log("UYARI: Thread hala çalışıyor, ancak işaretlendi")
        
        # Butonları güncelle
        self.auto_start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.manual_scrape_btn.config(state=tk.NORMAL)
        
        self.update_status("Durduruldu", "orange")
        self.add_log("Otomatik scrape durduruldu.")
        
    def update_status(self, text, color="gray"):
        """
        Durum etiketini güncelle (thread-safe)
        """
        self.root.after(0, self._update_status_ui, text, color)
        
    def _update_status_ui(self, text, color):
        """Durum etiketini gerçekten güncelle (main thread'de çalışır)"""
        self.status_label.config(text=f"Durum: {text}", foreground=color)
        
    def on_closing(self):
        """Uygulama kapatılırken temizlik işlemleri"""
        # Stop event'i set et
        self.stop_event.set()
        self.auto_scrape_running = False
        
        # Thread varsa ve hala çalışıyorsa bekle (auto_scrape_running flag'inden bağımsız)
        if self.auto_scrape_thread and self.auto_scrape_thread.is_alive():
            self.auto_scrape_thread.join(timeout=3.0)
        
        self.root.destroy()


def main():
    """Ana giriş noktası"""
    root = tk.Tk()
    app = SmartXFlowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
