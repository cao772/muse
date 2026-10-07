#include <stdio.h>
#include <string.h>
#include "muse_ui.h"
#include "bsp/esp-bsp.h"
#include "bsp/display.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "lvgl.h"

static portMUX_TYPE status_lock = portMUX_INITIALIZER_UNLOCKED;
static muse_status_t status;
static int64_t last_pong;
static char device_name[65] = "muse-01";
static lv_obj_t *home, *details, *title, *wifi, *gateway, *auth, *heartbeat;
static const char *previous_title;
static lv_obj_t *detail_device, *detail_wifi, *detail_gateway, *detail_auth, *detail_heartbeat;
static const uint32_t BG = 0x101922, FG = 0xF4F2E9, MUTED = 0x9CAFB9, GREEN = 0x91E5B8;

void muse_ui_update(muse_event_t event)
{
    portENTER_CRITICAL(&status_lock);
    muse_status_apply(&status, event);
    if (event == MUSE_PONG) last_pong = esp_timer_get_time();
    portEXIT_CRITICAL(&status_lock);
}

void muse_ui_set_device_id(const char *id)
{
    portENTER_CRITICAL(&status_lock);
    snprintf(device_name, sizeof(device_name), "%s", id);
    portEXIT_CRITICAL(&status_lock);
}

static lv_obj_t *label(lv_obj_t *parent, const char *text, int x, int y,
                       const lv_font_t *font, uint32_t color)
{
    lv_obj_t *obj = lv_label_create(parent);
    lv_label_set_text(obj, text);
    lv_obj_set_style_text_font(obj, font, 0);
    lv_obj_set_style_text_color(obj, lv_color_hex(color), 0);
    lv_obj_align(obj, LV_ALIGN_TOP_MID, x, y);
    lv_obj_add_flag(obj, LV_OBJ_FLAG_EVENT_BUBBLE);
    return obj;
}

static void touch(lv_event_t *event)
{
    lv_indev_t *input = lv_indev_active();
    if (!input) return;
    lv_point_t point;
    lv_indev_get_point(input, &point);
    ESP_LOGI("muse_ui", "TOUCH_OK x=%d y=%d area=%s%s", (int)point.x, (int)point.y,
             point.y < 233 ? "top-" : "bottom-", point.x < 233 ? "left" : "right");
}

static void show_details(lv_event_t *event)
{
    lv_screen_load(details);
    ESP_LOGI("muse_ui", "UI_PAGE details");
}

static void show_home(lv_event_t *event)
{
    lv_screen_load(home);
    ESP_LOGI("muse_ui", "UI_PAGE home");
}

static lv_obj_t *screen(void)
{
    lv_obj_t *obj = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(obj, lv_color_hex(BG), 0);
    lv_obj_set_style_text_color(obj, lv_color_hex(FG), 0);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(obj, touch, LV_EVENT_PRESSED, NULL);
    return obj;
}

static void button(lv_obj_t *parent, const char *text, int y, lv_event_cb_t action)
{
    lv_obj_t *obj = lv_button_create(parent);
    lv_obj_set_size(obj, 172, 42);
    lv_obj_align(obj, LV_ALIGN_TOP_MID, 0, y);
    lv_obj_set_style_radius(obj, 21, 0);
    lv_obj_set_style_bg_color(obj, lv_color_hex(0x293E49), 0);
    lv_obj_set_style_shadow_width(obj, 0, 0);
    lv_obj_add_flag(obj, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(obj, action, LV_EVENT_CLICKED, NULL);
    lv_obj_t *caption = label(obj, text, 0, 0, &lv_font_montserrat_16, FG);
    lv_obj_center(caption);
}

static lv_obj_t *row(lv_obj_t *parent, const char *name, int y)
{
    lv_obj_t *key = label(parent, name, 0, y, &lv_font_montserrat_18, MUTED);
    lv_obj_align(key, LV_ALIGN_TOP_LEFT, 100, y);
    lv_obj_t *value = label(parent, "Waiting", 0, y, &lv_font_montserrat_18, MUTED);
    lv_obj_align(value, LV_ALIGN_TOP_RIGHT, -100, y);
    return value;
}

static void value(lv_obj_t *obj, const char *text, bool ready)
{
    lv_label_set_text(obj, text);
    lv_obj_set_style_text_color(obj, lv_color_hex(ready ? GREEN : MUTED), 0);
}

static void refresh(lv_timer_t *timer)
{
    muse_status_t snapshot;
    char id[65];
    portENTER_CRITICAL(&status_lock);
    snapshot = status;
    if (snapshot.heartbeat && esp_timer_get_time() - last_pong > 15000000)
        muse_status_apply(&snapshot, MUSE_PONG_EXPIRED);
    memcpy(id, device_name, sizeof(id));
    portEXIT_CRITICAL(&status_lock);
    const char *current_title = muse_status_title(&snapshot);
    if (!previous_title || strcmp(previous_title, current_title) != 0) {
        ESP_LOGI("muse_ui", "UI_STATE %s", current_title);
        previous_title = current_title;
    }
    lv_label_set_text(title, current_title);
    lv_obj_set_style_text_color(title, lv_color_hex(snapshot.heartbeat ? GREEN : FG), 0);
    value(wifi, snapshot.wifi ? "Online" : "Offline", snapshot.wifi);
    value(gateway, snapshot.gateway ? "Online" : "Offline", snapshot.gateway);
    value(auth, snapshot.authenticated ? "Verified" : "Pending", snapshot.authenticated);
    value(heartbeat, snapshot.heartbeat ? "Heartbeat healthy / 5s" : "Waiting for heartbeat",
          snapshot.heartbeat);
    lv_label_set_text_fmt(detail_device, "Device  %s", id);
    value(detail_wifi, snapshot.wifi ? "Online" : "Offline", snapshot.wifi);
    value(detail_gateway, snapshot.gateway ? "Online" : "Offline", snapshot.gateway);
    value(detail_auth, snapshot.authenticated ? "Verified" : "Pending", snapshot.authenticated);
    value(detail_heartbeat, snapshot.heartbeat ? "Healthy / 5s" : "Waiting", snapshot.heartbeat);
}

void muse_ui_start(void)
{
    lv_display_t *display = bsp_display_start();
    ESP_ERROR_CHECK(display ? ESP_OK : ESP_FAIL);
    ESP_ERROR_CHECK(bsp_display_lock((uint32_t)-1));
    home = screen();
    label(home, "LOCAL AGENT", 0, 58, &lv_font_montserrat_16, MUTED);
    // Small vector face: no external assets, emoji font, or animation required.
    lv_obj_t *face = lv_obj_create(home);
    lv_obj_set_size(face, 84, 50);
    lv_obj_align(face, LV_ALIGN_TOP_MID, 0, 91);
    lv_obj_set_style_radius(face, 18, 0);
    lv_obj_set_style_bg_color(face, lv_color_hex(0x293E49), 0);
    lv_obj_set_style_border_width(face, 0, 0);
    lv_obj_remove_flag(face, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(face, LV_OBJ_FLAG_EVENT_BUBBLE);
    for (int x = -16; x <= 16; x += 32) {
        lv_obj_t *eye = lv_obj_create(face);
        lv_obj_set_size(eye, 8, 14);
        lv_obj_align(eye, LV_ALIGN_CENTER, x, 0);
        lv_obj_set_style_radius(eye, 4, 0);
        lv_obj_set_style_bg_color(eye, lv_color_hex(GREEN), 0);
        lv_obj_set_style_border_width(eye, 0, 0);
        lv_obj_remove_flag(eye, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    }
    label(home, "Muse", 0, 151, &lv_font_montserrat_36, FG);
    title = label(home, "USB setup", 0, 200, &lv_font_montserrat_20, FG);
    wifi = row(home, "Wi-Fi", 247);
    gateway = row(home, "Gateway", 279);
    auth = row(home, "Auth", 311);
    heartbeat = label(home, "Waiting for heartbeat", 0, 348, &lv_font_montserrat_16, MUTED);
    button(home, "View status", 382, show_details);

    details = screen();
    label(details, "Network", 0, 82, &lv_font_montserrat_24, FG);
    detail_device = label(details, "Device  muse-01", 0, 134, &lv_font_montserrat_16, MUTED);
    lv_obj_set_width(detail_device, 280);
    lv_label_set_long_mode(detail_device, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(detail_device, LV_TEXT_ALIGN_CENTER, 0);
    detail_wifi = row(details, "Wi-Fi", 197);
    detail_gateway = row(details, "Gateway", 236);
    detail_auth = row(details, "Auth", 275);
    detail_heartbeat = row(details, "Heartbeat", 314);
    button(details, "Back", 382, show_home);
    lv_timer_create(refresh, 200, NULL);
    refresh(NULL);
    lv_screen_load(home);
    bsp_display_unlock();
    ESP_LOGI("muse_ui", "UI_READY width=%d height=%d", (int)lv_display_get_horizontal_resolution(display),
             (int)lv_display_get_vertical_resolution(display));
}
