"""
SmartXFlow Monitor V1.02 - Desktop Application with License System
Masaüstü uygulaması: Flask backend + pywebview penceresi + Lisans kontrolü
"""
import sys
import os

if hasattr(sys, '_MEIPASS'):
    sys.path.insert(0, sys._MEIPASS)
    os.chdir(sys._MEIPASS)

import threading
import time
import socket
import logging
import hashlib
import uuid
import platform
import json
from datetime import datetime

VERSION = "1.02"
LICENSE_FILE = "license.json"

def setup_logging():
    """Log dosyası oluştur - EXE ile aynı dizinde"""
    log_dir = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.getcwd()
    log_file = os.path.join(log_dir, 'smartxflow_debug.log')
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info(f"=== SmartXFlow Desktop V{VERSION} Started at {datetime.now()} ===")
    logging.info(f"Log file: {log_file}")
    return log_file

def resource_path(relative_path):
    """PyInstaller EXE için dosya yolu çözümlemesi"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_license_file_path():
    """Lisans dosyası yolu - EXE ile aynı dizinde"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(os.path.dirname(sys.executable), LICENSE_FILE)
    return os.path.join(os.getcwd(), LICENSE_FILE)

def get_device_id():
    """Benzersiz cihaz ID oluştur (MAC + CPU + Node)"""
    try:
        mac = uuid.getnode()
        machine = platform.machine()
        node = platform.node()
        processor = platform.processor()
        
        raw = f"{mac}-{machine}-{node}-{processor}"
        device_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
        
        logging.info(f"Device ID generated: {device_id}")
        return device_id
    except Exception as e:
        logging.error(f"Device ID generation error: {e}")
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:16]

def get_device_name():
    """Cihaz adını al"""
    try:
        return f"{platform.node()} ({platform.system()} {platform.release()})"
    except:
        return "Unknown Device"

def load_saved_license():
    """Kayıtlı lisansı yükle"""
    try:
        license_path = get_license_file_path()
        if os.path.exists(license_path):
            with open(license_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logging.info(f"Saved license loaded: {data.get('key', '')[:10]}...")
                return data
    except Exception as e:
        logging.error(f"Load license error: {e}")
    return None

def save_license(key, email, expires_at, days_left):
    """Lisansı kaydet"""
    try:
        license_path = get_license_file_path()
        data = {
            'key': key,
            'email': email,
            'expires_at': expires_at,
            'days_left': days_left,
            'saved_at': datetime.now().isoformat()
        }
        with open(license_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logging.info(f"License saved: {key[:10]}...")
        return True
    except Exception as e:
        logging.error(f"Save license error: {e}")
        return False

def validate_license_online(key, device_id, device_name, api_base_url):
    """Online lisans doğrulama"""
    try:
        import requests
        
        url = f"{api_base_url}/api/licenses/validate"
        response = requests.post(url, json={
            'key': key,
            'device_id': device_id,
            'device_name': device_name
        }, timeout=10)
        
        data = response.json()
        logging.info(f"License validation response: {data}")
        return data
        
    except Exception as e:
        logging.error(f"Online validation error: {e}")
        return {'valid': False, 'error': f'Bağlantı hatası: {str(e)}'}

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

def show_info_dialog(title, message):
    """Bilgi mesajı göster"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
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

class LicenseAPI:
    """JavaScript'ten çağrılabilir lisans API'si"""
    def __init__(self, api_base_url, device_id, device_name):
        self.api_base_url = api_base_url
        self.device_id = device_id
        self.device_name = device_name
        self.license_valid = False
        self.license_data = None
    
    def validate(self, key):
        """Lisansı doğrula"""
        result = validate_license_online(key, self.device_id, self.device_name, self.api_base_url)
        
        if result.get('valid'):
            self.license_valid = True
            self.license_data = result
            save_license(
                key, 
                result.get('email', ''),
                result.get('expires_at', ''),
                result.get('days_left', 0)
            )
        
        return result
    
    def get_device_id(self):
        return self.device_id
    
    def open_url(self, url):
        """Harici URL aç"""
        import webbrowser
        webbrowser.open(url)

def show_activation_window(api_base_url, device_id, device_name):
    """Lisans aktivasyon penceresi göster"""
    import webview
    
    api = LicenseAPI(api_base_url, device_id, device_name)
    
    activation_html = f'''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>SmartXFlow Aktivasyon</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #080b10 0%, #0d1117 50%, #0b0f14 100%);
            color: #c9d1d9;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .container {{
            background: linear-gradient(180deg, #0f141a 0%, #0b0f14 100%);
            border: 1px solid rgba(255,255,255,0.04);
            border-radius: 20px;
            padding: 48px 40px;
            width: 440px;
            text-align: center;
            box-shadow: 
                0 0 0 1px rgba(255,255,255,0.04),
                0 20px 60px rgba(0,0,0,0.6),
                0 0 80px rgba(30,144,255,0.08);
        }}
        .logo {{
            width: 64px;
            height: auto;
            max-height: 64px;
            margin-bottom: 14px;
            object-fit: contain;
        }}
        .brand-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, rgba(30,144,255,0.18) 0%, rgba(30,144,255,0.06) 100%);
            border: 1px solid rgba(30,144,255,0.35);
            padding: 8px 16px;
            border-radius: 30px;
            margin-bottom: 16px;
            box-shadow: 0 0 20px rgba(30,144,255,0.12), 0 0 40px rgba(30,144,255,0.06);
        }}
        .brand-badge-icon {{
            width: 20px;
            height: 20px;
            background: linear-gradient(135deg, #1e90ff 0%, #00bfff 100%);
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: 700;
            color: white;
        }}
        .brand-badge-text {{
            font-size: 11px;
            font-weight: 600;
            color: #1e90ff;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        h1 {{ 
            color: #e6edf3; 
            font-size: 28px; 
            font-weight: 700;
            margin-bottom: 6px;
            letter-spacing: -0.5px;
        }}
        .subtitle {{ 
            font-size: 13px; 
            font-weight: 500;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 32px;
        }}
        .subtitle .green {{ color: #22c55e; }}
        .subtitle .red {{ color: #ef4444; }}
        .subtitle .muted {{ color: #8b949e; }}
        .form-group {{ margin-bottom: 24px; text-align: left; }}
        label {{
            display: block; 
            color: #8b949e; 
            font-size: 11px;
            margin-bottom: 10px; 
            text-transform: uppercase; 
            letter-spacing: 1px;
            font-weight: 500;
        }}
        input {{
            width: 100%; 
            padding: 16px 18px; 
            background: #0d1117;
            border: 1px solid #21262d; 
            border-radius: 10px; 
            color: #e6edf3;
            font-size: 18px; 
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; 
            letter-spacing: 2px;
            text-transform: uppercase;
            transition: all 0.2s ease;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 0 20px rgba(30,144,255,0.08);
        }}
        input:focus {{ 
            outline: none; 
            border-color: #1e90ff; 
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 0 0 2px rgba(30,144,255,0.4), 0 0 20px rgba(30,144,255,0.25);
        }}
        input::placeholder {{ 
            color: #30363d; 
            text-transform: uppercase; 
            letter-spacing: 2px;
            font-size: 16px;
        }}
        .btn {{
            width: 100%; 
            padding: 16px;
            background: linear-gradient(135deg, #1db954 0%, #22c55e 100%);
            border: none; 
            border-radius: 10px; 
            color: white;
            font-size: 15px; 
            font-weight: 600; 
            cursor: pointer; 
            transition: all 0.25s ease;
            letter-spacing: 0.5px;
            position: relative;
            overflow: hidden;
        }}
        .btn:hover {{ 
            transform: translateY(-3px); 
            box-shadow: 0 12px 28px rgba(29, 185, 84, 0.45);
            background: linear-gradient(135deg, #22c55e 0%, #34d058 100%);
        }}
        .btn:active {{ transform: translateY(0); }}
        .btn:disabled {{ 
            opacity: 0.6; 
            cursor: not-allowed; 
            transform: none;
            box-shadow: none;
        }}
        .btn-hint {{
            margin-top: 12px;
            font-size: 11px;
            color: #484f58;
            text-align: center;
        }}
        .btn-loading {{
            display: none;
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
        }}
        .btn-loading .spinner {{
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .error {{
            background: rgba(248, 81, 73, 0.1); 
            border: 1px solid rgba(248, 81, 73, 0.3);
            color: #f85149; 
            padding: 14px 16px; 
            border-radius: 10px;
            margin-bottom: 20px; 
            font-size: 13px; 
            display: none;
            text-align: left;
        }}
        .success {{
            background: rgba(35, 134, 54, 0.15); 
            border: 1px solid rgba(35, 134, 54, 0.3);
            color: #3fb950; 
            padding: 14px 16px; 
            border-radius: 10px;
            margin-bottom: 20px; 
            font-size: 13px; 
            display: none;
            text-align: center;
        }}
        .success-icon {{
            font-size: 24px;
            margin-bottom: 8px;
            animation: successPop 0.4s ease;
        }}
        @keyframes successPop {{
            0% {{ transform: scale(0); opacity: 0; }}
            50% {{ transform: scale(1.2); }}
            100% {{ transform: scale(1); opacity: 1; }}
        }}
        .shopier-btn {{
            margin-top: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 14px 24px;
            background: linear-gradient(135deg, #c45500 0%, #d4650a 100%);
            border: none;
            border-radius: 10px;
            color: white;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(196,85,0,0.2);
        }}
        .shopier-btn:hover {{
            transform: translateY(-2px);
            background: linear-gradient(135deg, #d4650a 0%, #e8750f 100%);
            box-shadow: 0 6px 20px rgba(196,85,0,0.4);
        }}
        .shopier-hint {{
            margin-top: 8px;
            font-size: 10px;
            color: #6e7681;
            text-align: center;
        }}
        .shopier-icon {{
            font-size: 18px;
        }}
        .social-section {{
            margin-top: 20px;
            padding: 16px;
            background: rgba(13,17,23,0.5);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            text-align: center;
        }}
        .social-title {{
            color: #8b949e;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 12px;
        }}
        .social-icons {{
            display: flex;
            justify-content: center;
            gap: 16px;
        }}
        .social-icon {{
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            cursor: pointer;
        }}
        .social-icon svg {{
            width: 20px;
            height: 20px;
        }}
        .social-icon.instagram {{
            background: rgba(225,48,108,0.15);
            border: 1px solid rgba(225,48,108,0.3);
        }}
        .social-icon.instagram svg {{
            fill: #E1306C;
        }}
        .social-icon.telegram {{
            background: rgba(0,136,204,0.15);
            border: 1px solid rgba(0,136,204,0.3);
        }}
        .social-icon.telegram svg {{
            fill: #0088cc;
        }}
        .social-icon-email {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            background: rgba(234,67,53,0.15);
            border: 1px solid rgba(234,67,53,0.3);
            border-radius: 10px;
            text-decoration: none;
            color: #ea4335;
            font-size: 11px;
            transition: all 0.2s ease;
            cursor: pointer;
        }}
        .social-icon-email svg {{
            width: 18px;
            height: 18px;
            flex-shrink: 0;
            fill: #ea4335;
        }}
        .social-icon-email:hover {{
            transform: scale(1.05);
            background: rgba(234,67,53,0.25);
        }}
        .social-icon:hover {{
            transform: scale(1.1);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}
        .device-info {{ 
            margin-top: 20px; 
            padding: 12px 16px; 
            background: rgba(13,17,23,0.6); 
            border: 1px solid #21262d;
            border-radius: 8px; 
            font-size: 11px; 
            color: #484f58;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .device-info-icon {{ opacity: 0.6; }}
        .progress-bar {{
            display: none;
            height: 3px;
            background: #21262d;
            border-radius: 2px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .progress-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #1e90ff, #00bfff);
            width: 0%;
            transition: width 0.3s ease;
            animation: progressPulse 1.5s ease infinite;
        }}
        @keyframes progressPulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        .fade-out {{
            animation: fadeOut 0.5s ease forwards;
        }}
        @keyframes fadeOut {{
            to {{ opacity: 0; transform: scale(0.98); }}
        }}
    </style>
</head>
<body>
    <div class="container" id="mainContainer">
        <h1>SmartXFlow Monitor</h1>
        <p class="subtitle"><span class="green">Akıllı Para</span> <span class="muted">&</span> <span class="red">Oran Takibi</span></p>
        
        <div id="progressBar" class="progress-bar">
            <div class="progress-bar-fill" id="progressFill"></div>
        </div>
        
        <div id="errorMsg" class="error"></div>
        <div id="successMsg" class="success"></div>
        
        <div class="form-group">
            <label>Lisans Anahtari</label>
            <input type="text" id="licenseKey" placeholder="SXF-XXXX-XXXX-XXXX" maxlength="18" autocomplete="off" spellcheck="false">
        </div>
        
        <button class="btn" id="activateBtn" onclick="activate()">
            <span class="btn-text">Lisansi Aktif Et</span>
            <div class="btn-loading"><div class="spinner"></div></div>
        </button>
        <div class="btn-hint">Lisans dogrulamasi birkac saniye surebilir</div>
        
        <a href="#" id="shopierBtn" class="shopier-btn" onclick="window.pywebview.api.open_url('https://shopier.com')">
            <span class="shopier-icon">🛒</span>
            <span>Lisans Satin Al</span>
        </a>
        <div class="shopier-hint">Guvenli odeme • Aninda lisans teslimi</div>
        
        <div class="social-section">
            <div class="social-title">Bize Ulasin</div>
            <div class="social-icons">
                <a href="#" onclick="window.pywebview.api.open_url('https://www.instagram.com/smartxflow/')" class="social-icon instagram" title="Instagram">
                    <svg viewBox="0 0 24 24" fill="white"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
                </a>
                <a href="#" onclick="window.pywebview.api.open_url('https://t.me/smartxflow')" class="social-icon telegram" title="Telegram">
                    <svg viewBox="0 0 24 24" fill="white"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
                </a>
                <a href="#" onclick="copyEmail()" class="social-icon-email" title="Kopyalamak icin tikla">
                    <svg viewBox="0 0 24 24" fill="white"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                    <span id="emailText">smartxflow29@gmail.com</span>
                </a>
            </div>
        </div>
        
        <div class="device-info">
            <span class="device-info-icon">🔒</span>
            <span>Cihaz otomatik tanimlandi</span>
        </div>
    </div>
    
    <script>
        const keyInput = document.getElementById('licenseKey');
        const btn = document.getElementById('activateBtn');
        const btnText = btn.querySelector('.btn-text');
        const btnLoading = btn.querySelector('.btn-loading');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        
        keyInput.addEventListener('input', function(e) {{
            let value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            if (value.length > 3 && !value.startsWith('SXF')) value = 'SXF' + value.substring(0, 12);
            let formatted = '';
            if (value.length > 0) {{
                formatted = value.substring(0, 3);
                if (value.length > 3) formatted += '-' + value.substring(3, 7);
                if (value.length > 7) formatted += '-' + value.substring(7, 11);
                if (value.length > 11) formatted += '-' + value.substring(11, 15);
            }}
            e.target.value = formatted;
        }});
        
        function showLoading() {{
            btn.disabled = true;
            btnText.style.opacity = '0';
            btnLoading.style.display = 'block';
            progressBar.style.display = 'block';
            let progress = 0;
            const interval = setInterval(() => {{
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                progressFill.style.width = progress + '%';
            }}, 200);
            return interval;
        }}
        
        function hideLoading(interval) {{
            clearInterval(interval);
            progressFill.style.width = '100%';
            setTimeout(() => {{
                btn.disabled = false;
                btnText.style.opacity = '1';
                btnLoading.style.display = 'none';
                progressBar.style.display = 'none';
                progressFill.style.width = '0%';
            }}, 300);
        }}
        
        function copyEmail() {{
            const email = 'smartxflow29@gmail.com';
            const emailSpan = document.getElementById('emailText');
            navigator.clipboard.writeText(email).then(() => {{
                emailSpan.textContent = 'Kopyalandi!';
                setTimeout(() => {{ emailSpan.textContent = email; }}, 1500);
            }});
        }}
        
        async function activate() {{
            const key = keyInput.value.trim();
            const errorEl = document.getElementById('errorMsg');
            const successEl = document.getElementById('successMsg');
            
            errorEl.style.display = 'none';
            successEl.style.display = 'none';
            
            if (!key || key.length < 18) {{
                errorEl.textContent = 'Lutfen gecerli bir lisans anahtari girin.';
                errorEl.style.display = 'block';
                keyInput.focus();
                return;
            }}
            
            const loadingInterval = showLoading();
            
            try {{
                const result = await pywebview.api.validate(key);
                
                hideLoading(loadingInterval);
                
                if (result.valid) {{
                    successEl.innerHTML = '<div class="success-icon">✓</div>Lisans aktif! Uygulama aciliyor...';
                    successEl.style.display = 'block';
                    
                    setTimeout(() => {{
                        document.getElementById('mainContainer').classList.add('fade-out');
                        setTimeout(() => {{
                            pywebview.api.close_and_continue();
                        }}, 500);
                    }}, 1500);
                }} else {{
                    errorEl.textContent = result.error || 'Lisans dogrulanamadi.';
                    errorEl.style.display = 'block';
                }}
            }} catch (e) {{
                hideLoading(loadingInterval);
                errorEl.textContent = 'Baglanti hatasi. Lutfen tekrar deneyin.';
                errorEl.style.display = 'block';
            }}
        }}
        
        keyInput.addEventListener('keypress', function(e) {{ if (e.key === 'Enter') activate(); }});
        keyInput.focus();
    </script>
</body>
</html>
'''
    
    activation_result = {'success': False, 'data': None}
    
    class ActivationAPI:
        def validate(self, key):
            result = api.validate(key)
            if result.get('valid'):
                activation_result['success'] = True
                activation_result['data'] = result
            return result
        
        def close_and_continue(self):
            activation_window.destroy()
    
    activation_api = ActivationAPI()
    
    activation_window = webview.create_window(
        title="SmartXFlow Aktivasyon",
        html=activation_html,
        width=480,
        height=580,
        resizable=False,
        js_api=activation_api
    )
    
    webview.start(gui='edgechromium')
    
    return activation_result

def main():
    log_file = setup_logging()
    logging.info(f"Starting SmartXFlow Desktop V{VERSION}...")
    
    device_id = get_device_id()
    device_name = get_device_name()
    
    port = find_free_port()
    if port is None:
        logging.error("No free port found!")
        show_error_dialog("SmartXFlow Monitor", "Port bulunamadı! Lütfen diğer uygulamaları kapatın.")
        sys.exit(1)
    
    logging.info(f"Using port: {port}")
    api_base_url = f"http://127.0.0.1:{port}"
    
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
        show_error_dialog("SmartXFlow Monitor", "Sunucu başlatılamadı!")
        sys.exit(1)
    
    logging.info("Flask server started successfully!")
    
    saved_license = load_saved_license()
    license_valid = False
    days_left = 0
    
    if saved_license and saved_license.get('key'):
        logging.info("Validating saved license...")
        result = validate_license_online(
            saved_license['key'], 
            device_id, 
            device_name, 
            api_base_url
        )
        
        if result.get('valid'):
            license_valid = True
            days_left = result.get('days_left', 0)
            logging.info(f"Saved license valid! Days left: {days_left}")
            
            save_license(
                saved_license['key'],
                result.get('email', saved_license.get('email', '')),
                result.get('expires_at', ''),
                days_left
            )
        else:
            logging.warning(f"Saved license invalid: {result.get('error')}")
            if result.get('expired'):
                show_error_dialog(
                    "Lisans Süresi Doldu",
                    "Lisans süreniz dolmuş.\n\n"
                    "Yenilemek için Telegram: @smartxflow"
                )
            elif result.get('device_limit'):
                show_error_dialog(
                    "Cihaz Limiti",
                    "Bu lisans başka cihazlarda aktif.\n\n"
                    "Yardım için Telegram: @smartxflow"
                )
    
    if not license_valid:
        logging.info("Showing activation window...")
        activation_result = show_activation_window(api_base_url, device_id, device_name)
        
        if not activation_result['success']:
            logging.info("Activation cancelled or failed")
            sys.exit(0)
        
        days_left = activation_result['data'].get('days_left', 0)
        logging.info(f"Activation successful! Days left: {days_left}")
    
    if 0 < days_left <= 7:
        show_info_dialog(
            "Lisans Uyarısı",
            f"Lisansınızın bitmesine {days_left} gün kaldı.\n\n"
            "Yenilemek için Telegram: @smartxflow"
        )
    
    logging.info("Testing Supabase connection...")
    try:
        from services.supabase_client import SupabaseClient
        sc = SupabaseClient()
        logging.info(f"Supabase available: {sc.is_available}")
        
        if sc.is_available:
            matches = sc.get_all_matches_with_latest('moneyway_1x2')
            logging.info(f"Test query: {len(matches)} matches from moneyway_1x2")
    except Exception as e:
        logging.error(f"Supabase test error: {e}")
    
    try:
        import webview
        logging.info("Creating main webview window...")
        
        window = webview.create_window(
            title=f"SmartXFlow Monitor V{VERSION}",
            url=f"http://127.0.0.1:{port}",
            width=1400,
            height=850,
            resizable=True,
            min_size=(1000, 600),
            text_select=True
        )
        
        logging.info("Starting main webview...")
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
            show_error_dialog("SmartXFlow Monitor Hatası", f"Uygulama başlatılamadı:\n{error_msg}")
        sys.exit(1)

if __name__ == "__main__":
    main()
