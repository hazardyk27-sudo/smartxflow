"""
SmartXFlow Alarm V1.01 - Desktop Application
Masaüstü uygulaması: Flask backend + pywebview penceresi
"""
import sys
import os
import threading
import time
import socket

def resource_path(relative_path):
    """PyInstaller EXE için dosya yolu çözümlemesi"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

os.environ['PYWEBVIEW_GUI'] = 'edgechromium'
os.environ['SMARTX_DESKTOP'] = '1'

def find_free_port(preferred_ports=[5000, 5050, 5051, 5052]):
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
    from app import app
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)

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
    port = find_free_port()
    if port is None:
        show_error_dialog("SmartXFlow Alarm", "Port bulunamadı! Lütfen diğer uygulamaları kapatın.")
        sys.exit(1)
    
    if sys.platform == 'win32' and not check_webview2():
        show_error_dialog(
            "WebView2 Gerekli",
            "Microsoft Edge WebView2 Runtime yüklü değil.\n\n"
            "Lütfen şu adresten indirin:\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
            "Yükledikten sonra uygulamayı tekrar çalıştırın."
        )
        sys.exit(1)
    
    flask_thread = threading.Thread(target=run_flask, args=(port,), daemon=True)
    flask_thread.start()
    
    if not wait_for_server(port):
        show_error_dialog("SmartXFlow Alarm", "Sunucu başlatılamadı!")
        sys.exit(1)
    
    try:
        import webview
        
        window = webview.create_window(
            title="SmartXFlow Alarm V1.01",
            url=f"http://127.0.0.1:{port}",
            width=1400,
            height=850,
            resizable=True,
            min_size=(1000, 600),
            text_select=True
        )
        
        webview.start(gui='edgechromium')
        
    except Exception as e:
        error_msg = str(e)
        if "WebView2" in error_msg or "edgechromium" in error_msg.lower():
            show_error_dialog(
                "WebView2 Gerekli",
                "Microsoft Edge WebView2 Runtime yüklü değil.\n\n"
                "Lütfen şu adresten indirin:\n"
                "https://developer.microsoft.com/microsoft-edge/webview2/"
            )
        else:
            show_error_dialog("SmartXFlow Alarm Hatası", f"Uygulama başlatılamadı:\n{error_msg}")
        sys.exit(1)

if __name__ == "__main__":
    main()
