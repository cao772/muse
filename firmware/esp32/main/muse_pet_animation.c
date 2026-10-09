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
    case 53: case 54: case 55: case 56: return MUSE_PET_WALK;
    default: return MUSE_PET_IDLE;
    }
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
    bool sleeping = pose == MUSE_PET_SLEEP || pose == MUSE_PET_BLINK;
    bool happy = pose == MUSE_PET_HAPPY;
    bool typing = pose == MUSE_PET_TYPE_A || pose == MUSE_PET_TYPE_B;
    bool grooming = pose == MUSE_PET_GROOM_A || pose == MUSE_PET_GROOM_B;
    const unsigned int white = 0xf3eee3, tabby = 0xad8a61, stripe = 0x695846;
    if (oval(x, y, 16, 29, 11, 2)) color = 0x233c2c;
    if (pose == MUSE_PET_CURL_A || pose == MUSE_PET_CURL_B) {
        int breath = pose == MUSE_PET_CURL_A ? 0 : 1;
        if (oval(x, y, 18, 24 - breath, 11, 5)) color = tabby;
        if (oval(x, y, 19, 24 - breath, 7, 3)) color = white;
        if (y == 21 - breath && x >= 18 && x <= 25 && x % 3 == 0) color = stripe;
        if (oval(x, y, 11, 21 - breath, 7, 5)) color = tabby;
        if (y >= 13 - breath && y <= 18 - breath &&
            ((x >= 5 && x <= 5 + (y - 13 + breath) / 2) ||
             (x >= 15 && x <= 17 - (y - 13 + breath) / 3))) color = tabby;
        if (y >= 15 - breath && y <= 18 - breath && (x == 6 || x == 16)) color = 0xc99f8d;
        if (y == 18 - breath && (x == 10 || x == 12)) color = stripe;
        if (x == 11 && y >= 18 - breath && y <= 23 - breath) color = white;
        if (oval(x, y, 11, 24 - breath, 5, 2)) color = white;
        if (y == 21 - breath && ((x >= 7 && x <= 9) || (x >= 13 && x <= 15))) color = stripe;
        if (x == 11 && y == 23 - breath) color = 0xc58b89;
        if (y == 28 && x >= 14 && x <= 27) color = x % 4 < 2 ? stripe : tabby;
        if ((y == 7 && x >= 22 && x <= 25) || (y == 10 && x >= 22 && x <= 25) ||
            (x + y == 32 && y >= 7 && y <= 10)) color = 0xb7c8a0;
        return color;
    }
    if (pose == MUSE_PET_TILT && y < 22) x += (y - 13) / 5;
    /* Curled ringed tail, then white chest and warm brown flank. */
    if ((oval(x, y, 24, 25, 5, 4) && !oval(x, y, 24, 24, 2, 2)) ||
        (x >= (pose == MUSE_PET_TAIL ? 28 : 26) && x <= 29 && y >= 19 && y <= 25))
        color = (y % 3 == 0 || x == 28) ? stripe : tabby;
    if (oval(x, y, 16, 23, 7, 6)) color = 0xc6bba4;
    if (oval(x, y, 16, 22, 6, 5)) color = white;
    if (oval(x, y, 21, 23, 2, 4)) color = tabby;
    if (x >= 20 && x <= 22 && (y == 23 || y == 26)) color = stripe;
    /* Tall triangular ears with pink interiors. */
    for (int side = 0; side < 2; ++side) {
        int ex = side == 0 ? x : 32 - x;
        if (y >= 3 && y <= 10 && ex >= 5 && ex <= 6 + (y - 3) / 2) color = stripe;
        if (y >= 3 && y <= 9 && ex >= 6 && ex <= 6 + (y - 3) / 2) color = 0xc99f8d;
    }
    if (oval(x, y, 16, 14, 12, 8)) color = 0xb79a74;
    if (oval(x, y, 16, 13, 11, 7)) color = tabby;
    /* Forehead M, cheek stripes, and the characteristic white nose blaze. */
    if (y >= 7 && y <= 10 && (x == 12 + (y - 7) / 2 || x == 20 - (y - 7) / 2)) color = stripe;
    if (y == 8 && (x == 10 || x == 22)) color = stripe;
    if ((y == 14 || y == 16) && ((x >= 6 && x <= 8) || (x >= 24 && x <= 26))) color = stripe;
    if (y >= 8 && y <= 19 && x >= 16 - (y - 7) / 3 && x <= 16 + (y - 7) / 3)
        color = white;
    if (oval(x, y, 16, 18, 7, 3)) color = white;
    if (sleeping || happy || grooming) {
        if (y == 14 && ((x >= 10 && x <= 12) || (x >= 20 && x <= 22))) color = 0x403a30;
        if (happy && y == 13 && (x == 11 || x == 21)) color = 0x403a30;
    } else {
        if (oval(x, y, 11, 14, 3, 3) || oval(x, y, 21, 14, 3, 3)) color = 0x8d8b66;
        if (oval(x, y, 11, 14, 2, 3) || oval(x, y, 21, 14, 2, 3)) color = 0x302d28;
        if ((x == 10 || x == 20) && (y == 12 || y == 13)) color = 0xfffaee;
    }
    if ((y == 17 && x >= 15 && x <= 17) || (y == 18 && x == 16)) color = 0xc58b89;
    if (y == 19 && (x == 15 || x == 17)) color = 0x8e7669;
    if (happy && x == 16 && y == 20) color = 0xd69798;
    if (pose == MUSE_PET_LISTEN && oval(x, y, 16, 19, 1, 1)) color = 0x72584e;
    if ((y == 18 || y == 20) && ((x >= 4 && x <= 7) || (x >= 25 && x <= 28))) color = 0xd5cbbb;
    int left_y = pose == MUSE_PET_WALK ? 27 : 28;
    if (oval(x, y, 12, left_y, 3, 1) || oval(x, y, 20, 28, 3, 1)) color = white;
    if (pose == MUSE_PET_SLEEP && ((y == 3 && x >= 25 && x <= 28) ||
        (y == 6 && x >= 25 && x <= 28) || (x + y == 31 && y >= 3 && y <= 6)))
        color = 0xb7c8a0;
    if (pose == MUSE_PET_WAIT && ((x == 29 && y >= 9 && y <= 12) || (x == 29 && y == 14)))
        color = 0xf0c575;
    if (happy && ((x == 2 && y >= 5 && y <= 7) || (y == 6 && x >= 1 && x <= 3)))
        color = 0xf0c575;
    if (grooming) {
        if (oval(x, y, 19, 21, 3, 3)) color = white;
        if (pose == MUSE_PET_GROOM_B && x >= 17 && x <= 18 && y == 20) color = 0xd69798;
        if (y == 14 && ((x >= 10 && x <= 12) || (x >= 20 && x <= 22))) color = stripe;
    }
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
