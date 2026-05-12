# KẾ HOẠCH TRIỂN KHAI CẬP NHẬT FIRMWARE TỪ XA (OTA UPDATE PLAN)

**Dự án:** Hệ thống Giám sát Sản xuất iMES
**Kiến trúc:** Gateway-based OTA (ThingsBoard -> Python -> ESP32)
**Ngày lập:** 12/05/2026

---

## 1. Mục tiêu (Objectives)
Thiết lập quy trình cập nhật phần mềm không dây (Over-the-Air) để:
- Nâng cấp tính năng OCR và xử lý ảnh từ xa.
- Sửa lỗi bảo mật và tối ưu hóa hiệu năng mà không cần can thiệp phần cứng.
- Giảm thiểu thời gian dừng máy (downtime) khi bảo trì hệ thống.

## 2. Kiến trúc Giải pháp (Architecture)
Hệ thống sử dụng mô hình **Gateway Proxy** để đảm bảo tính ổn định:
1. **ThingsBoard (Server):** Đóng vai trò Repository quản lý các bản build firmware (`.bin`).
2. **OCR Script (Gateway):** Chạy tại Edge (máy tính nội bộ), giám sát thuộc tính `fw_version` trên Cloud.
3. **ESP32-CAM (Node):** Cung cấp Endpoint `/update` để tiếp nhận firmware qua giao thức HTTP nội bộ.

## 3. Quy trình Triển khai Chi tiết

### Bước 1: Chuẩn bị Firmware
- Sử dụng Arduino IDE để xuất file Binary (`Sketch` -> `Export Compiled Binary`).
- Đảm bảo version trong code mới phải cao hơn version hiện tại.

### Bước 2: Quản lý trên ThingsBoard
1. Truy cập **Advanced features** -> **OTA updates**.
2. Tạo mới một bản Firmware:
   - **Title:** `ESP32-CAM-Firmware`
   - **Version:** (Ví dụ: `2.0.1`)
   - **File:** Tải lên file `.bin` đã chuẩn bị.

### Bước 3: Kích hoạt cập nhật
- Vào mục **Devices** hoặc **Device Profiles**.
- Chỉnh sửa thông tin thiết bị, tại mục **Firmware** chọn bản vừa upload.
- ThingsBoard sẽ tự động đẩy một tin nhắn MQTT thông báo có version mới xuống Gateway.

### Bước 4: Gateway thực thi (Tự động)
- `esp32_ocr.py` phát hiện `target_fw_version` thay đổi.
- Tự động tải file từ ThingsBoard qua API HTTP.
- Thực hiện lệnh `POST` dữ liệu nhị phân sang ESP32.

### Bước 5: Kiểm tra và Xác nhận
- ESP32 nhận đủ dữ liệu, ghi vào phân vùng OTA và tự Reboot.
- Sau khi khởi động, ESP32 báo cáo version mới lên Gateway.
- Gateway cập nhật telemetry `fw_state = UPDATED` lên Dashboard.

## 4. Các trạng thái theo dõi (Monitoring States)
| Trạng thái | Ý nghĩa |
| :--- | :--- |
| `DOWNLOADING` | Gateway đang tải file từ Server. |
| `UPDATING` | Gateway đang đẩy file vào ESP32 qua mạng LAN. |
| `UPDATED` | Cập nhật hoàn tất, thiết bị đã chạy code mới. |
| `FAILED` | Lỗi kết nối hoặc file không hợp lệ. |

## 5. Lưu ý an toàn
- **Nguồn điện:** Đảm bảo thiết bị không bị mất điện trong 30-60 giây đang nạp firmware.
- **Mạng:** Gateway và ESP32 phải nằm trong cùng mạng LAN.
- **Rollback:** Nếu cập nhật lỗi, ESP32 sẽ tự quay lại dùng bản firmware cũ (Dual-bank flash).

---
**Người lập kế hoạch:** Antigravity AI Assistant
