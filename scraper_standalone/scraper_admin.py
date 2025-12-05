"""
SmartXFlow Admin Panel v1.04 - Web Admin + Scraper
Web admin paneli (pywebview) + Arka planda scraper
"""
import sys
import os
import threading
import time
import socket
import logging
import json
from datetime import datetime

VERSION = "1.04"
CONFIG_FILE = "config.json"

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
    """Config dosyası yolu"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), CONFIG_FILE)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)


def load_config():
    """Config dosyasını yükle"""
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
            logging.error(f"Config load error: {e}")
    
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
    """Arka planda scraper çalıştır"""
    try:
        from standalone_scraper import SupabaseWriter, run_scrape
        from alarm_calculator import AlarmCalculator
        
        writer = SupabaseWriter(
            config['SUPABASE_URL'],
            config['SUPABASE_ANON_KEY']
        )
        logging.info("Scraper: Supabase bağlantısı hazır")
        
        interval_minutes = config.get('SCRAPE_INTERVAL_MINUTES', 10)
        
        while True:
            try:
                logging.info("Scraper: Scrape başlıyor...")
                rows = run_scrape(writer)
                logging.info(f"Scraper: {rows} satır yazıldı")
                
                logging.info("Scraper: Alarm hesaplama başlıyor...")
                calculator = AlarmCalculator(
                    config['SUPABASE_URL'],
                    config['SUPABASE_ANON_KEY']
                )
                calculator.run_all_calculations()
                logging.info("Scraper: Alarm hesaplama tamamlandı")
                
            except Exception as e:
                logging.error(f"Scraper hata: {e}")
            
            logging.info(f"Scraper: {interval_minutes} dakika bekleniyor...")
            time.sleep(interval_minutes * 60)
            
    except ImportError as e:
        logging.error(f"Scraper import hatası: {e}")
    except Exception as e:
        logging.error(f"Scraper başlatma hatası: {e}")


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
    
    config = setup_environment()
    
    if not config.get('SUPABASE_URL') or not config.get('SUPABASE_ANON_KEY'):
        show_error_dialog(
            "Supabase Ayarları Eksik",
            "config.json dosyasında SUPABASE_URL ve SUPABASE_ANON_KEY ayarlanmalı.\n\n"
            f"Config dosyası: {get_config_path()}"
        )
        logging.error("Supabase credentials missing!")
        sys.exit(1)
    
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
