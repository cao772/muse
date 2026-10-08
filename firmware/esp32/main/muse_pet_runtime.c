#include "muse_pet_runtime.h"
#include <stdint.h>
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs.h"

#define STORE_NAMESPACE "muse_pet_v1"
#define STORE_KEY "garden"
#define SAVE_DEBOUNCE_US 5000000LL
#define SAVE_RETRY_US 10000000LL
#define HAPPY_US 8000000LL
#define GROW_US ((int64_t)MUSE_PET_GROW_SECONDS * 1000000LL)

static const char *TAG = "muse_pet";
static muse_pet_save_t pet;
static nvs_handle_t handle;
static bool initialized, persistent, dirty;
static int64_t first_dirty, retry_after, happy_until, growing_from[MUSE_PET_PLOTS];

static void changed(void)
{
    if (!dirty) first_dirty = esp_timer_get_time();
    dirty = true;
}

void muse_pet_runtime_init(void)
{
    muse_pet_reset(&pet);
    persistent = false;
    esp_err_t error = nvs_open(STORE_NAMESPACE, NVS_READWRITE, &handle);
    if (error == ESP_OK) {
        persistent = true;
        muse_pet_save_t saved;
        size_t size = sizeof(saved);
        error = nvs_get_blob(handle, STORE_KEY, &saved, &size);
        if (error == ESP_OK && size == sizeof(saved) && muse_pet_valid(&saved)) {
            pet = saved;
            ESP_LOGI(TAG, "Existing pet state restored");
        } else if (error != ESP_ERR_NVS_NOT_FOUND) {
            ESP_LOGW(TAG, "Saved pet data absent/invalid; defaults used");
        }
    } else {
        ESP_LOGW(TAG, "Pet NVS unavailable; current session is RAM only");
    }
    int64_t now = esp_timer_get_time();
    /* No trusted RTC: elapsed time while unpowered is deliberately NOT credited. */
    for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i)
        if (pet.plots[i] == MUSE_PLOT_GROWING) growing_from[i] = now;
    initialized = true;
}

const muse_pet_save_t *muse_pet_runtime_state(void)
{
    return &pet;
}

void muse_pet_runtime_pat(void)
{
    if (!initialized || !muse_pet_pat(&pet)) return;
    happy_until = esp_timer_get_time() + HAPPY_US;
    changed();
}

void muse_pet_runtime_feed(void)
{
    if (!initialized || !muse_pet_feed(&pet)) return;
    happy_until = esp_timer_get_time() + HAPPY_US;
    changed();
}

void muse_pet_runtime_plot(unsigned int index)
{
    if (!initialized || !muse_pet_plot_tap(&pet, index)) return;
    if (pet.plots[index] == MUSE_PLOT_GROWING)
        growing_from[index] = esp_timer_get_time();
    else
        growing_from[index] = 0;
    changed();
}

bool muse_pet_runtime_happy(void)
{
    return initialized && esp_timer_get_time() < happy_until;
}

void muse_pet_runtime_service(void)
{
    if (!initialized) return;
    int64_t now = esp_timer_get_time();
    for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i) {
        if (pet.plots[i] != MUSE_PLOT_GROWING) continue;
        if (!growing_from[i]) growing_from[i] = now;
        if (now - growing_from[i] >= GROW_US && muse_pet_mature(&pet, i)) {
            growing_from[i] = 0;
            changed();
        }
    }
    if (!dirty || !persistent || now - first_dirty < SAVE_DEBOUNCE_US ||
        now < retry_after) return;
    muse_pet_seal(&pet);
    esp_err_t err = nvs_set_blob(handle, STORE_KEY, &pet, sizeof(pet));
    if (err == ESP_OK) err = nvs_commit(handle);
    if (err == ESP_OK) {
        dirty = false;
    } else {
        /* No per-frame retry and no NVS erase or modification of Wi-Fi keys. */
        retry_after = now + SAVE_RETRY_US;
        ESP_LOGW(TAG, "Pet checkpoint deferred");
    }
}
