# BÁO CÁO CẤP PHÁT HỆ THỐNG (PROVISIONING REPORT)

**Dự án:** Hệ thống Giám sát Sản xuất Thông minh (iMES)
**Thành phần:** ESP32-CAM + OCR Gateway + ThingsBoard
**Trạng thái:** Hoàn thành cấu hình tự động

---

## 1. Tổng Quan (Overview)
Quy trình Provisioning được thiết kế để đảm bảo tính **Plug & Play**. Người dùng cuối chỉ cần thực hiện cấu hình WiFi một lần duy nhất, toàn bộ quy trình đăng ký thiết bị, cấp phát Access Token và kết nối Server đều được thực hiện tự động.

## 2. Các Lớp Cấp Phát (Provisioning Layers)

### 2.1. Cấp phát Mạng (Network Provisioning)
Hệ thống sử dụng cơ chế **WiFiManager** để loại bỏ việc nạp cứng (hardcode) thông tin WiFi vào code.
- **Cơ chế:** Khi không tìm thấy WiFi đã lưu, thiết bị phát AP: `ESP32-CAM-Setup`.
- **Giao diện:** Cung cấp trang Web nội bộ (192.168.4.1) để người dùng chọn mạng WiFi.
- **Lưu trữ:** Thông tin WiFi được lưu vào bộ nhớ Flash của ESP32.

### 2.2. Định danh Thiết bị (Device Identity)
- **ID Duy nhất:** Tên thiết bị được tạo tự động bằng định dạng: `ESP32-CAM1-<MAC_ADDRESS>`.
- **Mục đích:** Đảm bảo không trùng lặp khi triển khai hàng loạt camera trên cùng một dây chuyền.

### 2.3. Đăng ký ThingsBoard (ThingsBoard Auto-Provisioning)
Thay vì tạo thiết bị thủ công trên Dashboard, hệ thống sử dụng **MQTT Device Provisioning**:
- **Cổng kết nối:** `tb-dev.imespro.ai:51883`.
- **Thông tin xác thực:** 
    - `Provision Key`: `9lymllsggh4lqmb49qlo`
    - `Provision Secret`: `ncr0x82zx8fcpqhid2a3`
- **Kết quả:** Sau khi đăng ký thành công, ThingsBoard trả về một **Access Token**. Token này được lưu vào `Preferences` (NVS) để thiết bị không phải đăng ký lại sau khi Reset.

### 2.4. Cấp phát OCR Gateway (OCR Handshake)
Kịch bản Python xử lý OCR đóng vai trò là Gateway trung gian. Quy trình cấp phát cho Gateway như sau:
1. **Dò tìm:** Script Python gửi yêu cầu GET tới `http://<ESP32_IP>/info`.
2. **Nhận Token:** ESP32 phản hồi kèm theo Access Token hiện tại của nó.
3. **Đồng bộ:** Script Python sử dụng Token này để khởi tạo kết nối MQTT lên ThingsBoard, đảm bảo dữ liệu OCR và hình ảnh được đẩy đúng vào Device Entity của camera đó.

## 3. Cấu hình Cập nhật (OTA Provisioning)
Hệ thống hỗ trợ cấp phát phiên bản phần mềm mới từ xa:
- **ThingsBoard:** Quản lý phiên bản Firmware (title/version).
- **Gateway:** Tự động nhận diện thay đổi thuộc tính (Shared Attributes), tải Firmware từ ThingsBoard và "flash" xuống ESP32 qua HTTP OTA.

## 4. Thông số Kỹ thuật Hiện tại
| Thông số | Giá trị |
| :--- | :--- |
| **Server** | `tb-dev.imespro.ai` |
| **MQTT Port** | `51883` |
| **HTTP Port** | `58090` |
| **Định dạng Ảnh** | SVGA (800x600), JPEG Quality 10 |
| **Chu kỳ Poll** | 5.0 giây |

---
**Người lập báo cáo:** Antigravity AI Assistant
**Ngày:** 12/05/2026
