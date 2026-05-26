# Kế hoạch bảo mật OTA cho ESP32-CAM - Chống hack checksum & file giả

Kế hoạch này giúp nâng cấp hệ thống OTA hiện tại để chống lại các lỗ hổng bảo mật nghiêm trọng:
1. **Lỗ hổng MD5/SHA256 đơn thuần**: Kẻ tấn công có thể tự tạo mã độc, tính toán mã MD5/SHA256 của mã độc đó rồi gửi kèm header `X-MD5` lên ESP32 để ghi đè firmware. MD5 chỉ là thuật toán kiểm tra lỗi truyền dẫn, không phải cơ chế bảo mật chống giả mạo.
2. **Lỗ hổng không xác thực endpoint `/update`**: Bất kỳ ai trong cùng mạng nội bộ đều có thể gọi lệnh POST tới endpoint `/update` của ESP32 để nạp firmware giả.

---

## Giải pháp đề xuất

### 1. Xác thực bằng Chữ ký số bất đối xứng (Asymmetric Cryptographic Signature Verification)
Sử dụng thuật toán **ECDSA (secp256r1 / prime256v1)** với mã băm **SHA-256** để ký số và xác thực firmware:
* **Khóa bí mật (Private Key)**: Chỉ Nhà phát triển giữ, dùng để ký số vào file `.bin` sau khi biên dịch.
* **Khóa công khai (Public Key)**: Khóa này được nhúng trực tiếp vào mã nguồn của ESP32-CAM (`esp32_cam.ino`).
* **Cơ chế ký và tách**:
  1. Nhà phát triển chạy script `sign_firmware.py` trên PC để ký file `esp32_cam.ino.bin`. Script sẽ tính SHA-256 của file, tạo ra một Signature dài khoảng 70-72 bytes (định dạng DER), rồi nối đuôi chữ ký + 2 bytes độ dài chữ ký vào cuối file `.bin` -> tạo thành `signed_firmware.bin`.
  2. Nhà phát triển upload `signed_firmware.bin` lên ThingsBoard.
  3. Khi có bản cập nhật mới, Python Gateway (`esp32_ocr.py`) tải `signed_firmware.bin` từ ThingsBoard về, đọc 2 byte cuối để lấy độ dài chữ ký, tách chữ ký ra riêng và phần binary gốc ra riêng.
  4. Python Gateway gửi phần binary gốc qua HTTP POST cho ESP32, kèm theo chữ ký trong header `X-Signature` (mã hóa Hex).
  5. ESP32-CAM nhận dữ liệu, tính toán mã băm SHA-256 trên từng gói dữ liệu đang tải lên (on-the-fly) thông qua thư viện phần cứng `mbedtls` tích hợp sẵn trong ESP32.
  6. Khi kết thúc quá trình tải lên, ESP32-CAM dùng Khóa công khai của nó để giải mã và so khớp chữ ký nhận được trong header `X-Signature` với mã băm SHA-256 vừa tính.
  7. Nếu chữ ký hợp lệ -> Chấp nhận cập nhật và Reboot. Nếu không hợp lệ -> Hủy bỏ ngay lập tức (Abort) và giữ nguyên firmware cũ an toàn.

### 2. Xác thực quyền gọi OTA bằng Token của ThingsBoard (Token Authentication)
Hiện tại, cả Python Gateway và ESP32-CAM đều sở hữu ThingsBoard Device Access Token (`tbToken`).
* Khi Python Gateway gọi POST `/update` đến ESP32, nó sẽ đính kèm thêm header `X-Auth-Token: <tbToken>`.
* ESP32-CAM sẽ so sánh `X-Auth-Token` nhận được với `tbToken` đang lưu trữ an toàn trong phân vùng NVS (Preferences) của nó.
* Nếu không khớp, ESP32-CAM từ chối ngay lập tức (trả về lỗi HTTP 401) trước khi thực hiện bất kỳ thao tác tắt camera hay ghi flash nào. Điều này ngăn chặn kẻ xấu spam phá hoại thiết bị.

---

## User Review Required

> [!IMPORTANT]
> **Yêu cầu cài đặt thư viện Python để ký**:
> Nhà phát triển cần cài đặt thư viện `cryptography` trên máy tính cá nhân để tạo khóa và ký firmware trước khi upload lên ThingsBoard:
> ```bash
> pip install cryptography
> ```
> *Lưu ý: Máy tính chạy Python Gateway (`esp32_ocr.py`) tại trạm giám sát KHÔNG cần cài đặt thêm thư viện này, vì việc tách chữ ký được xử lý thủ công bằng thao tác cắt byte cực kỳ nhẹ nhàng.*

> [!WARNING]
> **Quản lý Private Key**:
> File chứa Khóa bí mật (`private_key.pem`) phải được bảo mật tuyệt đối. Nếu mất khóa này, bạn sẽ không thể cập nhật OTA cho thiết bị nữa. Nếu lộ khóa này, kẻ xấu có thể ký số cho firmware độc hại để hack thiết bị của bạn.

---

## Open Questions

> [!NOTE]
> Bạn có muốn tạo luôn cặp khóa ECDSA (Private/Public) mẫu ngay bây giờ để tích hợp trực tiếp vào mã nguồn không? Nếu có, tôi sẽ viết một script Python sinh khóa tự động và hướng dẫn bạn chạy.

---

## Proposed Changes

### [Component] Công cụ ký số (Developer Tool)

#### [NEW] [sign_firmware.py](file:///c:/Users/Toan/Downloads/imes_toan/esp32_cam/sign_firmware.py)
* Viết script Python chạy trên máy tính của bạn để:
  1. Sinh cặp khóa ECDSA (nếu chưa có).
  2. Ký số vào file `firmware.bin` và xuất ra `signed_firmware.bin` để bạn upload lên ThingsBoard.

---

### [Component] Python Gateway (OCR & ThingsBoard Agent)

#### [MODIFY] [esp32_ocr.py](file:///c:/Users/Toan/Downloads/imes_toan/ocr/esp32_ocr.py)
* Nâng cấp hàm `process_ota`:
  * Tải file `signed_firmware.bin` từ ThingsBoard.
  * Tách phần chữ ký (Signature) nằm ở cuối file và tính toán mã MD5/SHA256 của phần firmware gốc.
  * Gửi request POST tới ESP32 kèm theo:
    * Header `X-Signature`: Chữ ký số dạng chuỗi Hex.
    * Header `X-Auth-Token`: ThingsBoard token để xác thực quyền gọi OTA.
    * Body: File firmware gốc (đã loại bỏ phần chữ ký thừa ở cuối).

---

### [Component] ESP32-CAM Firmware

#### [MODIFY] [esp32_cam.ino](file:///c:/Users/Toan/Downloads/imes_toan/esp32_cam/esp32_cam.ino)
* Nhúng khóa công khai **Public Key** dạng chuỗi PEM secp256r1 vào mã nguồn.
* Cấu hình WebServer để lắng nghe thêm header `X-Signature` và `X-Auth-Token` ở hàm setup (`server.collectHeaders`).
* Nâng cấp hàm `handle_update_upload`:
  * **Xác thực Token**: Kiểm tra `X-Auth-Token` có trùng khớp với `tbToken` lưu trong NVS không. Nếu sai, lập tức từ chối và ngắt kết nối.
  * **Tính SHA-256 on-the-fly**: Sử dụng `mbedtls_sha256_context` để băm dữ liệu trực tiếp khi ghi vào flash.
  * **Xác thực chữ ký số**: Ở sự kiện `UPLOAD_FILE_END`, sử dụng `mbedtls_pk_verify` để xác minh chữ ký `X-Signature` nhận được từ header với mã băm SHA-256 vừa tính.
  * Nếu xác minh thất bại, gọi `Update.abort()`, báo lỗi ra Serial và trả về HTTP 403 Forbidden.

---

## Verification Plan

### Automated/Manual Verification
1. **Kiểm thử ký số thành công**:
   - Sử dụng script `sign_firmware.py` để ký một file firmware thử nghiệm.
   - Chạy thử Python Gateway để xem nó có tải, tách chữ ký và gửi đi chính xác không.
2. **Kiểm thử xác thực thành công (Happy Path)**:
   - Nạp firmware mới có nhúng khóa công khai hợp lệ lên ESP32.
   - Thực hiện cập nhật OTA qua Python Gateway, kiểm tra log Serial của ESP32 xem có thông báo: `[OTA] Signature Verified successfully!`.
3. **Kiểm thử chống file giả (Fake File Attack)**:
   - Gửi một file `.bin` tùy ý không được ký bằng khóa bí mật (hoặc ký sai khóa) qua lệnh curl/postman lên ESP32.
   - Kiểm tra xem ESP32 có từ chối ngay lập tức với lỗi `Signature verification failed` và reboot giữ nguyên phiên bản cũ không.
4. **Kiểm thử chống gọi OTA trái phép (Unauthorized Trigger)**:
   - Thử gửi file firmware hợp lệ nhưng thiếu header `X-Auth-Token` hoặc điền sai token.
   - Kiểm tra xem ESP32 có từ chối ngay lập tức và trả về lỗi HTTP 401 không.
