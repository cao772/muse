#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "cJSON.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"
#include "muse_ui.h"
#include "muse_pet_runtime.h"
#include "muse_audio.h"

#define WIFI_READY BIT0
#define WS_READY BIT1
#define HELLO_READY BIT2
#define PONG_READY BIT3
static const char *TAG = "muse";
static EventGroupHandle_t state;
static esp_websocket_client_handle_t ws;
static char ssid[33], password[65], uri[160], device_id[65], token[129];
static char headers[300];
static unsigned int ping_id;
static char expected_id[32];
static char rx[1024];

static bool copy_string(cJSON *obj, const char *key, char *dst, size_t cap, bool empty)
{
    cJSON *v = cJSON_GetObjectItemCaseSensitive(obj, key);
    if (!cJSON_IsString(v) || strlen(v->valuestring) >= cap ||
        (!empty && !v->valuestring[0])) return false;
    strcpy(dst, v->valuestring);
    return true;
}

static bool safe_header(const char *text)
{
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p)
        if (*p < 33 || *p > 126) return false;
    return true;
}

static void read_configuration(void)
{
    usb_serial_jtag_driver_config_t usb = {
        // Four base64 playback frames fit without overflowing the USB RX ring.
        .rx_buffer_size = 8192, .tx_buffer_size = 2048,
    };
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    // Console TX must use the installed driver too; HAL polling races its IRQ.
    usb_serial_jtag_vfs_use_driver();
    char line[768];
    size_t used = 0;
    bool overflow = false;
    int64_t last_prompt = 0;
    for (;;) {
        if (esp_timer_get_time() - last_prompt > 2000000) {
            ESP_LOGI(TAG, "MUSE_CONFIG_READY");
            last_prompt = esp_timer_get_time();
        }
        char c;
        if (usb_serial_jtag_read_bytes(&c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c != '\n') {
            if (used < sizeof(line) - 1) line[used++] = c;
            else overflow = true;
            continue;
        }
        line[used] = 0;
        cJSON *obj = overflow ? NULL : cJSON_Parse(line);
        bool ok = obj && copy_string(obj, "ssid", ssid, sizeof(ssid), false) &&
            copy_string(obj, "password", password, sizeof(password), true) &&
            copy_string(obj, "uri", uri, sizeof(uri), false) &&
            copy_string(obj, "device_id", device_id, sizeof(device_id), false) &&
            copy_string(obj, "token", token, sizeof(token), false) &&
            strlen(token) >= 32 && safe_header(token) && safe_header(device_id) &&
            strncmp(uri, "ws://", 5) == 0 && !strpbrk(uri, "\r\n");
        cJSON_Delete(obj);
        memset(line, 0, sizeof(line)); used = 0; overflow = false;
        if (ok) {
            muse_ui_set_device_id(device_id);
            muse_ui_update(MUSE_CONFIGURED);
            ESP_LOGI(TAG, "MUSE_CONFIG_OK (RAM only)");
            return;
        }
        ESP_LOGW(TAG, "MUSE_CONFIG_INVALID");
    }
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t event, void *data)
{
    if (base == WIFI_EVENT && event == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && event == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(state, WIFI_READY | HELLO_READY | PONG_READY);
        muse_ui_update(MUSE_WIFI_DOWN);
        ESP_LOGW(TAG, "WIFI_DISCONNECTED; retrying");
        esp_wifi_connect();
    } else if (base == IP_EVENT && event == IP_EVENT_STA_GOT_IP) {
        muse_ui_update(MUSE_WIFI_UP);
        ESP_LOGI(TAG, "WIFI_GOT_IP");
        xEventGroupSetBits(state, WIFI_READY);
    }
}

static void websocket_event(void *arg, esp_event_base_t base, int32_t event, void *event_data)
{
    esp_websocket_event_data_t *data = event_data;
    if (event == WEBSOCKET_EVENT_CONNECTED) {
        xEventGroupClearBits(state, HELLO_READY | PONG_READY);
        xEventGroupSetBits(state, WS_READY);
        muse_ui_update(MUSE_WS_UP);
        ESP_LOGI(TAG, "WS_CONNECTED");
    } else if (event == WEBSOCKET_EVENT_DISCONNECTED) {
        xEventGroupClearBits(state, WS_READY | HELLO_READY | PONG_READY);
        muse_ui_update(MUSE_WS_DOWN);
        ESP_LOGW(TAG, "WS_DISCONNECTED; retrying");
    } else if (event == WEBSOCKET_EVENT_DATA && data->op_code == 1) {
        // Accept bounded, unfragmented JSON frames; SDK may split into events.
        if (!data->fin || data->payload_len <= 0 || data->payload_len >= sizeof(rx) ||
            data->payload_offset < 0 || data->data_len < 0 ||
            data->payload_offset + data->data_len > data->payload_len) return;
        memcpy(rx + data->payload_offset, data->data_ptr, data->data_len);
        if (data->payload_offset + data->data_len != data->payload_len) return;
        rx[data->payload_len] = 0;
        cJSON *obj = cJSON_Parse(rx);
        cJSON *type = cJSON_GetObjectItemCaseSensitive(obj, "type");
        if (cJSON_IsString(type) && strcmp(type->valuestring, "hello") == 0) {
            cJSON *version = cJSON_GetObjectItemCaseSensitive(obj, "protocol_version");
            if (cJSON_IsNumber(version) && version->valueint == 1) {
                muse_ui_update(MUSE_HELLO);
                ESP_LOGI(TAG, "HELLO_OK protocol=1");
                xEventGroupSetBits(state, HELLO_READY);
            }
        } else if (cJSON_IsString(type) && strcmp(type->valuestring, "pong") == 0) {
            cJSON *id = cJSON_GetObjectItemCaseSensitive(obj, "id");
            if (cJSON_IsString(id) && strcmp(id->valuestring, expected_id) == 0) {
                muse_ui_update(MUSE_PONG);
                ESP_LOGI(TAG, "PONG_OK id=%s", expected_id);
                xEventGroupSetBits(state, PONG_READY);
            }
        }
        cJSON_Delete(obj);
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "MUSE_STAGE5_BOOT; USB configuration required after every restart");
    state = xEventGroupCreate();
    assert(state);
    // Initialize NVS before LVGL so pet and crops work even without Wi-Fi.
    // Never erase the shared NVS partition or overwrite existing network keys.
    ESP_ERROR_CHECK(nvs_flash_init());
    muse_pet_runtime_init();
    muse_ui_start();
    read_configuration();
    muse_audio_start();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    wifi_config_t config = {0};
    memcpy(config.sta.ssid, ssid, strlen(ssid));
    memcpy(config.sta.password, password, strlen(password));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config));
    memset(password, 0, sizeof(password));
    ESP_ERROR_CHECK(esp_wifi_start());
    xEventGroupWaitBits(state, WIFI_READY, pdFALSE, pdTRUE, portMAX_DELAY);
    snprintf(headers, sizeof(headers), "Authorization: Bearer %s\r\nX-Device-ID: %s\r\n", token, device_id);
    esp_websocket_client_config_t websocket = {
        .uri = uri, .headers = headers, .buffer_size = 1024,
        .reconnect_timeout_ms = 3000, .network_timeout_ms = 5000,
        .enable_close_reconnect = true,
    };
    // SDK diagnostic logging may include handshake details; keep it quiet.
    esp_log_level_set("websocket_client", ESP_LOG_NONE);
    esp_log_level_set("transport_ws", ESP_LOG_NONE);
    ws = esp_websocket_client_init(&websocket);
    assert(ws);
    ESP_ERROR_CHECK(esp_websocket_register_events(ws, WEBSOCKET_EVENT_ANY, websocket_event, NULL));
    ESP_ERROR_CHECK(esp_websocket_client_start(ws));
    for (;;) {
        EventBits_t bits = xEventGroupWaitBits(state, WIFI_READY | WS_READY | HELLO_READY,
                                              pdFALSE, pdTRUE, pdMS_TO_TICKS(15000));
        if ((bits & (WIFI_READY | WS_READY | HELLO_READY)) !=
            (WIFI_READY | WS_READY | HELLO_READY)) {
            ESP_LOGW(TAG, "WAITING_FOR_HELLO");
            continue;
        }
        xEventGroupClearBits(state, PONG_READY);
        snprintf(expected_id, sizeof(expected_id), "p-%u", ++ping_id);
        char message[80];
        int length = snprintf(message, sizeof(message), "{\"type\":\"ping\",\"id\":\"%s\"}", expected_id);
        int sent = esp_websocket_client_send_text(ws, message, length, pdMS_TO_TICKS(5000));
        bits = xEventGroupWaitBits(state, PONG_READY, pdTRUE, pdTRUE, pdMS_TO_TICKS(5000));
        if (sent != length || !(bits & PONG_READY)) {
            muse_ui_update(MUSE_PONG_EXPIRED);
            ESP_LOGW(TAG, "PONG_TIMEOUT; restarting connection");
            ESP_ERROR_CHECK(esp_websocket_client_stop(ws));
            xEventGroupClearBits(state, WS_READY | HELLO_READY | PONG_READY);
            ESP_ERROR_CHECK(esp_websocket_client_start(ws));
        }
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
