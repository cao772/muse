#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MUSE_PET_SPRITE_W 48u
#define MUSE_PET_SPRITE_H 48u
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
    MUSE_PET_BLINK,
    MUSE_PET_TILT,
    MUSE_PET_GROOM_A,
    MUSE_PET_GROOM_B,
    MUSE_PET_TAIL,
    MUSE_PET_CURL_A,
    MUSE_PET_CURL_B,
    MUSE_PET_BALL_A,
    MUSE_PET_BALL_B,
    MUSE_PET_WAND_A,
    MUSE_PET_WAND_B,
    MUSE_PET_FEED_A,
    MUSE_PET_FEED_B,
    MUSE_PET_POSE_COUNT
} muse_pet_pose_t;

muse_pet_pose_t muse_pet_select_pose(bool happy, bool agent_running,
                                    bool needs_user, bool voice_busy,
                                    uint32_t inactive_seconds, uint32_t elapsed_seconds);

/* 200ms UI ticks animate without creating timers or changing persistent state. */
muse_pet_pose_t muse_pet_select_frame(bool happy, bool agent_running, bool needs_user,
    bool voice_busy, uint32_t inactive_seconds, uint32_t ticks);

/* Renders an original opaque RGB565 48x48 pixel sprite, no third-party assets. */
bool muse_pet_sprite_render(muse_pet_pose_t pose, uint16_t *pixels, size_t capacity);

/* Short local interactions, no persistent state or task execution. */
typedef enum { MUSE_PET_PLAY_NONE, MUSE_PET_PLAY_BALL, MUSE_PET_PLAY_WAND,
               MUSE_PET_PLAY_FOOD } muse_pet_play_t;
muse_pet_pose_t muse_pet_play_frame(muse_pet_play_t play, uint32_t ticks);
