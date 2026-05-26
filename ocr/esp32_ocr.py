"""
esp32_ocr_mqtt_ultimate.py - Version 3.0 (OTA Stable)
============================================================
Features: Live Base64 Dashboard + ThingsBoard Edge OTA
"""

import sys
import os
import time
import json
import ssl
import urllib.request
import re
from pathlib import Path
import threading
import base64
import requests

# ── Tu dong dung venv ──────────────────────────────────────────────────────
_VENV_PYTHON = r"c:\thaytri\cuoiky\test_ocr\venv_vncv\Scripts\python.exe"
if os.path.isfile(_VENV_PYTHON) and "venv" not in sys.executable:
    import subprocess
    sys.exit(subprocess.run([_VENV_PYTHON] + sys.argv).returncode)

VNCV_SITE_PACKAGES = r"c:\thaytri\cuoiky\test_ocr\venv_vncv\Lib\site-packages"
if VNCV_SITE_PACKAGES not in sys.path: sys.path.insert(0, VNCV_SITE_PACKAGES)

try:
    from vncv import extract_text
    import paho.mqtt.client as mqtt
except ImportError:
    pass

# ── Credentials ─────────────────────────────────────────────────────────────
TB_HOST   = "tb-dev.imespro.ai"
TB_PORT   = 51883
CLIENT_ID = "ocr_machine"
USER_NAME = ""   # Tu dong lay tu ESP32 hoac .tb_token
TOKEN_FILE = Path(__file__).parent / ".tb_token"
ESP32_IP = "192.168.0.132"

active_client = None

is_ota_processing = False
last_ota_version = None

# ── Xu ly OTA ─────────────────────────────────────────────────────────────
def process_ota(token, fw_title, fw_version, fw_checksum="", fw_checksum_algorithm=""):
    global active_client, is_ota_processing, last_ota_version
    
    if active_client is None or not active_client.is_connected:
        print(f"[OTA] Dang cho ket noi MQTT de bat dau...")
        return

    if is_ota_processing or fw_version == last_ota_version:
        return
        
    is_ota_processing = True
    print(f"\n[OTA] --- BAT DAU CAP NHAT: {fw_title} (v{fw_version}) ---")
    
    try:
        # 1. Report DOWNLOADING
        active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "DOWNLOADING"}))
        
        # 2. Download from ThingsBoard (Port 58090)
        tb_url = f"http://{TB_HOST}:58090/api/v1/{token}/firmware?title={fw_title}&version={fw_version}"
        print(f"[OTA] 1/3: Dang tai file tu ThingsBoard...")
        resp = requests.get(tb_url, timeout=30)
        
        if resp.status_code == 200:
            fw_data = resp.content
            print(f"[OTA] 2/3: Tai xong {len(fw_data)} bytes.")
            
            import hashlib
            
            # 1. Kiem tra file voi ThingsBoard (Ho tro MD5 va SHA256)
            if fw_checksum:
                algo = fw_checksum_algorithm.upper() if fw_checksum_algorithm else "MD5"
                if "SHA256" in algo or "SHA-256" in algo:
                    calc_hash = hashlib.sha256(fw_data).hexdigest()
                else:
                    calc_hash = hashlib.md5(fw_data).hexdigest()
                    
                if calc_hash != fw_checksum:
                    print(f"[OTA] [!] LOI BAO MAT: Checksum khong khop! (Mong muon: {fw_checksum}, Thuc te: {calc_hash})")
                    active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "FAILED"}))
                    is_ota_processing = False
                    return
                print(f"[OTA] [*] File chuan tu ThingsBoard (Verified {algo}).")
            
            # 2. Tach chu ky so tu cuoi file
            clean_data = fw_data
            signature_hex = ""
            if len(fw_data) > 2:
                sig_len = int.from_bytes(fw_data[-2:], byteorder='big')
                if 60 <= sig_len <= 80 and len(fw_data) > sig_len + 2:
                    signature_bytes = fw_data[-(sig_len + 2):-2]
                    signature_hex = signature_bytes.hex()
                    clean_data = fw_data[:-(sig_len + 2)]
                    print(f"[OTA] [*] Da phat hien chu ky so: {signature_hex[:16]}... ({sig_len} bytes)")
                else:
                    print(f"[OTA] [!] CANH BAO: Khong phat hien chu ky so hop le o cuoi file!")
            
            # 3. Tinh MD5 cua clean binary de bao ve truyen dan Python -> ESP32
            esp_md5 = hashlib.md5(clean_data).hexdigest()
            print(f"[OTA] Dang ban xuong ESP32 (Kem ma bao ve MD5: {esp_md5[:8]}...).")

            time.sleep(5) 
        
            
            # Report UPDATING
            active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "UPDATING"}))
            
            # 4. Push to ESP32
            esp_url = f"http://{ESP32_IP}/update"
            files = {'image': ('firmware.bin', clean_data, 'application/octet-stream')}
            
            headers = {
                'Connection': 'close',
                'X-MD5': esp_md5,
                'X-Signature': signature_hex,
                'X-Auth-Token': token
            }
                
            esp_resp = requests.post(esp_url, files=files, timeout=300, headers=headers)  
            
            if esp_resp.status_code == 200 and "OK" in esp_resp.text:
                print("[OTA] 3/3: ESP32 xac nhan thanh cong! Dang reboot...")
                active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "UPDATED"}))
                last_ota_version = fw_version
            else:
                print(f"[OTA] [!] ESP32 bao loi: {esp_resp.status_code} - {esp_resp.text}")
                active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "FAILED"}))
        else:
            print(f"[OTA] [!] Loi tai file: HTTP {resp.status_code}")
            active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "FAILED"}))
            
    except Exception as e:
        print(f"[OTA] [!] Loi nghiem trong: {e}")
        try: active_client.client.publish("v1/devices/me/telemetry", json.dumps({"fw_state": "FAILED"}))
        except: pass
    finally:
        is_ota_processing = False
        print("[OTA] --- KET THUC QUY TRINH ---")

class TBClient:
    def __init__(self, version, use_ssl):
        self.version = version
        self.use_ssl = use_ssl
        self.is_connected = False
        
        if version == "v5":
            if hasattr(mqtt, 'CallbackAPIVersion'):
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5, client_id=CLIENT_ID)
            else:
                self.client = mqtt.Client(protocol=mqtt.MQTTv5, client_id=CLIENT_ID)
        else:
            if hasattr(mqtt, 'CallbackAPIVersion'):
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311, client_id=CLIENT_ID)
            else:
                self.client = mqtt.Client(protocol=mqtt.MQTTv311, client_id=CLIENT_ID)
            
        self.client.username_pw_set(USER_NAME, "")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        if use_ssl:
            try:
                self.client.tls_set_context(ssl.create_default_context())
                self.client.tls_insecure_set(True)
            except: pass

    def on_connect(self, client, userdata, flags, rc, properties=None):
        self.rc_code = rc.value if hasattr(rc, 'value') else rc
        if self.rc_code == 0:
            self.is_connected = True
            # Subscribe to Shared Attributes
            self.client.subscribe("v1/devices/me/attributes")
            self.client.subscribe("v1/devices/me/attributes/response/+")
            
            # Pull current OTA info immediately
            payload = {"sharedKeys": "fw_title,fw_version,fw_tag,target_fw_title,target_fw_version,target_fw_tag,fw_checksum,target_fw_checksum,fw_checksum_algorithm,target_fw_checksum_algorithm"}
            self.client.publish("v1/devices/me/attributes/request/1", json.dumps(payload))
        else:
            self.is_connected = False
            
    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            attr_data = data.get("shared", data)
            
            fw_keys = ["fw_title", "fw_version", "fw_tag", "target_fw_title", "target_fw_version", "target_fw_tag", "fw_checksum", "target_fw_checksum", "fw_checksum_algorithm", "target_fw_checksum_algorithm"]
            if any(k in attr_data for k in fw_keys):
                fw_title = attr_data.get("target_fw_title") or attr_data.get("fw_title") or attr_data.get("target_fw_tag") or "Firmware"
                fw_version = attr_data.get("target_fw_version") or attr_data.get("fw_version") or attr_data.get("target_fw_tag")
                fw_checksum = attr_data.get("target_fw_checksum") or attr_data.get("fw_checksum") or ""
                fw_algo = attr_data.get("target_fw_checksum_algorithm") or attr_data.get("fw_checksum_algorithm") or ""
                
                if fw_version:
                    threading.Thread(target=process_ota, args=(USER_NAME, fw_title, fw_version, fw_checksum, fw_algo), daemon=True).start()
        except: pass

    def connect(self):
        try:
            self.client.connect(TB_HOST, TB_PORT, 20)
            self.client.loop_start()
            for _ in range(10):
                if self.is_connected: return True
                time.sleep(0.5)
            self.client.loop_stop()
            return False
        except: return False

def get_device_info():
    try:
        with urllib.request.urlopen(f"http://{ESP32_IP}/info", timeout=5) as r:
            return json.loads(r.read().decode('utf-8')).get("tb_token", "")
    except: return ""

def main():
    
    global active_client, USER_NAME, is_ota_processing
    print("\n" + "="*50)
    print("      SYSTEM STARTING... (OTA GATEWAY ENABLED)")
    print("="*50)
    
    # 1. Resolve Token
    auto_token = get_device_info()
    if auto_token:
        USER_NAME = auto_token
        try: TOKEN_FILE.write_text(auto_token)
        except: pass
        print(f"[*] Token resolve: {USER_NAME[:8]}... (from Device)")
    elif TOKEN_FILE.exists():
        USER_NAME = TOKEN_FILE.read_text().strip()
        print(f"[*] Token resolve: {USER_NAME[:8]}... (from Cache)")
    else:
        print("[!] Critical: No Token found.")
        sys.exit(1)

    # 2. MQTT Connection
    scenarios = [("v3.1.1", False), ("v3.1.1", True), ("v5", False), ("v5", True)]
    for ver, use_ssl in scenarios:
        c = TBClient(ver, use_ssl)
        if c.connect():
            print(f"[*] MQTT Status  : Connected ({ver})")
            active_client = c
            break

    if not active_client:
        print("[!] MQTT Status  : Failed to connect.")
        sys.exit(1)

    # 3. Warmup & Loop
    print("[*] OCR Engine   : Loading...")
    try: extract_text(None, lang="vi")
    except: pass
    print("[*] OCR Engine   : Ready.")
    
    frame = 0
    print("\n[*] Monitoring started (Cycle: 5s)")
    while True:
        if is_ota_processing:
            print("[DEBUG] Dang co OTA, tam dung Monitoring 10s...")
            time.sleep(10)
            continue

        loop_start = time.time()
        frame += 1
        img_data = None

        
        try:
            with urllib.request.urlopen(f"http://{ESP32_IP}/capture", timeout=10) as r: 
                img_data = r.read()
        except:
            print(f"[#{frame}] ESP32 Link : Offline/Timed out")

        if img_data:
            img_filename = f"frame_{frame:04d}.jpg"
            path = Path(__file__).parent / "captures" / img_filename
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(img_data)
            
            # OCR
            results = []
            try: results = extract_text(str(path), lang="vi", return_dict=False)
            except: pass
            
            ocr_text = " ".join(results) if results else ""
            product_id = "UNKNOWN"
            if results:
                matches = re.findall(r'[A-Z0-9-]{4,}', " ".join(results))
                product_id = matches[0] if matches else "UNKNOWN"
            
            print(f"[#{frame}] Image: {img_filename} | OCR: {product_id}")
            
            # Telemetry
            b64_str = base64.b64encode(img_data).decode('utf-8')
            now = time.strftime("%H:%M:%S", time.localtime())
            
            payload = {
                "sequence": frame,
                "product_id": product_id,
                "ocr_text": ocr_text,       # <--- Thêm toàn bộ văn bản quét được
                "image_name": img_filename,
                "processed_at": now,
                "timestamp": int(time.time() * 1000),
                "image_base64": f"data:image/jpeg;base64,{b64_str}"
            }
            active_client.client.publish("v1/devices/me/telemetry", json.dumps(payload))

        time.sleep(max(0.1, 5.0 - (time.time() - loop_start)))

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nSystem stopped.")
