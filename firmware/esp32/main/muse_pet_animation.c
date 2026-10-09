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

/* Shiyi: original pixel portrait based on the owner's tabby-and-white cat. */
static bool oval(int x, int y, int cx, int cy, int rx, int ry)
{
    int dx = x - cx, dy = y - cy;
    return dx * dx * ry * ry + dy * dy * rx * rx <= rx * rx * ry * ry;
}

static unsigned int pixel_color(muse_pet_pose_t pose, int x, int y)
{
    unsigned int color = 0x14261f;
    bool sleeping = pose == MUSE_PET_SLEEP;
    bool happy = pose == MUSE_PET_HAPPY;
    bool typing = pose == MUSE_PET_TYPE_A || pose == MUSE_PET_TYPE_B;
    const unsigned int white = 0xf3eee3, tabby = 0xad8a61, stripe = 0x695846;
    if (oval(x, y, 16, 29, 11, 2)) color = 0x233c2c;
    /* Curled ringed tail, then white chest and warm brown flank. */
    if ((oval(x, y, 24, 25, 5, 4) && !oval(x, y, 24, 24, 2, 2)) ||
        (x >= 26 && x <= 28 && y >= 20 && y <= 25))
        color = (y % 3 == 0 || x == 28) ? stripe : tabby;
    if (oval(x, y, 16, 23, 7, 6)) color = 0xc6bba4;
    if (oval(x, y, 16, 22, 6, 5)) color = white;
    if (oval(x, y, 21, 23, 2, 4)) color = tabby;
    if (x >= 20 && x <= 22 && (y == 23 || y == 26)) color = stripe;
    /* Tall triangular ears with pink interiors. */
    for (int side = 0; side < 2; ++side) {
        int ex = side == 0 ? x : 32 - x;
        if (y >= 2 && y <= 10 && ex >= 5 && ex <= 6 + (y - 2) / 2) color = stripe;
        if (y >= 3 && y <= 9 && ex >= 6 && ex <= 6 + (y - 3) / 2) color = 0xc99f8d;
    }
    if (oval(x, y, 16, 14, 11, 8)) color = 0xb79a74;
    if (oval(x, y, 16, 13, 10, 7)) color = tabby;
    /* Forehead M, cheek stripes, and the characteristic white nose blaze. */
    if (y >= 7 && y <= 10 && (x == 12 + (y - 7) / 2 || x == 20 - (y - 7) / 2)) color = stripe;
    if (y == 8 && (x == 10 || x == 22)) color = stripe;
    if ((y == 14 || y == 16) && ((x >= 6 && x <= 8) || (x >= 24 && x <= 26))) color = stripe;
    if (y >= 8 && y <= 19 && x >= 16 - (y - 7) / 3 && x <= 16 + (y - 7) / 3)
        color = white;
    if (oval(x, y, 16, 18, 7, 3)) color = white;
    if (sleeping || happy) {
        if (y == 14 && ((x >= 10 && x <= 12) || (x >= 20 && x <= 22))) color = 0x403a30;
        if (happy && y == 13 && (x == 11 || x == 21)) color = 0x403a30;
    } else {
        if (oval(x, y, 11, 13, 2, 2) || oval(x, y, 21, 13, 2, 2)) color = 0xa0a177;
        if ((x == 11 || x == 21) && y >= 12 && y <= 14) color = 0x302d28;
        if ((x == 10 || x == 20) && y == 12) color = 0xfffaee;
    }
    if ((y == 17 && x >= 15 && x <= 17) || (y == 18 && x == 16)) color = 0xc58b89;
    if (y == 19 && (x == 15 || x == 17)) color = 0x8e7669;
    if (happy && x == 16 && y == 20) color = 0xd69798;
    if (pose == MUSE_PET_LISTEN && oval(x, y, 16, 19, 1, 1)) color = 0x72584e;
    if ((y == 18 || y == 20) && ((x >= 4 && x <= 7) || (x >= 25 && x <= 28))) color = 0xd5cbbb;
    int left_y = pose == MUSE_PET_WALK ? 27 : 28;
    if (oval(x, y, 12, left_y, 3, 1) || oval(x, y, 20, 28, 3, 1)) color = white;
    if (sleeping && ((y == 3 && x >= 25 && x <= 28) ||
        (y == 6 && x >= 25 && x <= 28) || (x + y == 31 && y >= 3 && y <= 6)))
        color = 0xb7c8a0;
    if (pose == MUSE_PET_WAIT && ((x == 29 && y >= 9 && y <= 12) || (x == 29 && y == 14)))
        color = 0xf0c575;
    if (happy && ((x == 2 && y >= 5 && y <= 7) || (y == 6 && x >= 1 && x <= 3)))
        color = 0xf0c575;
    if (typing) {
        if (x >= 8 && x <= 24 && y >= 26 && y <= 29) color = 0x6b8f78;
        if (x >= 10 && x <= 22 && y == 27 && x % 2 == 0) color = 0xc8d7b6;
        if (oval(x, y, pose == MUSE_PET_TYPE_A ? 12 : 21, 25, 2, 1)) color = white;
    }
    return color;
}

bool muse_pet_sprite_render(muse_pet_pose_t pose, uint16_t *pixels, size_t capacity)
{
    if ((unsigned int)pose >= MUSE_PET_POSE_COUNT || !pixels || capacity < MUSE_PET_SPRITE_PIXELS)
        return false;
    for (unsigned int y = 0; y < MUSE_PET_SPRITE_H; ++y)
        for (unsigned int x = 0; x < MUSE_PET_SPRITE_W; ++x)
            pixels[y * MUSE_PET_SPRITE_W + x] = rgb565(pixel_color(pose, (int)x, (int)y));
    return true;
}
