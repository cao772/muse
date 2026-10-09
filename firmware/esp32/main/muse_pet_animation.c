#include "muse_pet_animation.h"

static uint16_t rgb565(unsigned int rgb)
{
    return (uint16_t)((((rgb >> 16) & 0xf8u) << 8) |
                      (((rgb >> 8) & 0xfcu) << 3) |
                      ((rgb & 0xf8u) >> 3));
}

muse_pet_pose_t muse_pet_select_pose(bool happy, bool agent_running,
                                    bool needs_user, bool voice_busy,
                                    uint32_t inactive_seconds, uint32_t elapsed_seconds)
{
    /* Status from the authenticated Mac USB snapshot is advisory and visual-only. */
    if (needs_user) return MUSE_PET_WAIT;
    if (voice_busy) return MUSE_PET_LISTEN;
    if (agent_running) return elapsed_seconds % 2u ? MUSE_PET_TYPE_B : MUSE_PET_TYPE_A;
    if (happy) return MUSE_PET_HAPPY;
    if (inactive_seconds >= 30u) return MUSE_PET_SLEEP;
    if (elapsed_seconds % 11u == 3u || elapsed_seconds % 11u == 4u)
        return MUSE_PET_WALK;
    return MUSE_PET_IDLE;
}

muse_pet_pose_t muse_pet_select_frame(bool happy, bool agent_running, bool needs_user,
    bool voice_busy, uint32_t inactive_seconds, uint32_t ticks)
{
    if (needs_user) return MUSE_PET_WAIT;
    if (voice_busy) return ticks % 12u == 0 ? MUSE_PET_BLINK : MUSE_PET_LISTEN;
    if (agent_running) return ticks % 4u < 2 ? MUSE_PET_TYPE_A : MUSE_PET_TYPE_B;
    if (happy) return ticks % 6u < 3 ? MUSE_PET_HAPPY : MUSE_PET_TILT;
    if (inactive_seconds >= 30u) return ticks % 12u < 6 ? MUSE_PET_CURL_A : MUSE_PET_CURL_B;
    switch (ticks % 70u) {
    case 8: case 9: case 35: return MUSE_PET_BLINK;
    case 15: case 16: case 17: case 18: return MUSE_PET_TILT;
    case 25: case 27: case 29: return MUSE_PET_GROOM_A;
    case 26: case 28: case 30: return MUSE_PET_GROOM_B;
    case 42: case 43: case 46: case 47: return MUSE_PET_TAIL;
    case 53: case 54: return MUSE_PET_WALK;
    case 55: case 56: return MUSE_PET_WALK_B;
    default: return MUSE_PET_IDLE;
    }
}

#include "muse_pet_art.inc"

muse_pet_pose_t muse_pet_play_frame(muse_pet_play_t play, uint32_t ticks)
{
    if (ticks >= 30u) return MUSE_PET_IDLE;
    bool second = ticks % 6u >= 3u;
    switch (play) {
    case MUSE_PET_PLAY_BALL: return second ? MUSE_PET_BALL_B : MUSE_PET_BALL_A;
    case MUSE_PET_PLAY_WAND: return second ? MUSE_PET_WAND_B : MUSE_PET_WAND_A;
    case MUSE_PET_PLAY_FOOD: return second ? MUSE_PET_FEED_B : MUSE_PET_FEED_A;
    default: return MUSE_PET_IDLE;
    }
}

static uint16_t pixel_color(muse_pet_pose_t pose, int x, int y)
{
    static const uint8_t frames[MUSE_PET_POSE_COUNT] = {
        0, 4, 8, 2, 14, 15, 13, 12, 1, 3, 6, 7, 0, 8, 9, 10, 11, 10, 11, 0, 1, 5
    };
    int sx = x;
    if (pose == MUSE_PET_TAIL && y > 67 && x < 42) sx = x > 1 ? x-2 : 0;
    uint16_t c = shiyi_palette[shiyi_art[frames[pose]][y * MUSE_PET_SPRITE_W + sx]];
    bool ball = pose == MUSE_PET_BALL_A || pose == MUSE_PET_BALL_B;
    bool wand = pose == MUSE_PET_WAND_A || pose == MUSE_PET_WAND_B;
    bool feed = pose == MUSE_PET_FEED_A || pose == MUSE_PET_FEED_B;
    if (ball) {
        int bx = pose == MUSE_PET_BALL_A ? 82 : 88;
        int by = pose == MUSE_PET_BALL_A ? 87 : 74;
        int dx=x-bx, dy=y-by;
        if (dx*dx+dy*dy <= 25) c=rgb565(0xddaa89);
        if (dy == 0 && dx >= -4 && dx <= 4) c=rgb565(0xb47761);
    }
    if (wand) {
        int wx = pose == MUSE_PET_WAND_A ? 84 : 76;
        if (x == 91 && y >= 7 && y <= 34) c=rgb565(0xc5ab7c);
        if (y >= 17 && y <= 40 && x == 91-(y-17)*(91-wx)/23) c=rgb565(0xdacfba);
        int dx=x-wx,dy=y-44;
        if (dx*dx*4+dy*dy <= 49) c=rgb565(0xb6cbb0);
        if (x == wx && y >= 40 && y <= 49) c=rgb565(0xf0d0a3);
    }
    if (feed) {
        if (y >= 85 && y <= 92 && x >= 34+(y-85) && x <= 64-(y-85)) c=rgb565(0xabbd9e);
        if (y == 85 && x >= 35 && x <= 63) c=rgb565(0x795b43);
        if (y == 84 && (x == 42 || x == 51 || x == 57)) c=rgb565(0xe1b47a);
    }
    if (pose == MUSE_PET_TYPE_A || pose == MUSE_PET_TYPE_B) {
        if (x >= 29 && x <= 68 && y >= 88 && y <= 94) c=rgb565(0x6b8f78);
        if (y == 91 && x >= 32 && x <= 65 && x % 4 == 0) c=rgb565(0xc8d7b6);
    }
    if (pose == MUSE_PET_WAIT && x >= 86 && x <= 87 &&
        ((y >= 24 && y <= 31) || y == 35)) c=rgb565(0xf0c575);
    return c;
}

bool muse_pet_sprite_render(muse_pet_pose_t pose, uint16_t *pixels, size_t capacity)
{
    if ((unsigned int)pose >= MUSE_PET_POSE_COUNT || !pixels || capacity < MUSE_PET_SPRITE_PIXELS)
        return false;
    for (unsigned int y = 0; y < MUSE_PET_SPRITE_H; ++y)
        for (unsigned int x = 0; x < MUSE_PET_SPRITE_W; ++x)
            pixels[y * MUSE_PET_SPRITE_W + x] = pixel_color(pose, (int)x, (int)y);
    return true;
}
