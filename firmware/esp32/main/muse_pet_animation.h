#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MUSE_PET_SPRITE_W 16u
#define MUSE_PET_SPRITE_H 16u
#define MUSE_PET_SPRITE_PIXELS (MUSE_PET_SPRITE_W * MUSE_PET_SPRITE_H)

/* Visual states only: they never change the saved pet/garden schema. */
typedef enum {
    MUSE_PET_IDLE = 0,
    MUSE_PET_WALK,
    MUSE_PET_SLEEP,
    MUSE_PET_HAPPY,
    MUSE_PET_TYPE_A,
    MUSE_PET_TYPE_B,
    MUSE_PET_WAIT,
    MUSE_PET_LISTEN,
    MUSE_PET_POSE_COUNT
} muse_pet_pose_t;

muse_pet_pose_t muse_pet_select_pose(bool happy, bool agent_running,
                                    bool needs_user, bool voice_busy,
                                    uint32_t inactive_seconds, uint32_t elapsed_seconds);

/* Renders an original opaque RGB565 16x16 pixel sprite, no third-party assets. */
bool muse_pet_sprite_render(muse_pet_pose_t pose, uint16_t *pixels, size_t capacity);
