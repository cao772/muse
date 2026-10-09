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

static unsigned int pixel_color(muse_pet_pose_t pose, int x, int y)
{
    const unsigned int bg = 0x14261f, outline = 0x665444;
    const unsigned int fur = 0xba966b, shade = 0x987b5b;
    const unsigned int white = 0xf5eee2, cream = 0xdacfba, stripe = 0x77634e;
    unsigned int c = bg;
    bool happy = pose == MUSE_PET_HAPPY;
    bool groom = pose == MUSE_PET_GROOM_A || pose == MUSE_PET_GROOM_B;
    bool sleep = pose == MUSE_PET_SLEEP || pose == MUSE_PET_CURL_A || pose == MUSE_PET_CURL_B;
    bool ball = pose == MUSE_PET_BALL_A || pose == MUSE_PET_BALL_B;
    bool wand = pose == MUSE_PET_WAND_A || pose == MUSE_PET_WAND_B;
    bool feed = pose == MUSE_PET_FEED_A || pose == MUSE_PET_FEED_B;
    bool typing = pose == MUSE_PET_TYPE_A || pose == MUSE_PET_TYPE_B;
    if (oval(x, y, 24, 45, 18, 2)) c = 0x233c2c;
    if (sleep) {
        int b = pose == MUSE_PET_CURL_B ? 1 : 0;
        if (oval(x, y, 26, 35-b, 17, 9)) c = outline;
        if (oval(x, y, 26, 34-b, 16, 8)) c = fur;
        if (oval(x, y, 27, 35-b, 12, 6)) c = white;
        if (oval(x, y, 31, 31-b, 6, 4)) c = shade;
        if (y == 29-b && x >= 28 && x <= 35 && x % 3 == 0) c = stripe;
        if (oval(x, y, 15, 33-b, 10, 8)) c = outline;
        if (oval(x, y, 15, 32-b, 9, 7)) c = fur;
        if (y >= 20-b && y <= 28-b && ((x >= 6 && x <= 7+(y-20+b)/3) ||
            (x >= 22-(y-20+b)/3 && x <= 23))) c = fur;
        if (y >= 22-b && y <= 27-b && (x == 7 || x == 22)) c = 0xd0a39a;
        if (oval(x, y, 15, 36-b, 7, 4) || (x == 15 && y >= 27-b && y <= 35-b)) c = white;
        if (y == 32-b && ((x >= 9 && x <= 12) || (x >= 18 && x <= 21))) c = outline;
        if (x == 15 && y == 35-b) c = 0xce9290;
        if (oval(x, y, 26, 41, 12, 3)) c = x % 6 < 2 ? stripe : fur;
        if (oval(x, y, 12, 40, 4, 2)) c = white;
        if ((y == 12 && x >= 34 && x <= 38) || (y == 16 && x >= 34 && x <= 38) ||
            (x+y == 50 && y >= 12 && y <= 16)) c = 0xb7c8a0;
        return c;
    }
    /* The ringed tail sits behind the haunch, with two visibly different arcs. */
    int tail_x = pose == MUSE_PET_TAIL || pose == MUSE_PET_BALL_B ? 43 : 40;
    if (oval(x, y, tail_x, 32, 4, 10) && !oval(x, y, tail_x-2, 30, 2, 7))
        c = y % 5 < 2 ? stripe : fur;
    /* A broad pear-shaped body, two rear haunches, and four separated paws. */
    if (oval(x, y, 24, 32, 16, 12)) c = outline;
    if (oval(x, y, 24, 31, 15, 11)) c = fur;
    if (oval(x, y, 24, 32, 11, 10)) c = white;
    if (oval(x, y, 13, 37, 6, 7) || oval(x, y, 35, 37, 6, 7)) c = shade;
    if (y >= 34 && y <= 39 && (x == 10 || x == 37)) c = stripe;
    if (oval(x, y, 12, 42, 4, 2) || oval(x, y, 36, 42, 4, 2)) c = cream;
    /* Front legs have their own outline and toe marks, not a shared white blob. */
    int left_y = pose == MUSE_PET_WALK ? 36 : 37;
    if (oval(x, y, 20, left_y, 4, 7) || oval(x, y, 28, 37, 4, 7)) c = cream;
    if (oval(x, y, 20, left_y-1, 3, 6) || oval(x, y, 28, 36, 3, 6)) c = white;
    if (oval(x, y, 20, left_y+5, 3, 2) || oval(x, y, 28, 42, 3, 2)) c = white;
    if (y == 43 && (x == 19 || x == 21 || x == 27 || x == 29)) c = 0xc9bca9;
    if (x == 24 && y >= 33 && y <= 42) c = cream;
    if (x == 24 && y >= 43 && y <= 44) c = bg;
    if ((x == 16 || x == 32) && y >= 40 && y <= 43) c = outline;
    /* Short tabby ears and a rounded, wide face. */
    int hx = x, hy = y;
    if (pose == MUSE_PET_TILT) hx += (y-17)/6;
    for (int side = 0; side < 2; ++side) {
        int ex = side ? 48-hx : hx;
        if (hy >= 4 && hy <= 14 && ex >= 11 && ex <= 12+(hy-4)/2) c = outline;
        if (hy >= 5 && hy <= 13 && ex >= 12 && ex <= 12+(hy-5)/2) c = fur;
        if (hy >= 7 && hy <= 12 && ex >= 12 && ex <= 12+(hy-7)/2) c = 0xd4a6a0;
    }
    if (oval(hx, hy, 24, 18, 15, 11)) c = outline;
    if (oval(hx, hy, 24, 17, 14, 10)) c = fur;
    if (oval(hx, hy, 24, 23, 11, 5)) c = white;
    /* Shiyi's irregular white forehead blaze widens toward the pink nose. */
    if (hy >= 10 && hy <= 24 && hx >= 24-(hy-9)/4 && hx <= 25+(hy-9)/5) c = white;
    if (hy >= 10 && hy <= 14 && (hx == 18+(hy-10)/2 || hx == 30-(hy-10)/2)) c = stripe;
    if ((hy == 18 || hy == 21) && ((hx >= 11 && hx <= 14) || (hx >= 34 && hx <= 37))) c = stripe;
    bool closed = happy || groom || pose == MUSE_PET_BLINK || pose == MUSE_PET_FEED_B;
    if (closed) {
        if (hy == 19 && ((hx >= 16 && hx <= 20) || (hx >= 28 && hx <= 32))) c = outline;
        if (happy && hy == 18 && (hx == 18 || hx == 30)) c = outline;
    } else {
        if (oval(hx, hy, 18, 18, 3, 4) || oval(hx, hy, 30, 18, 3, 4)) c = 0x91906e;
        if (oval(hx, hy, 18, 18, 2, 4) || oval(hx, hy, 30, 18, 2, 4)) c = 0x342f29;
        if ((hx == 17 || hx == 29) && (hy == 15 || hy == 16)) c = 0xfffaf0;
        if ((hx == 19 || hx == 31) && hy == 20) c = 0xc2bfa7;
    }
    if (hy == 23 && hx >= 23 && hx <= 25) c = 0xcb908f;
    if (hy == 24 && hx == 24) c = 0xcb908f;
    if (hy == 25 && (hx == 23 || hx == 25)) c = 0x947c6a;
    if ((hy == 24 || hy == 26) && ((hx >= 8 && hx <= 12) || (hx >= 36 && hx <= 40))) c = 0xd7c9b7;
    if (pose == MUSE_PET_LISTEN && oval(hx, hy, 24, 26, 1, 1)) c = outline;
    if (happy && ((x == 5 && y >= 13 && y <= 16) || (y == 14 && x >= 3 && x <= 7))) c = 0xe7b38b;
    if (pose == MUSE_PET_WAIT && x == 43 && ((y >= 12 && y <= 16) || y == 18)) c = 0xf0c575;
    if (groom) {
        if (oval(x, y, 28, 27, 4, 5)) c = cream;
        if (oval(x, y, 27, 26, 3, 4)) c = white;
        if (pose == MUSE_PET_GROOM_B && y == 26 && x >= 24 && x <= 25) c = 0xd49798;
    }
    if (ball || wand) {
        int paw_y = pose == MUSE_PET_BALL_B || pose == MUSE_PET_WAND_B ? 26 : 31;
        if (oval(x, y, 36, paw_y, 5, 3)) c = cream;
        if (oval(x, y, 36, paw_y-1, 4, 2)) c = white;
    }
    if (ball) {
        int bx = pose == MUSE_PET_BALL_A ? 40 : 44;
        int by = pose == MUSE_PET_BALL_A ? 42 : 36;
        if (oval(x, y, bx, by, 3, 3)) c = 0xddaa89;
        if (oval(x, y, bx-1, by-1, 1, 1)) c = 0xf4dbc1;
        if (y == by && x >= bx-2 && x <= bx+2) c = 0xb47761;
    }
    if (wand) {
        int wx = pose == MUSE_PET_WAND_A ? 40 : 35;
        if (x == 44 && y >= 4 && y <= 19) c = 0xc5ab7c;
        if (y >= 8 && y <= 20 && x == 44-(y-8)*(44-wx)/12) c = cream;
        if (oval(x, y, wx, 23, 2, 4)) c = 0xb6cbb0;
        if (x == wx && y >= 21 && y <= 26) c = 0xf0d0a3;
    }
    if (feed) {
        if (y >= 42 && y <= 45 && x >= 18+(y-42) && x <= 31-(y-42)) c = 0xabbd9e;
        if (y == 42 && x >= 19 && x <= 30) c = 0x795b43;
        if (y == 41 && (x == 22 || x == 26)) c = 0xe1b47a;
    }
    if (typing) {
        if (x >= 14 && x <= 34 && y >= 40 && y <= 44) c = 0x6b8f78;
        if (y == 42 && x >= 16 && x <= 32 && x % 3 == 0) c = 0xc8d7b6;
        if (oval(x, y, pose == MUSE_PET_TYPE_A ? 20 : 28, 39, 3, 2)) c = white;
    }
    return c;
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
