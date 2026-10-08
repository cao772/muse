#include "muse_pet_animation.h"

static const char *const sprite[MUSE_PET_SPRITE_H] = {
    "................",
    "....OO....OO....",
    "...OBBO..OBBO...",
    "..OBBBB..BBBBO..",
    "..OBBBBBBBBBBBO.",
    ".OBBBBBBBBBBBBO.",
    ".OBBBBBBBBBBBBO.",
    ".OBBEEBBBEEBBBO.",
    ".OBBBBBBBBBBBBO.",
    ".OBBBBBMBBBBBBO.",
    ".OBBBBBBBBBBBBO.",
    "..OBBBBBBBBBBBO.",
    "...OBBBBBBBBBO..",
    "....OOOOOOOO....",
    "................",
    "................",
};

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

static char pixel_char(muse_pet_pose_t pose, unsigned int x, unsigned int y)
{
    char pixel = sprite[y][x];
    if (pose == MUSE_PET_SLEEP && y == 7 && pixel == 'E') return 'O';
    if (pose == MUSE_PET_HAPPY && y == 7 && pixel == 'E') return 'P';
    if (pose == MUSE_PET_LISTEN && y == 9 && pixel == 'M') return 'E';
    if (pose == MUSE_PET_WAIT && x == 14 && (y == 4 || y == 5)) return 'Y';
    if (pose == MUSE_PET_WAIT && x == 14 && y == 6) return 'O';
    if (pose == MUSE_PET_SLEEP && x == 13 && y == 1) return 'Y';
    if (pose == MUSE_PET_SLEEP && x == 14 && y == 0) return 'Y';
    if (pose == MUSE_PET_WALK && y == 14 && (x == 5 || x == 10)) return 'O';
    if (pose == MUSE_PET_HAPPY && y == 10 && (x == 3 || x == 12)) return 'P';
    if (pose == MUSE_PET_TYPE_A || pose == MUSE_PET_TYPE_B) {
        if (y == 14 && x >= 3 && x <= 12) return 'K';
        if (y == 15 && x >= 4 && x <= 11) return 'O';
        if (y == 12 && x == (pose == MUSE_PET_TYPE_A ? 5u : 10u)) return 'P';
    }
    return pixel;
}

bool muse_pet_sprite_render(muse_pet_pose_t pose, uint16_t *pixels, size_t capacity)
{
    if (pose >= MUSE_PET_POSE_COUNT || !pixels || capacity < MUSE_PET_SPRITE_PIXELS)
        return false;
    for (unsigned int y = 0; y < MUSE_PET_SPRITE_H; ++y) {
        for (unsigned int x = 0; x < MUSE_PET_SPRITE_W; ++x) {
            unsigned int color;
            switch (pixel_char(pose, x, y)) {
            case 'B': color = pose == MUSE_PET_HAPPY ? 0xf2b3cb : 0x8dd3e2; break;
            case 'O': color = 0x274350; break;
            case 'E': color = 0x172a35; break;
            case 'M': color = 0xdd869d; break;
            case 'P': color = 0xec8fa9; break;
            case 'Y': color = 0xf7d476; break;
            case 'K': color = 0x77818c; break;
            default: color = 0x101922; break;
            }
            pixels[y * MUSE_PET_SPRITE_W + x] = rgb565(color);
        }
    }
    return true;
}
