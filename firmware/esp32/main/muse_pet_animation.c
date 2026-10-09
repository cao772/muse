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

/* Original cream puppy, drawn in layered pixel shapes. No downloaded assets. */
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
    if (oval(x, y, 16, 29, 11, 2)) color = 0x233c2c; /* soft grounding shadow */
    if (oval(x, y, 16, 23, 7, 6)) color = 0xd9c6a7;
    if (oval(x, y, 16, 22, 6, 5)) color = 0xf0e1c5;
    if (oval(x, y, 7, 13, 4, 7) || oval(x, y, 25, 13, 4, 7)) color = 0x9f775c;
    if (oval(x, y, 7, 12, 3, 5) || oval(x, y, 25, 12, 3, 5)) color = 0xc79b77;
    if (oval(x, y, 16, 13, 10, 9)) color = 0xd5ba91;
    if (oval(x, y, 16, 12, 9, 8)) color = 0xf5e9d1;
    if (oval(x, y, 14, 8, 5, 3)) color = 0xfff4de;
    /* Tiny leaf-shaped tuft, rather than pointed monster ears. */
    if ((y == 3 && x >= 15 && x <= 17) || (y == 2 && x == 17)) color = 0xf5e9d1;
    if (oval(x, y, 9, 16, 2, 1) || oval(x, y, 23, 16, 2, 1)) color = 0xe6a695;
    if (sleeping || happy) {
        if (((x >= 10 && x <= 12) || (x >= 20 && x <= 22)) && y == (happy ? 12 : 14))
            color = 0x594636;
        if (happy && (x == 10 || x == 22) && y == 13) color = 0x594636;
    } else {
        if (((x >= 11 && x <= 12) || (x >= 20 && x <= 21)) && y >= 12 && y <= 14)
            color = 0x403b30;
        if ((x == 11 || x == 20) && y == 12) color = 0xfff9eb;
    }
    if (oval(x, y, 16, 17, 4, 3)) color = 0xfff4de;
    if ((y == 16 && x >= 15 && x <= 17) || (y == 17 && x == 16)) color = 0x67513e;
    if (y == 19 && (x == 15 || x == 17)) color = 0x9b7058;
    if (happy && x == 16 && y == 20) color = 0xe6a695;
    if (pose == MUSE_PET_LISTEN && oval(x, y, 16, 19, 1, 1)) color = 0x67513e;
    if (y >= 21 && y <= 22 && x >= 11 && x <= 21) color = 0x80ae8c;
    if (x >= 19 && x <= 20 && y >= 23 && y <= 25) color = 0x608b70;
    int left_y = pose == MUSE_PET_WALK ? 27 : 28;
    if (oval(x, y, 12, left_y, 3, 1) || oval(x, y, 21, 28, 3, 1)) color = 0xffefd4;
    if (sleeping && ((y == 3 && x >= 25 && x <= 28) ||
        (y == 6 && x >= 25 && x <= 28) || (x + y == 31 && y >= 3 && y <= 6)))
        color = 0xb7c8a0;
    if (pose == MUSE_PET_WAIT && ((x == 28 && y >= 9 && y <= 12) || (x == 28 && y == 14)))
        color = 0xf0c575;
    if (happy && ((x == 3 && y >= 5 && y <= 7) || (y == 6 && x >= 2 && x <= 4)))
        color = 0xf0c575;
    if (typing) {
        if (x >= 8 && x <= 24 && y >= 26 && y <= 29) color = 0x6b8f78;
        if (x >= 10 && x <= 22 && y == 27 && x % 2 == 0) color = 0xc8d7b6;
        if (oval(x, y, pose == MUSE_PET_TYPE_A ? 12 : 21, 25, 2, 1)) color = 0xffefd4;
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
