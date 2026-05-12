import time
import json
import urllib.request
import urllib.error

# Thông số kết nối ThingsBoard cho Máy QC
TB_HOST = "tb-dev.imespro.ai"
TB_PORT = 58090
USER_NAME = "KqKd3frfckERpdFcobQ9" # Token của Virtual_QC_Machine (Device: QC-Trigger)

def main():
    print("="*60)
    print("  MAY QC AO (VIRTUAL) - CHẾ ĐỘ GỬI TÍN HIỆU KÍCH HOẠT")
    print("  Logic PASS/FAIL và Mapping sẽ do Rule Chain xử lý.")
    print("="*60)

    url = f"http://{TB_HOST}:{TB_PORT}/api/v1/{USER_NAME}/telemetry"

    product_count = 0
    while True:
        product_count += 1
        
        print(f"\n[QC] Đang giả lập chu kỳ sản xuất #{product_count}...")
        # Đếm ngược 60 giây mô phỏng thời gian máy chạy
        for i in range(60, 0, -1):
            print(f"\r[QC] Thời gian chờ máy hoàn tất: {i:02d}s", end="", flush=True)
            time.sleep(1)
            
        print("\r[QC] Máy đã chạy xong! Gửi tín hiệu kích hoạt QC lên Rule Chain...", flush=True)
        
        # Chỉ gửi tín hiệu trigger đơn giản
        payload = {
            "trigger_qc": True,
            "machine_status": "READY",
            "cycle_count": product_count
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    print(f"[QC] -> Đã kích hoạt Rule Chain thành công!")
                else:
                    print(f"[QC] -> Gửi thất bại. Status: {response.status}")
        except urllib.error.URLError as e:
            print(f"[QC] -> Lỗi kết nối ThingsBoard: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[QC] Đã dừng máy QC ảo.")
