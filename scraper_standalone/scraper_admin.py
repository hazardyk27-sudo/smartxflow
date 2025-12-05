"""
SmartXFlow Admin Panel v1.05 - Web Admin + Scraper
Web admin paneli (pywebview) + Arka planda scraper
İlk açılışta config yoksa setup formu açılır ve config.json oluşturulur.
"""
import sys
import os
import threading
import time
import socket
import logging
import json
from datetime import datetime
from collections import deque
import queue

VERSION = "1.06"
CONFIG_FILE = "config.json"

# Scraper Console - Global Log Buffer & State
SCRAPER_LOG_BUFFER = deque(maxlen=500)
SCRAPER_LOG_LOCK = threading.Lock()
SCRAPER_SSE_CLIENTS = []
SCRAPER_STATE = {
    'running': False,
    'interval_minutes': 10,
    'last_scrape': None,
    'next_scrape': None,
    'last_rows': 0,
    'last_alarm_count': 0,
    'status': 'Bekliyor...'
}


def log_scraper(message, level='INFO'):
    """Scraper logunu buffer'a ve SSE client'lara gönder"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_line = f"[{timestamp}] {message}"
    
    with SCRAPER_LOG_LOCK:
        SCRAPER_LOG_BUFFER.append(log_line)
    
    # SSE client'lara gönder
    for client_queue in SCRAPER_SSE_CLIENTS[:]:
        try:
            client_queue.put_nowait(log_line)
        except:
            pass
    
    # Normal logging'e de yaz
    if level == 'ERROR':
        logging.error(f"Scraper: {message}")
    else:
        logging.info(f"Scraper: {message}")

# Hardcoded Supabase credentials (fallback)
EMBEDDED_SUPABASE_URL = "https://pswdvnmqjjnjodwzkmkp.supabase.co"
EMBEDDED_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzd2R2bm1xampuam9kd3prbWtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI3NzA0NzMsImV4cCI6MjA3ODM0NjQ3M30.Xt7kHbzOxK9-tqg4y0v5E_H5kLEcWZyLNqfQlLo3w3s"

def setup_logging():
    """Log dosyası oluştur"""
    log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, 'smartxflow_admin.log')
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info(f"=== SmartXFlow Admin Panel v{VERSION} Started ===")
    return log_file


def resource_path(relative_path):
    """PyInstaller EXE için dosya yolu çözümlemesi"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_config_path():
    """Config dosyası yolu - önce EXE yanı (kullanıcı kaydetmiş), sonra gömülü"""
    if getattr(sys, 'frozen', False):
        user_config = os.path.join(os.path.dirname(sys.executable), CONFIG_FILE)
        if os.path.exists(user_config):
            return user_config
        embedded_config = os.path.join(sys._MEIPASS, CONFIG_FILE)
        if os.path.exists(embedded_config):
            return embedded_config
        return user_config
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)


def get_writable_config_path():
    """Yazılabilir config dosyası yolu - her zaman EXE yanı"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), CONFIG_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)


def save_config(config):
    """Config dosyasını EXE yanına kaydet"""
    config_path = get_writable_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logging.info(f"Config saved to: {config_path}")
        return True
    except Exception as e:
        logging.error(f"Config save error: {e}")
        return False


def show_setup_dialog():
    """İlk kurulum dialog'u - Supabase bilgilerini al"""
    import tkinter as tk
    from tkinter import ttk, messagebox
    
    result = {'success': False, 'config': None}
    
    def on_save():
        url = url_entry.get().strip()
        key = key_entry.get().strip()
        
        if not url or not key:
            messagebox.showerror("Hata", "Supabase URL ve ANON_KEY gerekli!")
            return
        
        if not url.startswith('https://') or 'supabase' not in url:
            messagebox.showerror("Hata", "Geçerli bir Supabase URL girin!\nÖrnek: https://xxxxx.supabase.co")
            return
        
        if not key.startswith('eyJ'):
            messagebox.showerror("Hata", "Geçerli bir Supabase ANON_KEY girin!\nJWT token ile başlamalı (eyJ...)")
            return
        
        config = {
            'SUPABASE_URL': url,
            'SUPABASE_ANON_KEY': key,
            'SCRAPE_INTERVAL_MINUTES': 10
        }
        
        if save_config(config):
            result['success'] = True
            result['config'] = config
            root.destroy()
        else:
            messagebox.showerror("Hata", "Config dosyası kaydedilemedi!")
    
    def on_cancel():
        root.destroy()
    
    root = tk.Tk()
    root.title("SmartXFlow Admin - İlk Kurulum")
    root.geometry("550x320")
    root.resizable(False, False)
    
    try:
        root.iconbitmap(default='')
    except:
        pass
    
    root.configure(bg='#1a1a2e')
    
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TLabel', background='#1a1a2e', foreground='#e0e0e0', font=('Segoe UI', 10))
    style.configure('TEntry', fieldbackground='#16213e', foreground='#e0e0e0')
    style.configure('TButton', font=('Segoe UI', 10))
    
    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(fill='both', expand=True)
    main_frame.configure(style='TFrame')
    style.configure('TFrame', background='#1a1a2e')
    
    title_label = ttk.Label(main_frame, text="SmartXFlow Admin Panel - İlk Kurulum", 
                            font=('Segoe UI', 14, 'bold'), foreground='#4fc3f7')
    title_label.pack(pady=(0, 20))
    
    info_label = ttk.Label(main_frame, text="Supabase bağlantı bilgilerinizi girin.\nBu bilgiler config.json dosyasına kaydedilecek.",
                           font=('Segoe UI', 9), foreground='#888888')
    info_label.pack(pady=(0, 15))
    
    url_frame = ttk.Frame(main_frame)
    url_frame.pack(fill='x', pady=5)
    ttk.Label(url_frame, text="Supabase URL:", width=15).pack(side='left')
    url_entry = ttk.Entry(url_frame, width=50)
    url_entry.pack(side='left', padx=5)
    url_entry.insert(0, "https://")
    
    key_frame = ttk.Frame(main_frame)
    key_frame.pack(fill='x', pady=5)
    ttk.Label(key_frame, text="Supabase ANON_KEY:", width=15).pack(side='left')
    key_entry = ttk.Entry(key_frame, width=50, show='*')
    key_entry.pack(side='left', padx=5)
    
    show_key_var = tk.BooleanVar()
    def toggle_key():
        key_entry.configure(show='' if show_key_var.get() else '*')
    show_key_cb = ttk.Checkbutton(main_frame, text="Key'i göster", variable=show_key_var, command=toggle_key)
    show_key_cb.pack(anchor='w', pady=5)
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=20)
    
    save_btn = ttk.Button(button_frame, text="Kaydet ve Başlat", command=on_save)
    save_btn.pack(side='left', padx=10)
    
    cancel_btn = ttk.Button(button_frame, text="İptal", command=on_cancel)
    cancel_btn.pack(side='left', padx=10)
    
    root.eval('tk::PlaceWindow . center')
    root.mainloop()
    
    return result


def load_config():
    """Config dosyasını yükle - embedded fallback ile"""
    config_path = get_config_path()
    default_config = {
        'SUPABASE_URL': EMBEDDED_SUPABASE_URL,
        'SUPABASE_ANON_KEY': EMBEDDED_SUPABASE_KEY,
        'SCRAPE_INTERVAL_MINUTES': 10
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
                if content.startswith('\ufeff'):
                    content = content[1:]
                config = json.loads(content)
                if not config.get('SUPABASE_URL'):
                    config['SUPABASE_URL'] = EMBEDDED_SUPABASE_URL
                if not config.get('SUPABASE_ANON_KEY'):
                    config['SUPABASE_ANON_KEY'] = EMBEDDED_SUPABASE_KEY
                if 'SCRAPE_INTERVAL_MINUTES' not in config:
                    config['SCRAPE_INTERVAL_MINUTES'] = 10
                return config
        except Exception as e:
            logging.error(f"Config load error: {e}, using embedded credentials")
    
    logging.info("Using embedded Supabase credentials")
    return default_config


def setup_environment():
    """Ortam değişkenlerini ayarla"""
    config = load_config()
    
    if config.get('SUPABASE_URL'):
        os.environ['SUPABASE_URL'] = config['SUPABASE_URL']
    if config.get('SUPABASE_ANON_KEY'):
        os.environ['SUPABASE_ANON_KEY'] = config['SUPABASE_ANON_KEY']
    
    os.environ['PYWEBVIEW_GUI'] = 'edgechromium'
    os.environ['SMARTX_DESKTOP'] = '1'
    os.environ['DISABLE_SCRAPER'] = 'false'
    
    logging.info(f"Supabase URL: {config.get('SUPABASE_URL', '')[:40]}...")
    logging.info(f"Scrape Interval: {config.get('SCRAPE_INTERVAL_MINUTES', 10)} min")
    
    return config


def find_free_port(preferred_ports=[5000, 5050, 5051, 5052, 5053]):
    """Boş port bul"""
    for port in preferred_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return None


def wait_for_server(port, timeout=30):
    """Flask sunucusunun başlamasını bekle"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(('127.0.0.1', port))
                return True
        except (socket.error, socket.timeout):
            time.sleep(0.5)
    return False


def run_flask(port):
    """Flask sunucusunu başlat"""
    sys.path.insert(0, resource_path('.'))
    
    from app import app
    import logging as flask_log
    log = flask_log.getLogger('werkzeug')
    log.setLevel(flask_log.ERROR)
    
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)


def run_scraper(config):
    """Arka planda scraper çalıştır - canlı log ile"""
    global SCRAPER_STATE
    
    try:
        from standalone_scraper import SupabaseWriter, run_scrape
        from alarm_calculator import AlarmCalculator
        
        interval_minutes = config.get('SCRAPE_INTERVAL_MINUTES', 10)
        SCRAPER_STATE['interval_minutes'] = interval_minutes
        SCRAPER_STATE['running'] = True
        
        log_scraper("=" * 50)
        log_scraper(f"SmartXFlow Scraper v{VERSION} başlatıldı")
        log_scraper(f"Veri çekme aralığı: {interval_minutes} dakika")
        log_scraper("=" * 50)
        
        writer = SupabaseWriter(
            config['SUPABASE_URL'],
            config['SUPABASE_ANON_KEY']
        )
        log_scraper("Supabase bağlantısı hazır")
        
        while True:
            try:
                SCRAPER_STATE['status'] = 'Veri çekiliyor...'
                log_scraper("-" * 50)
                log_scraper("SCRAPE BAŞLIYOR...")
                
                # Moneyway verileri
                log_scraper("Moneyway verileri çekiliyor...")
                rows = run_scrape(writer)
                SCRAPER_STATE['last_rows'] = rows
                SCRAPER_STATE['last_scrape'] = datetime.now().isoformat()
                log_scraper(f"Scrape tamamlandı - Toplam: {rows} satır")
                
                # Alarm hesaplama
                SCRAPER_STATE['status'] = 'Alarmlar hesaplanıyor...'
                log_scraper("Alarm hesaplama başlıyor...")
                calculator = AlarmCalculator(
                    config['SUPABASE_URL'],
                    config['SUPABASE_ANON_KEY']
                )
                alarm_count = calculator.run_all_calculations()
                SCRAPER_STATE['last_alarm_count'] = alarm_count if alarm_count else 0
                log_scraper(f"Alarm hesaplama tamamlandı - {SCRAPER_STATE['last_alarm_count']} alarm")
                
            except Exception as e:
                log_scraper(f"HATA: {str(e)}", level='ERROR')
                SCRAPER_STATE['status'] = f'Hata: {str(e)[:50]}'
            
            # Bekleme
            next_run = datetime.now().timestamp() + (interval_minutes * 60)
            SCRAPER_STATE['next_scrape'] = datetime.fromtimestamp(next_run).isoformat()
            SCRAPER_STATE['status'] = f'{interval_minutes} dakika bekleniyor...'
            log_scraper(f"{interval_minutes} dakika bekleniyor...")
            log_scraper("-" * 50)
            
            time.sleep(interval_minutes * 60)
            
    except ImportError as e:
        log_scraper(f"Import hatası: {e}", level='ERROR')
        SCRAPER_STATE['running'] = False
    except Exception as e:
        log_scraper(f"Başlatma hatası: {e}", level='ERROR')
        SCRAPER_STATE['running'] = False


def show_error_dialog(title, message):
    """Hata mesajı göster"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except:
        print(f"{title}: {message}")


def check_webview2():
    """WebView2 Runtime kontrolü"""
    try:
        import winreg
        key_paths = [
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ]
        for path in key_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                winreg.CloseKey(key)
                return True
            except WindowsError:
                continue
        return False
    except:
        return True


def main():
    log_file = setup_logging()
    logging.info(f"Log file: {log_file}")
    
    config_path = get_writable_config_path()
    logging.info(f"Config path: {config_path}")
    
    need_setup = True
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                url = saved_config.get('SUPABASE_URL', '')
                key = saved_config.get('SUPABASE_ANON_KEY', '')
                if url and key and url.startswith('https://') and key.startswith('eyJ'):
                    need_setup = False
                    logging.info("Valid config found!")
        except Exception as e:
            logging.error(f"Config read error: {e}")
    
    if need_setup:
        logging.info("Config eksik veya gecersiz - Kurulum penceresi aciliyor...")
        result = show_setup_dialog()
        
        if not result['success']:
            logging.error("Kullanici kurulumu iptal etti")
            sys.exit(0)
        
        config = result['config']
    else:
        config = saved_config
    
    os.environ['SUPABASE_URL'] = config['SUPABASE_URL']
    os.environ['SUPABASE_ANON_KEY'] = config['SUPABASE_ANON_KEY']
    os.environ['PYWEBVIEW_GUI'] = 'edgechromium'
    os.environ['SMARTX_DESKTOP'] = '1'
    os.environ['DISABLE_SCRAPER'] = 'false'
    
    logging.info(f"Supabase URL: {config.get('SUPABASE_URL', '')[:40]}...")
    logging.info("Config loaded - starting application")
    
    port = find_free_port()
    if port is None:
        logging.error("No free port found!")
        show_error_dialog("SmartXFlow Admin", "Port bulunamadı! Diğer uygulamaları kapatın.")
        sys.exit(1)
    
    logging.info(f"Using port: {port}")
    
    if sys.platform == 'win32' and not check_webview2():
        logging.error("WebView2 not found!")
        show_error_dialog(
            "WebView2 Gerekli",
            "Microsoft Edge WebView2 Runtime yüklü değil.\n\n"
            "Lütfen şu adresten indirin:\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
            "Yükledikten sonra uygulamayı tekrar çalıştırın."
        )
        sys.exit(1)
    
    logging.info("Starting Flask server...")
    flask_thread = threading.Thread(target=run_flask, args=(port,), daemon=True)
    flask_thread.start()
    
    if not wait_for_server(port):
        logging.error("Flask server failed to start!")
        show_error_dialog("SmartXFlow Admin", "Sunucu başlatılamadı!")
        sys.exit(1)
    
    logging.info("Flask server started successfully!")
    
    logging.info("Starting background scraper...")
    scraper_thread = threading.Thread(target=run_scraper, args=(config,), daemon=True)
    scraper_thread.start()
    
    try:
        import webview
        logging.info("Creating webview window...")
        
        window = webview.create_window(
            title=f"SmartXFlow Admin Panel v{VERSION}",
            url=f"http://127.0.0.1:{port}/admin",
            width=1400,
            height=900,
            resizable=True,
            min_size=(1100, 700),
            text_select=True
        )
        
        logging.info("Starting webview (opening /admin)...")
        webview.start(gui='edgechromium')
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Webview error: {error_msg}")
        if "WebView2" in error_msg or "edgechromium" in error_msg.lower():
            show_error_dialog(
                "WebView2 Gerekli",
                "Microsoft Edge WebView2 Runtime yüklü değil.\n\n"
                "Lütfen şu adresten indirin:\n"
                "https://developer.microsoft.com/microsoft-edge/webview2/"
            )
        else:
            show_error_dialog("SmartXFlow Admin Hatası", f"Uygulama başlatılamadı:\n{error_msg}")
        sys.exit(1)
    
    logging.info("Application closed.")


if __name__ == "__main__":
    main()
