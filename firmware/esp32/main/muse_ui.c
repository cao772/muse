#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "muse_pet_runtime.h"
#include "muse_ui.h"
#include "muse_audio.h"
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
static lv_obj_t *audio_page, *audio_state, *audio_levels[2], *audio_numbers[2], *audio_clipping;
static lv_obj_t *record_button, *voice_status, *codex_status;
static lv_obj_t *task_page, *inbox_page;
static lv_obj_t *task_state, *task_profile, *task_owner, *task_name;
static lv_obj_t *inbox_count, *inbox_sync, *inbox_wechat;
static lv_obj_t *pet_page, *pet_face, *pet_eyes[2], *pet_counter;
static lv_obj_t *plots[MUSE_PET_PLOTS], *plot_text[MUSE_PET_PLOTS];
enum { PAGE_HOME, PAGE_AUDIO, PAGE_TASK, PAGE_INBOX, PAGE_PET, PAGE_NETWORK, PAGE_TOTAL };
static lv_obj_t *pages[PAGE_TOTAL];
static unsigned int active_page;
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

static const char *page_names[PAGE_TOTAL] = {
    "home", "audio", "tasks", "inbox", "pet-garden", "network",
};

static void load_page(unsigned int index)
{
    if (index >= PAGE_TOTAL || !pages[index]) return;
    active_page = index;
    lv_screen_load(pages[index]);
    ESP_LOGI("muse_ui", "UI_PAGE %s", page_names[index]);
}

static void previous_page(lv_event_t *event)
{
    load_page((active_page + PAGE_TOTAL - 1) % PAGE_TOTAL);
}

static void next_page(lv_event_t *event)
{
    load_page((active_page + 1) % PAGE_TOTAL);
}

static void swipe_page(lv_event_t *event)
{
    lv_indev_t *indev = lv_indev_active();
    if (!indev) return;
    lv_dir_t dir = lv_indev_get_gesture_dir(indev);
    if (dir == LV_DIR_LEFT) {
        lv_indev_wait_release(indev);
        next_page(event);
    } else if (dir == LV_DIR_RIGHT) {
        lv_indev_wait_release(indev);
        previous_page(event);
    }
}

static void show_details(lv_event_t *event)
{
    load_page(PAGE_NETWORK);
}

static void show_audio(lv_event_t *event)
{
    load_page(PAGE_AUDIO);
}

static void record_audio(lv_event_t *event)
{
    if (muse_audio_request_auto_capture()) ESP_LOGI("muse_ui", "UI_AUDIO_RECORD_REQUEST");
    else ESP_LOGI("muse_ui", "UI_AUDIO_RECORD_REJECTED");
}

static void show_home(lv_event_t *event)
{
    load_page(PAGE_HOME);
}


static void pet_pat(lv_event_t *event)
{
    muse_pet_runtime_pat();
    ESP_LOGI("muse_ui", "PET_INTERACTION pat");
}

static void pet_feed(lv_event_t *event)
{
    muse_pet_runtime_feed();
    ESP_LOGI("muse_ui", "PET_INTERACTION treat");
}

static void pet_plot(lv_event_t *event)
{
    uintptr_t plot = (uintptr_t)lv_event_get_user_data(event);
    if (plot < MUSE_PET_PLOTS) {
        muse_pet_runtime_plot((unsigned int)plot);
        ESP_LOGI("muse_ui", "PET_INTERACTION plot=%u", (unsigned int)plot);
    }
}

static lv_obj_t *pet_dot(lv_obj_t *parent, int x, int y, int w, int h,
                         uint32_t color)
{
    lv_obj_t *dot = lv_obj_create(parent);
    lv_obj_set_size(dot, w, h);
    lv_obj_align(dot, LV_ALIGN_TOP_MID, x, y);
    lv_obj_set_style_bg_color(dot, lv_color_hex(color), 0);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(dot, 0, 0);
    lv_obj_remove_flag(dot, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(dot, LV_OBJ_FLAG_EVENT_BUBBLE);
    return dot;
}


static lv_obj_t *screen(void)
{
    lv_obj_t *obj = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(obj, lv_color_hex(BG), 0);
    lv_obj_set_style_text_color(obj, lv_color_hex(FG), 0);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(obj, touch, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(obj, swipe_page, LV_EVENT_GESTURE, NULL);
    return obj;
}

static lv_obj_t *button(lv_obj_t *parent, const char *text, int y, lv_event_cb_t action)
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
    return obj;
}

static lv_obj_t *row(lv_obj_t *parent, const char *name, int y)
{
    lv_obj_t *key = label(parent, name, 0, y, &lv_font_montserrat_18, MUTED);
    lv_obj_align(key, LV_ALIGN_TOP_LEFT, 100, y);
    lv_obj_t *value = label(parent, "Waiting", 0, y, &lv_font_montserrat_18, MUTED);
    lv_obj_align(value, LV_ALIGN_TOP_RIGHT, -100, y);
    return value;
}

static void navigation(lv_obj_t *page, unsigned int index)
{
    lv_obj_t *previous = lv_button_create(page);
    lv_obj_set_size(previous, 36, 30);
    lv_obj_align(previous, LV_ALIGN_TOP_MID, -68, 24);
    lv_obj_set_style_radius(previous, 15, 0);
    lv_obj_set_style_shadow_width(previous, 0, 0);
    lv_obj_set_style_bg_color(previous, lv_color_hex(0x293E49), 0);
    lv_obj_add_flag(previous, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(previous, previous_page, LV_EVENT_CLICKED, NULL);
    lv_obj_t *back = label(previous, "<", 0, 0, &lv_font_montserrat_16, FG);
    lv_obj_center(back);

    char counter[20];
    snprintf(counter, sizeof(counter), "%u / %u", index + 1, PAGE_TOTAL);
    label(page, counter, 0, 30, &lv_font_montserrat_14, MUTED);

    lv_obj_t *next = lv_button_create(page);
    lv_obj_set_size(next, 36, 30);
    lv_obj_align(next, LV_ALIGN_TOP_MID, 68, 24);
    lv_obj_set_style_radius(next, 15, 0);
    lv_obj_set_style_shadow_width(next, 0, 0);
    lv_obj_set_style_bg_color(next, lv_color_hex(0x293E49), 0);
    lv_obj_add_flag(next, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(next, next_page, LV_EVENT_CLICKED, NULL);
    lv_obj_t *forward = label(next, ">", 0, 0, &lv_font_montserrat_16, FG);
    lv_obj_center(forward);
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
    // One cooperative tick for all pages; no network, audio or random delays.
    muse_pet_runtime_service();
    if (active_page == PAGE_PET) {
        const muse_pet_save_t *garden = muse_pet_runtime_state();
        bool happy = muse_pet_runtime_happy();
        lv_obj_set_style_bg_color(pet_face,
                                  lv_color_hex(happy ? 0xf2bcce : 0x88cfdf), 0);
        for (unsigned int i = 0; i < 2; ++i) {
            lv_obj_set_height(pet_eyes[i], happy ? 6 : 12);
        }
        int bob = ((esp_timer_get_time() / 500000) % 2) ? 1 : 0;
        lv_obj_align(pet_face, LV_ALIGN_TOP_MID, 0, 119 + bob);
        lv_label_set_text_fmt(pet_counter, "Pats %u / Treats %u / Crops %u",
                              (unsigned int)garden->pats,
                              (unsigned int)garden->treats,
                              (unsigned int)garden->harvests);
        static const char *stage_text[] = {"Plant", "Water", "Growing", "Pick"};
        static const uint32_t stage_color[] = {
            0x293e49, 0x94705f, 0x598c69, 0xa6ca72,
        };
        for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i) {
            unsigned int stage = garden->plots[i];
            if (stage > MUSE_PLOT_READY) stage = MUSE_PLOT_EMPTY;
            lv_label_set_text(plot_text[i], stage_text[stage]);
            lv_obj_set_style_bg_color(plots[i],
                                      lv_color_hex(stage_color[stage]), 0);
        }
    }
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
    muse_audio_snapshot_t input;
    muse_audio_snapshot(&input);
    for (size_t ch = 0; ch < 2; ++ch) {
        int meter = (int)(input.stats.rms_dbfs[ch] + 60);
        if (!input.ready) meter = 0;
        if (meter < 0) meter = 0;
        if (meter > 60) meter = 60;
        lv_bar_set_value(audio_levels[ch], meter, LV_ANIM_OFF);
        lv_label_set_text_fmt(audio_numbers[ch], "RMS %.1f dBFS   Peak %u",
                             input.ready ? input.stats.rms_dbfs[ch] : -96.0,
                             (unsigned)input.stats.peak[ch]);
    }
    lv_label_set_text_fmt(audio_clipping, "Clipping L %u / R %u (100ms)",
                         (unsigned)input.stats.clipped[0], (unsigned)input.stats.clipped[1]);
    const char *activity = input.failed ? "Input error" : !input.ready ? "Waiting for USB setup" :
                           input.recording ? "Recording / USB" : input.exporting ? "Exporting / USB" :
                           input.receiving ? "Receiving / USB" : input.playing ? "Playing / Speaker" : "Listening";
    if (input.voice_active) activity = input.recording || input.exporting ? "Listening" : input.voice_state;
    value(audio_state, activity, input.ready && !input.failed);
    lv_label_set_text(voice_status, input.voice_active ? activity : "");
    if (input.attention_known && input.attention_count && input.voice_ready)
        lv_label_set_text_fmt(voice_status, "Ready / Items needing you: %u", input.attention_count);
    if (input.codex_state) {
        value(task_state, input.codex_state, !input.codex_needs_user);
        value(task_profile, input.codex_profile ? input.codex_profile : "Unknown", true);
        value(task_owner, input.codex_needs_user ? "Needs your input" : "Monitor only",
              !input.codex_needs_user);
        lv_label_set_text(task_name, input.codex_title[0] ? input.codex_title : "Unnamed task");
    } else {
        value(task_state, "No active task", false);
        value(task_profile, "--", false);
        value(task_owner, "No execution snapshot", false);
        lv_label_set_text(task_name, "Waiting for CAO");
    }
    if (input.attention_known) {
        lv_label_set_text_fmt(inbox_count, "%u pending", input.attention_count);
        value(inbox_sync, "CAO snapshot via USB", true);
    } else {
        lv_label_set_text(inbox_count, "--");
        value(inbox_sync, "CAO not available / stale", false);
    }
    if (input.codex_state) {
        lv_label_set_text_fmt(heartbeat, "CODEX %s / %s", input.codex_state, input.codex_profile);
        lv_label_set_text_fmt(codex_status, "CODEX %s / %s%s\n%s", input.codex_state,
                             input.codex_profile, input.codex_needs_user ? " / Needs you" : "", input.codex_title);
    } else lv_label_set_text(codex_status, "");
    bool enabled = input.ready && !input.failed && !input.recording && !input.exporting &&
                   !input.receiving && !input.playing && (!input.voice_active || input.voice_ready);
    if (enabled) lv_obj_remove_state(record_button, LV_STATE_DISABLED);
    else lv_obj_add_state(record_button, LV_STATE_DISABLED);
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
    voice_status = label(home, "", 0, 224, &lv_font_montserrat_16, GREEN);
    heartbeat = label(home, "Waiting for heartbeat", 0, 348, &lv_font_montserrat_16, MUTED);
    lv_obj_t *network_button = button(home, "View status", 382, show_details);
    lv_obj_set_width(network_button, 128);
    lv_obj_align(network_button, LV_ALIGN_TOP_MID, -70, 382);
    lv_obj_t *audio_button = button(home, "Audio Input", 382, show_audio);
    lv_obj_set_width(audio_button, 128);
    lv_obj_align(audio_button, LV_ALIGN_TOP_MID, 70, 382);

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
    codex_status = label(details, "", 0, 347, &lv_font_montserrat_14, GREEN);
    button(details, "Back", 397, show_home);
    audio_page = screen();
    label(audio_page, "Audio Input", 0, 60, &lv_font_montserrat_24, FG);
    label(audio_page, "16 kHz / 16 bit / Stereo", 0, 105, &lv_font_montserrat_16, MUTED);
    for (size_t ch = 0; ch < 2; ++ch) {
        int y = 148 + ch * 96;
        label(audio_page, ch ? "Mic R / channel 1" : "Mic L / channel 0", 0, y,
              &lv_font_montserrat_18, FG);
        audio_levels[ch] = lv_bar_create(audio_page);
        lv_obj_set_size(audio_levels[ch], 250, 14);
        lv_obj_align(audio_levels[ch], LV_ALIGN_TOP_MID, 0, y + 29);
        lv_bar_set_range(audio_levels[ch], 0, 60);
        lv_obj_set_style_bg_color(audio_levels[ch], lv_color_hex(0x293E49), LV_PART_MAIN);
        lv_obj_set_style_bg_color(audio_levels[ch], lv_color_hex(GREEN), LV_PART_INDICATOR);
        audio_numbers[ch] = label(audio_page, "RMS -96 dBFS   Peak 0", 0, y + 52,
                                  &lv_font_montserrat_16, MUTED);
    }
    audio_clipping = label(audio_page, "Clipping L 0 / R 0 (100ms)", 0, 322,
                           &lv_font_montserrat_16, MUTED);
    audio_state = label(audio_page, "Waiting for USB setup", 0, 348, &lv_font_montserrat_16, MUTED);
    record_button = button(audio_page, "Speak", 382, record_audio);
    lv_obj_set_width(record_button, 128);
    lv_obj_align(record_button, LV_ALIGN_TOP_MID, -70, 382);
    lv_obj_t *back_button = button(audio_page, "Back", 382, show_home);
    lv_obj_set_width(back_button, 128);
    lv_obj_align(back_button, LV_ALIGN_TOP_MID, 70, 382);
    task_page = screen();
    label(task_page, "Codex / Projects", 0, 69, &lv_font_montserrat_24, FG);
    label(task_page, "Execution", 0, 118, &lv_font_montserrat_16, MUTED);
    task_state = label(task_page, "No active task", 0, 152, &lv_font_montserrat_20, GREEN);
    label(task_page, "Model profile", 0, 204, &lv_font_montserrat_16, MUTED);
    task_profile = label(task_page, "--", 0, 234, &lv_font_montserrat_20, FG);
    task_owner = label(task_page, "No execution snapshot", 0, 276,
                       &lv_font_montserrat_16, MUTED);
    task_name = label(task_page, "Waiting for CAO", 0, 312, &lv_font_montserrat_16, MUTED);
    lv_obj_set_width(task_name, 280);
    lv_label_set_long_mode(task_name, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(task_name, LV_TEXT_ALIGN_CENTER, 0);
    label(task_page, "Ended does not mean accepted", 0, 348,
          &lv_font_montserrat_14, MUTED);
    button(task_page, "Speak", 382, show_audio);

    inbox_page = screen();
    label(inbox_page, "Notifications", 0, 69, &lv_font_montserrat_24, FG);
    label(inbox_page, "Projects needing you", 0, 126, &lv_font_montserrat_16, MUTED);
    inbox_count = label(inbox_page, "--", 0, 160, &lv_font_montserrat_24, GREEN);
    inbox_sync = label(inbox_page, "CAO not available", 0, 202,
                       &lv_font_montserrat_14, MUTED);
    label(inbox_page, "WeChat", 0, 254, &lv_font_montserrat_20, FG);
    inbox_wechat = label(inbox_page, "Not linked to Muse", 0, 292,
                        &lv_font_montserrat_16, MUTED);
    label(inbox_page, "No real-time message feed yet", 0, 326,
          &lv_font_montserrat_14, MUTED);
    button(inbox_page, "Audio Input", 382, show_audio);

    pet_page = screen();
    label(pet_page, "Pet & Garden", 0, 67, &lv_font_montserrat_24, FG);
    // Original LVGL shapes; no imported sprites, font files or game engine.
    pet_dot(pet_page, -39, 107, 32, 32, 0x88cfdf);
    pet_dot(pet_page, 39, 107, 32, 32, 0x88cfdf);
    pet_face = lv_obj_create(pet_page);
    lv_obj_set_size(pet_face, 118, 94);
    lv_obj_align(pet_face, LV_ALIGN_TOP_MID, 0, 119);
    lv_obj_set_style_radius(pet_face, 40, 0);
    lv_obj_set_style_bg_color(pet_face, lv_color_hex(0x88cfdf), 0);
    lv_obj_set_style_border_width(pet_face, 0, 0);
    lv_obj_remove_flag(pet_face, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(pet_face, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(pet_face, pet_pat, LV_EVENT_CLICKED, NULL);
    pet_eyes[0] = pet_dot(pet_face, -22, 27, 11, 12, 0x1e3541);
    pet_eyes[1] = pet_dot(pet_face, 22, 27, 11, 12, 0x1e3541);
    pet_dot(pet_face, 0, 49, 15, 8, 0xe49aa4);
    pet_counter = label(pet_page, "Pats 0 / Treats 0 / Crops 0",
                        0, 227, &lv_font_montserrat_14, MUTED);
    lv_obj_t *feed = button(pet_page, "Give treat", 254, pet_feed);
    lv_obj_set_size(feed, 132, 34);
    label(pet_page, "Tap plots to plant, water and pick",
          0, 297, &lv_font_montserrat_14, MUTED);
    for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i) {
        plots[i] = lv_button_create(pet_page);
        lv_obj_set_size(plots[i], 92, 50);
        lv_obj_align(plots[i], LV_ALIGN_TOP_MID, (int)(i * 106) - 106, 321);
        lv_obj_set_style_radius(plots[i], 15, 0);
        lv_obj_set_style_bg_color(plots[i], lv_color_hex(0x293e49), 0);
        lv_obj_set_style_shadow_width(plots[i], 0, 0);
        lv_obj_add_flag(plots[i], LV_OBJ_FLAG_EVENT_BUBBLE);
        lv_obj_add_event_cb(plots[i], pet_plot, LV_EVENT_CLICKED,
                            (void *)(uintptr_t)i);
        plot_text[i] = label(plots[i], "Plant", 0, 0,
                             &lv_font_montserrat_16, FG);
        lv_obj_center(plot_text[i]);
    }
    lv_obj_t *pet_speak = button(pet_page, "Speak", 388, show_audio);
    lv_obj_set_width(pet_speak, 120);

    pages[PAGE_HOME] = home;
    pages[PAGE_AUDIO] = audio_page;
    pages[PAGE_TASK] = task_page;
    pages[PAGE_INBOX] = inbox_page;
    pages[PAGE_PET] = pet_page;
    pages[PAGE_NETWORK] = details;
    for (unsigned int page = 0; page < PAGE_TOTAL; ++page) {
        navigation(pages[page], page);
    }
    active_page = PAGE_HOME;
    lv_timer_create(refresh, 200, NULL);
    refresh(NULL);
    load_page(PAGE_HOME);
    bsp_display_unlock();
    ESP_LOGI("muse_ui", "UI_READY width=%d height=%d", (int)lv_display_get_horizontal_resolution(display),
             (int)lv_display_get_vertical_resolution(display));
}
