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

#include "muse_endpoint.h"

#define BLOCK_FRAMES 1600
static portMUX_TYPE audio_lock = portMUX_INITIALIZER_UNLOCKED;
static muse_audio_snapshot_t snapshot;
static unsigned int requested_seconds, pending_ack;
static bool acknowledged, requested_adaptive;
static int64_t voice_deadline;
static int16_t pcm[BLOCK_FRAMES * 2];
static esp_codec_dev_handle_t speaker;
static TaskHandle_t playback_handle;
static uint8_t *play_buffer;
static size_t play_expected, play_used;
static char play_digest[65];
static int play_volume = 20;
static int64_t play_deadline;
static bool playback_command(cJSON *obj);
static bool playback_timeout(void);
static void playback_task(void *arg);

void muse_audio_snapshot(muse_audio_snapshot_t *out)
{
    portENTER_CRITICAL(&audio_lock);
    *out = snapshot;
    if (out->voice_active && esp_timer_get_time() > voice_deadline) {
        out->voice_ready = false; out->voice_state = "Host offline";
        if (out->codex_state) out->codex_state = "Unknown";
    }
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

static bool request_capture(unsigned int seconds, bool adaptive)
{
    portENTER_CRITICAL(&audio_lock);
    bool ok = seconds >= 1 && seconds <= (adaptive ? MUSE_ENDPOINT_MAX_SECONDS : MUSE_AUDIO_MAX_SECONDS) && snapshot.ready &&
              !snapshot.recording && !snapshot.exporting && !snapshot.receiving &&
              !snapshot.playing && !requested_seconds &&
              (!snapshot.voice_active || (snapshot.voice_ready && esp_timer_get_time() <= voice_deadline));
    if (ok) {
        requested_seconds = seconds;
        requested_adaptive = adaptive;
        if (snapshot.voice_active) { snapshot.voice_ready = false; snapshot.voice_state = "Listening"; }
    }
    portEXIT_CRITICAL(&audio_lock);
    if (ok && snapshot.voice_active) ESP_LOGI("muse_audio", "VOICE_STATE Listening");
    return ok;
}

bool muse_audio_request_capture(unsigned int seconds)
{
    return request_capture(seconds, false);
}

bool muse_audio_request_auto_capture(void)
{
    return request_capture(MUSE_ENDPOINT_MAX_SECONDS, true);
}

static void command_task(void *arg)
{
    char line[1536];
    size_t used = 0;
    bool overflow = false;
    for (;;) {
        char c;
        if (playback_timeout()) {
            memset(line, 0, sizeof(line)); used = 0; overflow = false;
        }
        if (usb_serial_jtag_read_bytes(&c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c != '\n') {
            if (used < sizeof(line) - 1) line[used++] = c;
            else overflow = true;
            continue;
        }
        line[used] = 0;
        cJSON *obj = overflow ? NULL : cJSON_Parse(line);
        cJSON *codex = cJSON_GetObjectItemCaseSensitive(obj, "codex");
        if (cJSON_IsObject(codex)) {
            cJSON *cs = cJSON_GetObjectItemCaseSensitive(codex, "state");
            cJSON *cp = cJSON_GetObjectItemCaseSensitive(codex, "profile");
            cJSON *ct = cJSON_GetObjectItemCaseSensitive(codex, "title");
            const char *state = NULL, *profile = NULL;
            if (cJSON_IsString(cs)) {
                const char *s = cs->valuestring;
                state = !strcmp(s, "starting") || !strcmp(s, "queued") ? "Starting" :
                        !strcmp(s, "running") ? "Working" : !strcmp(s, "waiting") ? "Waiting" :
                        !strcmp(s, "finished") ? "Done" : !strcmp(s, "failed") ? "Failed" :
                        !strcmp(s, "unknown") ? "Unknown" : NULL;
            }
            if (cJSON_IsString(cp)) {
                const char *s = cp->valuestring;
                profile = !strcmp(s, "fast") ? "fast" : !strcmp(s, "strong") ? "strong" :
                          !strcmp(s, "balanced") ? "balanced" : NULL;
            }
            if (state && profile) {
                portENTER_CRITICAL(&audio_lock);
                snapshot.codex_state = state; snapshot.codex_profile = profile;
                snapshot.codex_needs_user = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(codex, "needs_user"));
                size_t n = 0;
                if (cJSON_IsString(ct)) {
                    for (const char *s = ct->valuestring; *s && n < sizeof(snapshot.codex_title) - 1; ++s)
                        if (*s >= 32 && *s <= 126) snapshot.codex_title[n++] = *s;
                }
                snapshot.codex_title[n] = 0;
                portEXIT_CRITICAL(&audio_lock);
            }
        }
        cJSON *voice = cJSON_GetObjectItemCaseSensitive(obj, "voice_state");
        if (cJSON_IsString(voice)) {
            const char *state = !strcmp(voice->valuestring, "Ready") ? "Ready" :
                                !strcmp(voice->valuestring, "Thinking") ? "Thinking" :
                                !strcmp(voice->valuestring, "Speaking") ? "Speaking" : NULL;
            if (state) {
                portENTER_CRITICAL(&audio_lock);
                bool busy = snapshot.recording || snapshot.exporting || snapshot.receiving ||
                            snapshot.playing || requested_seconds;
                bool accepted = strcmp(state, "Ready") || !busy;
                bool changed = accepted && (!snapshot.voice_state || strcmp(snapshot.voice_state, state));
                if (accepted) {
                    snapshot.voice_active = true; snapshot.voice_state = state;
                    snapshot.voice_ready = !strcmp(state, "Ready");
                }
                voice_deadline = esp_timer_get_time() + 15000000;
                portEXIT_CRITICAL(&audio_lock);
                if (changed) ESP_LOGI("muse_audio", "VOICE_STATE %s", state);
            }
            cJSON_Delete(obj);
            memset(line, 0, sizeof(line)); used = 0; overflow = false;
            continue;
        }
        if (playback_command(obj)) {
            cJSON_Delete(obj);
            memset(line, 0, sizeof(line)); used = 0; overflow = false;
            continue;
        }
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
    char transport[1154];
    if (bytes + 1 > sizeof(transport)) return false;
    // Start a fresh line even if console output was partial when the host opened.
    // The delimiter and frame enter the TX ring in one atomic driver write.
    transport[0] = '\n';
    memcpy(transport + 1, line, bytes);
    bytes++;
    // VFS writes characters and can drop after its short timeout. Send the
    // complete transport frame through the blocking driver, never as log text.
    flockfile(stdout);
    fflush(stdout);
    int written = usb_serial_jtag_write_bytes(transport, bytes, pdMS_TO_TICKS(1000));
    esp_err_t drained = usb_serial_jtag_wait_tx_done(pdMS_TO_TICKS(1000));
    funlockfile(stdout);
    return written == bytes && drained == ESP_OK;
}

static void release_upload(void)
{
    if (play_buffer) { memset(play_buffer, 0, play_expected); free(play_buffer); }
    play_buffer = NULL; play_expected = play_used = 0;
    memset(play_digest, 0, sizeof(play_digest));
    portENTER_CRITICAL(&audio_lock);
    snapshot.receiving = false;
    portEXIT_CRITICAL(&audio_lock);
}

static void playback_error(const char *code)
{
    char frame[80];
    snprintf(frame, sizeof(frame), "MUSE_SPK_ERROR code=%s\n", code);
    send_frame(frame);
}

static bool playback_timeout(void)
{
    muse_audio_snapshot_t current;
    muse_audio_snapshot(&current);
    if (current.receiving && esp_timer_get_time() > play_deadline) {
        release_upload(); playback_error("timeout");
        return true;
    }
    return false;
}

static bool integer(cJSON *value, int expected)
{
    return cJSON_IsNumber(value) && value->valuedouble == expected;
}

static bool playback_command(cJSON *obj)
{
    cJSON *begin = cJSON_GetObjectItemCaseSensitive(obj, "play_begin");
    cJSON *chunk = cJSON_GetObjectItemCaseSensitive(obj, "play_data");
    cJSON *end = cJSON_GetObjectItemCaseSensitive(obj, "play_end");
    cJSON *cancel = cJSON_GetObjectItemCaseSensitive(obj, "play_cancel");
    if (!begin && !chunk && !end && !cancel) return false;
    if (begin) {
        int bytes = cJSON_IsNumber(begin) ? begin->valueint : 0;
        cJSON *digest = cJSON_GetObjectItemCaseSensitive(obj, "sha256");
        cJSON *volume = cJSON_GetObjectItemCaseSensitive(obj, "volume");
        int level = volume && cJSON_IsNumber(volume) ? volume->valueint : 20;
        bool volume_valid = !volume || (integer(volume, level) && level >= 10 && level <= 80);
        bool valid = volume_valid && integer(begin, bytes) && bytes > 0 && bytes <= MUSE_AUDIO_RATE * 2 * 5 && bytes % 2 == 0 &&
                     integer(cJSON_GetObjectItemCaseSensitive(obj, "rate"), MUSE_AUDIO_RATE) &&
                     integer(cJSON_GetObjectItemCaseSensitive(obj, "channels"), 1) &&
                     integer(cJSON_GetObjectItemCaseSensitive(obj, "bits"), 16) &&
                     cJSON_IsString(digest) && strlen(digest->valuestring) == 64;
        if (valid) {
            for (int i = 0; i < 64; ++i) {
                char c = digest->valuestring[i];
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) valid = false;
            }
        }
        if (!valid) { playback_error("format"); return true; }
        portENTER_CRITICAL(&audio_lock);
        bool available = snapshot.ready && snapshot.speaker_ready && !snapshot.recording &&
                         !snapshot.exporting && !snapshot.receiving && !snapshot.playing && !requested_seconds;
        if (available) snapshot.receiving = true;
        portEXIT_CRITICAL(&audio_lock);
        if (!available) { playback_error("busy"); return true; }
        play_expected = bytes; play_used = 0; play_volume = level;
        play_buffer = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!play_buffer) { release_upload(); playback_error("memory"); return true; }
        memcpy(play_digest, digest->valuestring, 65);
        play_deadline = esp_timer_get_time() + 5000000;
        char frame[80];
        snprintf(frame, sizeof(frame), "MUSE_SPK_READY bytes=%u\n", (unsigned)bytes);
        if (!send_frame(frame)) release_upload();
        return true;
    }
    muse_audio_snapshot_t current;
    muse_audio_snapshot(&current);
    if (!current.receiving) { playback_error("state"); return true; }
    if (cancel) { release_upload(); playback_error("cancelled"); return true; }
    if (chunk) {
        cJSON *data = cJSON_GetObjectItemCaseSensitive(obj, "data");
        unsigned char decoded[768];
        size_t count = 0;
        bool valid = integer(chunk, play_used) && cJSON_IsString(data) &&
                     strlen(data->valuestring) <= 1024 &&
                     mbedtls_base64_decode(decoded, sizeof(decoded), &count,
                         (unsigned char *)data->valuestring, strlen(data->valuestring)) == 0 &&
                     count > 0 && count % 2 == 0 && play_used + count <= play_expected;
        if (!valid) { release_upload(); playback_error("chunk"); return true; }
        memcpy(play_buffer + play_used, decoded, count); play_used += count;
        memset(decoded, 0, sizeof(decoded));
        play_deadline = esp_timer_get_time() + 5000000;
        char frame[80];
        snprintf(frame, sizeof(frame), "MUSE_SPK_ACK offset=%u\n", (unsigned)play_used);
        if (!send_frame(frame)) release_upload();
        return true;
    }
    unsigned char hash[32]; char hex[65];
    bool valid = cJSON_IsTrue(end) && play_used == play_expected &&
                 mbedtls_sha256(play_buffer, play_used, hash, 0) == 0;
    if (valid) {
        for (size_t i = 0; i < 32; ++i) snprintf(hex + i * 2, 3, "%02x", hash[i]);
        valid = memcmp(hex, play_digest, 64) == 0;
    }
    if (!valid) { release_upload(); playback_error("hash"); return true; }
    portENTER_CRITICAL(&audio_lock);
    snapshot.receiving = false; snapshot.playing = true;
    portEXIT_CRITICAL(&audio_lock);
    xTaskNotifyGive(playback_handle);
    return true;
}

static void playback_task(void *arg)
{
    int16_t output[640];
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        size_t frames = play_expected / 2;
        int64_t started = esp_timer_get_time();
        bool ok = esp_codec_dev_set_out_vol(speaker, play_volume) == ESP_CODEC_DEV_OK &&
                  esp_codec_dev_set_out_mute(speaker, false) == ESP_CODEC_DEV_OK;
        char playing[64];
        snprintf(playing, sizeof(playing), "MUSE_SPK_PLAYING volume=%d\n", play_volume);
        if (ok) send_frame(playing);
        for (size_t offset = 0; ok && offset < frames; offset += 320) {
            size_t count = frames - offset < 320 ? frames - offset : 320;
            const int16_t *mono = (const int16_t *)play_buffer;
            for (size_t i = 0; i < count; ++i) output[2 * i] = output[2 * i + 1] = mono[offset + i];
            ok = esp_codec_dev_write(speaker, output, count * 4) == ESP_CODEC_DEV_OK;
        }
        // Default IDF DMA holds at most ~90ms at 16kHz; drain before muting.
        if (ok) vTaskDelay(pdMS_TO_TICKS(120));
        if (esp_codec_dev_set_out_mute(speaker, true) != ESP_CODEC_DEV_OK) ok = false;
        char frame[120];
        snprintf(frame, sizeof(frame), "MUSE_SPK_DONE bytes=%u frames=%u elapsed_ms=%lld\n",
                 (unsigned)play_expected, (unsigned)frames,
                 (long long)((esp_timer_get_time() - started) / 1000));
        memset(output, 0, sizeof(output));
        release_upload();
        portENTER_CRITICAL(&audio_lock);
        snapshot.playing = false;
        portEXIT_CRITICAL(&audio_lock);
        if (ok) send_frame(frame);
        else playback_error("codec");
    }
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
    // Open both codecs with identical framing before reads start; BSP owns PA/GPIO.
    speaker = bsp_audio_codec_speaker_init();
    bool output_ok = speaker && esp_codec_dev_open(speaker, &format) == ESP_CODEC_DEV_OK &&
                     esp_codec_dev_set_out_mute(speaker, true) == ESP_CODEC_DEV_OK &&
                     esp_codec_dev_set_out_vol(speaker, 20) == ESP_CODEC_DEV_OK;
    if (output_ok) output_ok = xTaskCreate(playback_task, "muse_play", 4096, NULL, 3, &playback_handle) == pdPASS;
    portENTER_CRITICAL(&audio_lock);
    snapshot.speaker_ready = output_ok;
    portEXIT_CRITICAL(&audio_lock);
    if (output_ok) ESP_LOGI("muse_audio", "SPEAKER_READY rate=16000 slots=2 bits=16 volume=20 muted=1");
    else ESP_LOGW("muse_audio", "SPEAKER_UNAVAILABLE");
    portENTER_CRITICAL(&audio_lock);
    snapshot.ready = true;
    portEXIT_CRITICAL(&audio_lock);
    ESP_LOGI("muse_audio", "AUDIO_READY rate=%d channels=2 bits=16 gain_db=24", MUSE_AUDIO_RATE);
    uint8_t *recording = NULL;
    size_t target = 0, used = 0;
    int64_t started = 0, last_report = 0;
    bool adaptive = false;
    float noise = 40;
    muse_endpoint_t endpoint;
    for (;;) {
        unsigned int seconds = 0;
        portENTER_CRITICAL(&audio_lock);
        if (requested_seconds) {
            seconds = requested_seconds;
            adaptive = requested_adaptive;
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
            muse_endpoint_init(&endpoint, noise);
            ESP_LOGI("muse_audio", "AUDIO_RECORDING seconds=%u mode=%s", seconds, adaptive ? "adaptive" : "fixed");
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
        float level = stats.rms[0] > stats.rms[1] ? stats.rms[0] : stats.rms[1];
        if (!recording && level < 300) noise = noise * 0.95f + level * 0.05f;
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
            muse_endpoint_result_t endpoint_result = adaptive ? muse_endpoint_push(&endpoint, level, amount / 4) : MUSE_ENDPOINT_LISTEN;
            if (adaptive && (endpoint_result == MUSE_ENDPOINT_EMPTY || endpoint_result == MUSE_ENDPOINT_LIMIT)) {
                memset(recording, 0, target); free(recording); recording = NULL;
                portENTER_CRITICAL(&audio_lock);
                snapshot.recording = false;
                portEXIT_CRITICAL(&audio_lock);
                ESP_LOGW("muse_audio", "AUDIO_CAPTURE_CANCELLED reason=%s", endpoint_result == MUSE_ENDPOINT_EMPTY ? "no_speech" : "limit");
                continue;
            }
            if (used == target || endpoint_result == MUSE_ENDPOINT_DONE) {
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
    if (xTaskCreate(command_task, "muse_audio_cmd", 8192, NULL, 3, NULL) != pdPASS) fail();
}
