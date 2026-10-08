#pragma once
#include <stdbool.h>
#include "muse_pet_logic.h"

/* Call once after nvs_flash_init(), before creating the LVGL pages. */
void muse_pet_runtime_init(void);
/* LVGL task only: bounded, cooperative growth and delayed NVS checkpoint. */
void muse_pet_runtime_service(void);
const muse_pet_save_t *muse_pet_runtime_state(void);
void muse_pet_runtime_pat(void);
void muse_pet_runtime_feed(void);
void muse_pet_runtime_plot(unsigned int index);
bool muse_pet_runtime_happy(void);
