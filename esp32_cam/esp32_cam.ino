/*
  ESP32-CAM - MJPEG Stream + /capture endpoint
  + WiFiManager (tu dong tao AP neu chua co WiFi)
  + ThingsBoard Device Provisioning tu dong
  + Luu token vao NVS (Preferences) de khong provision lai sau reset

  Thu vien can cai qua Arduino Library Manager:
    - WiFiManager by tzapu  (Search: "WiFiManager")
    - ArduinoHttpClient     (Search: "ArduinoHttpClient")

  Board: AI-Thinker ESP32-CAM
*/

#include "src/OV2640.h"
#include <WiFi.h>
#include <WebServer.h>
#include <WiFiClient.h>
#include <WiFiManager.h>          // WiFi auto-provisioning
#include <PubSubClient.h>        // MQTT Provisioning & OTA
#include <Update.h>               // OTA Update
#include <Preferences.h>          // Luu token vao NVS flash
#include <ArduinoJson.h>          // Parse JSON response

// Select camera model
//#define CAMERA_MODEL_WROVER_KIT
//#define CAMERA_MODEL_ESP_EYE
//#define CAMERA_MODEL_M5STACK_PSRAM
//#define CAMERA_MODEL_M5STACK_WIDE
#define CAMERA_MODEL_AI_THINKER

#include "camera_pins.h"

// ── ThingsBoard ──────────────────────────────────────────────────────────────
#define TB_HOST         "http://tb-dev.imespro.ai:58090" // Keep for reference
#define TB_MQTT_HOST    "tb-dev.imespro.ai"
#define TB_MQTT_PORT    51883
#define TB_PROV_KEY     "9lymllsggh4lqmb49qlo"
#define TB_PROV_SECRET  "ncr0x82zx8fcpqhid2a3"
// Device name = "ESP32-CAM-" + MAC (6 hex chars) de dam bao duy nhat
String TB_DEVICE_NAME = "ESP32-CAM1-";

// ── Capture interval ─────────────────────────────────────────────────────────
#define CAPTURE_INTERVAL_MS 5000

// ── Globals ──────────────────────────────────────────────────────────────────
OV2640 cam;
WebServer server(80);
Preferences prefs;
WiFiClient espClient;
PubSubClient mqttClient(espClient);
unsigned long lastHeartbeat = 0;

String tbToken = "";   // ThingsBoard access token (loaded from NVS or provisioned)
volatile bool provisionResponseReceived = false;

// ─────────────────────────────────────────────────────────────────────────────
// HTTP helpers
// ─────────────────────────────────────────────────────────────────────────────

const char HEADER[] = "HTTP/1.1 200 OK\r\n"
                      "Access-Control-Allow-Origin: *\r\n"
                      "Content-Type: multipart/x-mixed-replace; boundary=123456789000000000000987654321\r\n";
const char BOUNDARY[] = "\r\n--123456789000000000000987654321\r\n";
const char CTNTTYPE[] = "Content-Type: image/jpeg\r\nContent-Length: ";
const int hdrLen = strlen(HEADER);
const int bdrLen = strlen(BOUNDARY);
const int cntLen = strlen(CTNTTYPE);

const char JHEADER[] = "HTTP/1.1 200 OK\r\n"
                        "Content-disposition: inline; filename=capture.jpg\r\n"
                        "Content-type: image/jpeg\r\n\r\n";
const int jhdLen = strlen(JHEADER);

// ─────────────────────────────────────────────────────────────────────────────
// Camera endpoints
// ─────────────────────────────────────────────────────────────────────────────

void handle_jpg_stream(void)
{
  char buf[32];
  int s;
  WiFiClient client = server.client();
  client.write(HEADER, hdrLen);
  client.write(BOUNDARY, bdrLen);
  while (true) {
    if (!client.connected()) break;
    cam.run();
    s = cam.getSize();
    client.write(CTNTTYPE, cntLen);
    sprintf(buf, "%d\r\n\r\n", s);
    client.write(buf, strlen(buf));
    client.write((char *)cam.getfb(), s);
    client.write(BOUNDARY, bdrLen);
  }
}

void handle_jpg(void)
{
  WiFiClient client = server.client();
  cam.run();
  if (!client.connected()) return;
  client.write(JHEADER, jhdLen);
  client.write((char *)cam.getfb(), cam.getSize());
}

// /capture - endpoint cho Python OCR script poll
void handle_capture(void)
{
  WiFiClient client = server.client();
  cam.run();
  if (!client.connected()) return;
  client.write(JHEADER, jhdLen);
  client.write((char *)cam.getfb(), cam.getSize());
  Serial.println("[CAM] Capture served via /capture");
}

void handleNotFound()
{
  server.send(200, "text/plain",
    "ESP32-CAM running\n"
    "  /mjpeg/1  - MJPEG stream\n"
    "  /jpg      - single JPEG\n"
    "  /capture  - single JPEG (OCR endpoint)\n"
    "  /info     - device info\n"
    "  /update   - POST firmware .bin file to update\n"
  );
}

// /info - tra ve thong tin thiet bi + TB token
void handle_info()
{
  String body = "{";
  body += "\"device\":\"" + TB_DEVICE_NAME + "\",";
  body += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  body += "\"tb_token\":\"" + tbToken + "\",";
  body += "\"provisioned\":" + String(tbToken.length() > 0 ? "true" : "false");
  body += "}";
  server.send(200, "application/json", body);
}

// /update - HTTP OTA endpoint
void handle_update_post() {
  server.sendHeader("Connection", "close");
  server.send(200, "text/plain", (Update.hasError()) ? "FAIL" : "OK");
  ESP.restart();
}

void handle_update_upload() {
  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("[OTA] Update Start: %s\n", upload.filename.c_str());
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) {
      Serial.printf("[OTA] Update Success: %u bytes\n", upload.totalSize);
    } else {
      Update.printError(Serial);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ThingsBoard Provisioning
// ─────────────────────────────────────────────────────────────────────────────

void provisionCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println("[TB] Provision Response: " + message);

  if (String(topic) == "/provision/response") {
    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, message);
    if (!err) {
      const char* status = doc["status"] | "none";
      if (strcmp(status, "SUCCESS") == 0) {
        if (doc.containsKey("credentialsValue"))
          tbToken = doc["credentialsValue"].as<String>();
        else if (doc.containsKey("token"))
          tbToken = doc["token"].as<String>();
      } else {
        Serial.printf("[TB] FAILURE: %s\n", doc["errorMsg"] | "unknown error");
      }
    }
    provisionResponseReceived = true;
  }
}

String tbProvision()
{
  Serial.println("[TB] Starting MQTT provisioning...");
  Serial.println("[TB] MQTT Host: " + String(TB_MQTT_HOST) + ":" + String(TB_MQTT_PORT));
  Serial.println("[TB] Device   : " + TB_DEVICE_NAME);

  mqttClient.setServer(TB_MQTT_HOST, TB_MQTT_PORT);
  mqttClient.setCallback(provisionCallback);

  // Connect to MQTT Broker (Using "provision" username as recommended by some TB versions, or empty)
  if (mqttClient.connect("ESP32_Prov", "provision", "")) {
    Serial.println("[TB] Connected to MQTT for provisioning");
    mqttClient.subscribe("/provision/response");

    String body = "{";
    body += "\"deviceName\":\"" + TB_DEVICE_NAME + "\",";
    body += "\"provisionDeviceKey\":\"" TB_PROV_KEY "\",";
    body += "\"provisionDeviceSecret\":\"" TB_PROV_SECRET "\"";
    body += "}";

    Serial.println("[TB] Publish /provision/request: " + body);
    mqttClient.publish("/provision/request", body.c_str());

    unsigned long startWait = millis();
    provisionResponseReceived = false;
    String prevToken = tbToken;
    tbToken = ""; // Clear before waiting

    while (!provisionResponseReceived && millis() - startWait < 15000) {
      mqttClient.loop();
      delay(10);
    }

    if (!provisionResponseReceived) {
      Serial.println("[TB] Provisioning timeout!");
      tbToken = prevToken; // Restore if timeout
    }
    mqttClient.disconnect();
  } else {
    Serial.println("[TB] Failed to connect to MQTT broker for provisioning");
  }

  return tbToken;
}

// ─────────────────────────────────────────────────────────────────────────────
// Setup
// ─────────────────────────────────────────────────────────────────────────────

void setup()
{
  Serial.begin(115200);
  Serial.println("\n[ESP32] Booting v2.0...");

  // ── Camera init ──────────────────────────────────────────
  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = Y2_GPIO_NUM;
  config.pin_d1        = Y3_GPIO_NUM;
  config.pin_d2        = Y4_GPIO_NUM;
  config.pin_d3        = Y5_GPIO_NUM;
  config.pin_d4        = Y6_GPIO_NUM;
  config.pin_d5        = Y7_GPIO_NUM;
  config.pin_d6        = Y8_GPIO_NUM;
  config.pin_d7        = Y9_GPIO_NUM;
  config.pin_xclk      = XCLK_GPIO_NUM;
  config.pin_pclk      = PCLK_GPIO_NUM;
  config.pin_vsync     = VSYNC_GPIO_NUM;
  config.pin_href      = HREF_GPIO_NUM;
  config.pin_sscb_sda  = SIOD_GPIO_NUM;
  config.pin_sscb_scl  = SIOC_GPIO_NUM;
  config.pin_pwdn      = PWDN_GPIO_NUM;
  config.pin_reset     = RESET_GPIO_NUM;
  config.xclk_freq_hz  = 20000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.frame_size    = FRAMESIZE_SVGA; // 800x600 - Tot nhat cho OCR va WiFi
  config.jpeg_quality  = 10;           // Chat luong tot (1-63, so cang thap cang net)
  config.fb_count      = 2;

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  cam.init(config);
  Serial.println("[CAM] Camera initialized");

  // ── WiFiManager ──────────────────────────────────────────
  // Neu chua co WiFi credentials, tao AP ten "ESP32-CAM-Setup"
  // Mo trinh duyet -> 192.168.4.1 -> nhap SSID/password
  WiFiManager wm;
  wm.setConfigPortalTimeout(120);   // AP timeout 2 phut
  wm.setConnectTimeout(30);

  Serial.println("[WiFi] Connecting via WiFiManager...");
  bool connected = wm.autoConnect("ESP32-CAM-Setup", "12345678");

  if (!connected) {
    Serial.println("[WiFi] Failed to connect. Restarting...");
    delay(3000);
    ESP.restart();
  }

  Serial.println("[WiFi] Connected!");
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("[WiFi] SSID: ");
  Serial.println(WiFi.SSID());

  // Tao device name duy nhat dua tren MAC address
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char macSuffix[13];
  sprintf(macSuffix, "%02X%02X%02X%02X%02X%02X", mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
  TB_DEVICE_NAME += String(macSuffix);
  Serial.println("[TB] Device name: " + TB_DEVICE_NAME);

  // ── ThingsBoard Provisioning ─────────────────────────────
  // Doc token tu NVS
  prefs.begin("tb", false);
  tbToken = prefs.getString("token", "");

  if (tbToken.length() > 0) {
    Serial.println("[TB] Found cached token: " + tbToken.substring(0, 8) + "...");
  } else {
    Serial.println("[TB] No cached token, provisioning...");
    tbToken = tbProvision();
    if (tbToken.length() > 0) {
      prefs.putString("token", tbToken);
      Serial.println("[TB] Token saved to NVS: " + tbToken.substring(0, 8) + "...");
    } else {
      Serial.println("[TB] Provisioning failed! Running without ThingsBoard.");
    }
  }
  prefs.end();

  // ── Web server ───────────────────────────────────────────
  server.on("/mjpeg/1", HTTP_GET, handle_jpg_stream);
  server.on("/jpg",     HTTP_GET, handle_jpg);
  server.on("/capture", HTTP_GET, handle_capture);
  server.on("/info",    HTTP_GET, handle_info);
  
  // OTA Update Endpoints
  server.on("/update", HTTP_POST, handle_update_post, handle_update_upload);

  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("[ESP32] Web server started");
  Serial.print("[ESP32] Stream : http://");
  Serial.print(WiFi.localIP());
  Serial.println("/mjpeg/1");
  Serial.print("[ESP32] Capture: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/capture");
}

// ─────────────────────────────────────────────────────────────────────────────
// Loop
// ─────────────────────────────────────────────────────────────────────────────

void loop()
{
  server.handleClient();
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastHeartbeat >= CAPTURE_INTERVAL_MS) {
    lastHeartbeat = now;
    Serial.printf("[ESP32] Uptime: %lus | IP: %s | TB: %s\n",
      now / 1000,
      WiFi.localIP().toString().c_str(),
      tbToken.length() > 0 ? "OK" : "NO TOKEN"
    );
  }
}
