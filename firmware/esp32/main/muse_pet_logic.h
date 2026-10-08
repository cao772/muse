#pragma once
#include <stdbool.h>
#include <stdint.h>

#define MUSE_PET_PLOTS 3
#define MUSE_PET_SCHEMA_VERSION 1u
#define MUSE_PET_MAGIC 0x4d505431u
#define MUSE_PET_GROW_SECONDS 45u

typedef enum {
    MUSE_PLOT_EMPTY = 0,
    MUSE_PLOT_SEEDED = 1,
    MUSE_PLOT_GROWING = 2,
    MUSE_PLOT_READY = 3,
} muse_plot_stage_t;

/* Fixed-version NVS payload. No Wi-Fi secrets, wall-clock timestamps or pointers. */
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t pats;
    uint32_t treats;
    uint32_t harvests;
    uint8_t plots[MUSE_PET_PLOTS];
    uint8_t reserved;
    uint32_t checksum;
} muse_pet_save_t;

void muse_pet_reset(muse_pet_save_t *state);
bool muse_pet_valid(const muse_pet_save_t *state);
void muse_pet_seal(muse_pet_save_t *state);
bool muse_pet_pat(muse_pet_save_t *state);
bool muse_pet_feed(muse_pet_save_t *state);
bool muse_pet_plot_tap(muse_pet_save_t *state, unsigned int plot);
bool muse_pet_mature(muse_pet_save_t *state, unsigned int plot);
