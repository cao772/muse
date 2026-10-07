#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "muse_audio.h"
#include "bsp/esp-bsp.h"
#include "cJSON.h"
#include "driver/usb_serial_jtag.h"
#include "esp_codec_dev.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"

#define BLOCK_FRAMES 1600
static portMUX_TYPE audio_lock = portMUX_INITIALIZER_UNLOCKED;
static muse_audio_snapshot_t snapshot;
static unsigned int requested_seconds, pending_ack;
static bool acknowledged;
static int16_t pcm[BLOCK_FRAMES * 2];

void muse_audio_snapshot(muse_audio_snapshot_t *out)
{
    portENTER_CRITICAL(&audio_lock);
    *out = snapshot;
    portEXIT_CRITICAL(&audio_lock);
}

static void fail(void)
{
    portENTER_CRITICAL(&audio_lock);
    snapshot.failed = true;
    snapshot.ready = snapshot.recording = snapshot.exporting = false;
    requested_seconds = 0;
    portEXIT_CRITICAL(&audio_lock);
    ESP_LOGE("muse_audio", "AUDIO_ERROR (capture stopped)");
}

bool muse_audio_request_capture(unsigned int seconds)
{
    portENTER_CRITICAL(&audio_lock);
    bool ok = seconds >= 1 && seconds <= MUSE_AUDIO_MAX_SECONDS && snapshot.ready &&
              !snapshot.recording && !snapshot.exporting && !requested_seconds;
    if (ok) requested_seconds = seconds;
    portEXIT_CRITICAL(&audio_lock);
    return ok;
}

static void command_task(void *arg)
{
    char line[64];
    size_t used = 0;
    bool overflow = false;
    for (;;) {
        char c;
        if (usb_serial_jtag_read_bytes(&c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c != '\n') {
            if (used < sizeof(line) - 1) line[used++] = c;
            else overflow = true;
            continue;
        }
        line[used] = 0;
        cJSON *obj = overflow ? NULL : cJSON_Parse(line);
        cJSON *ack = cJSON_GetObjectItemCaseSensitive(obj, "pcm_ack");
        if (cJSON_IsNumber(ack)) {
            portENTER_CRITICAL(&audio_lock);
            if (snapshot.exporting && ack->valuedouble == pending_ack) acknowledged = true;
            portEXIT_CRITICAL(&audio_lock);
            cJSON_Delete(obj);
            memset(line, 0, sizeof(line)); used = 0; overflow = false;
            continue;
        }
        cJSON *seconds = cJSON_GetObjectItemCaseSensitive(obj, "capture_seconds");
        bool valid = cJSON_IsNumber(seconds) && seconds->valuedouble == seconds->valueint &&
                     seconds->valueint >= 1 && seconds->valueint <= MUSE_AUDIO_MAX_SECONDS;
        if (valid) valid = muse_audio_request_capture(seconds->valueint);
        cJSON_Delete(obj);
        memset(line, 0, sizeof(line)); used = 0; overflow = false;
        if (!valid) ESP_LOGW("muse_audio", "AUDIO_CAPTURE_REJECTED");
    }
}

static bool send_frame(const char *line)
{
    size_t bytes = strlen(line);
    // VFS writes characters and can drop after its short timeout. Send the
    // complete transport frame through the blocking driver, never as log text.
    flockfile(stdout);
    fflush(stdout);
    int written = usb_serial_jtag_write_bytes(line, bytes, pdMS_TO_TICKS(1000));
    esp_err_t drained = usb_serial_jtag_wait_tx_done(pdMS_TO_TICKS(1000));
    funlockfile(stdout);
    return written == bytes && drained == ESP_OK;
}

static bool export_pcm(const uint8_t *buffer, size_t bytes)
{
    unsigned char hash[32];
    if (mbedtls_sha256(buffer, bytes, hash, 0) != 0) return false;
    char hex[65];
    for (size_t i = 0; i < 32; ++i) snprintf(hex + i * 2, 3, "%02x", hash[i]);
    char frame[1152];
    snprintf(frame, sizeof(frame), "MUSE_PCM_BEGIN rate=%d channels=2 bits=16 bytes=%u sha256=%s\n",
             MUSE_AUDIO_RATE, (unsigned)bytes, hex);
    if (!send_frame(frame)) return false;
    for (size_t offset = 0; offset < bytes; offset += 768) {
        size_t length = bytes - offset < 768 ? bytes - offset : 768;
        unsigned char encoded[1025];
        size_t written;
        if (mbedtls_base64_encode(encoded, sizeof(encoded), &written, buffer + offset, length) != 0)
            return false;
        portENTER_CRITICAL(&audio_lock);
        pending_ack = offset + length;
        acknowledged = false;
        portEXIT_CRITICAL(&audio_lock);
        snprintf(frame, sizeof(frame), "MUSE_PCM_DATA offset=%u data=%.*s\n", (unsigned)offset, (int)written, encoded);
        if (!send_frame(frame)) return false;
        int64_t deadline = esp_timer_get_time() + 3000000;
        bool received = false;
        do {
            vTaskDelay(pdMS_TO_TICKS(2));
            portENTER_CRITICAL(&audio_lock);
            received = acknowledged;
            portEXIT_CRITICAL(&audio_lock);
        } while (!received && esp_timer_get_time() < deadline);
        if (!received) return false;
    }
    snprintf(frame, sizeof(frame), "MUSE_PCM_END bytes=%u sha256=%s\n", (unsigned)bytes, hex);
    return send_frame(frame);
}

static void capture_task(void *arg)
{
    // The locked BSP owns I2S pins and the ES7210 MIC1/MIC2 selection.
    esp_codec_dev_handle_t mic = bsp_audio_codec_microphone_init();
    esp_codec_dev_sample_info_t format = {
        .sample_rate = MUSE_AUDIO_RATE, .channel = 2, .bits_per_sample = 16,
    };
    if (!mic || esp_codec_dev_open(mic, &format) != ESP_CODEC_DEV_OK ||
        esp_codec_dev_set_in_gain(mic, 24.0f) != ESP_CODEC_DEV_OK) {
        fail(); vTaskDelete(NULL); return;
    }
    portENTER_CRITICAL(&audio_lock);
    snapshot.ready = true;
    portEXIT_CRITICAL(&audio_lock);
    ESP_LOGI("muse_audio", "AUDIO_READY rate=%d channels=2 bits=16 gain_db=24", MUSE_AUDIO_RATE);
    uint8_t *recording = NULL;
    size_t target = 0, used = 0;
    int64_t started = 0, last_report = 0;
    for (;;) {
        unsigned int seconds = 0;
        portENTER_CRITICAL(&audio_lock);
        if (requested_seconds) {
            seconds = requested_seconds;
            requested_seconds = 0;
            snapshot.recording = true;
        }
        portEXIT_CRITICAL(&audio_lock);
        if (seconds) {
            target = seconds * MUSE_AUDIO_RATE * 4;
            recording = heap_caps_malloc(target, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
            if (!recording) { fail(); vTaskDelete(NULL); return; }
            used = 0;
            started = esp_timer_get_time();
            ESP_LOGI("muse_audio", "AUDIO_RECORDING seconds=%u", seconds);
        }
        if (esp_codec_dev_read(mic, pcm, sizeof(pcm)) != ESP_CODEC_DEV_OK) {
            if (recording) { memset(recording, 0, target); free(recording); }
            fail(); vTaskDelete(NULL); return;
        }
        muse_audio_stats_t stats;
        muse_audio_measure(pcm, BLOCK_FRAMES, &stats);
        portENTER_CRITICAL(&audio_lock);
        snapshot.stats = stats;
        portEXIT_CRITICAL(&audio_lock);
        int64_t now = esp_timer_get_time();
        if (now - last_report >= 2000000) {
            ESP_LOGI("muse_audio", "AUDIO_STATS L_peak=%u L_rms=%.1f L_clip=%u R_peak=%u R_rms=%.1f R_clip=%u equal=%u/%u",
                     (unsigned)stats.peak[0], stats.rms[0], (unsigned)stats.clipped[0],
                     (unsigned)stats.peak[1], stats.rms[1], (unsigned)stats.clipped[1],
                     (unsigned)stats.equal_frames, (unsigned)stats.frames);
            last_report = now;
        }
        if (recording) {
            size_t amount = target - used < sizeof(pcm) ? target - used : sizeof(pcm);
            memcpy(recording + used, pcm, amount);
            used += amount;
            if (used == target) {
                ESP_LOGI("muse_audio", "AUDIO_CAPTURED frames=%u elapsed_ms=%lld", (unsigned)(used / 4),
                         (long long)((now - started) / 1000));
                portENTER_CRITICAL(&audio_lock);
                snapshot.recording = false; snapshot.exporting = true;
                portEXIT_CRITICAL(&audio_lock);
                bool ok = export_pcm(recording, used);
                memset(recording, 0, target); free(recording); recording = NULL;
                portENTER_CRITICAL(&audio_lock);
                snapshot.exporting = false;
                portEXIT_CRITICAL(&audio_lock);
                if (!ok) ESP_LOGE("muse_audio", "AUDIO_EXPORT_ERROR");
            }
        }
    }
}

void muse_audio_start(void)
{
    if (xTaskCreate(capture_task, "muse_audio", 8192, NULL, 4, NULL) != pdPASS) {
        fail(); return;
    }
    if (xTaskCreate(command_task, "muse_audio_cmd", 3072, NULL, 3, NULL) != pdPASS) fail();
}
