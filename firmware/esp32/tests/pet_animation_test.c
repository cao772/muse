#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../main/muse_pet_animation.h"

int main(void)
{
    uint16_t sprite[MUSE_PET_SPRITE_PIXELS];
    uint16_t reference[MUSE_PET_SPRITE_PIXELS];
    for (unsigned int pose = 0; pose < MUSE_PET_POSE_COUNT; ++pose) {
        assert(muse_pet_sprite_render((muse_pet_pose_t)pose, sprite,
                                      MUSE_PET_SPRITE_PIXELS));
        if (pose == 0) memcpy(reference, sprite, sizeof(sprite));
        else assert(memcmp(reference, sprite, sizeof(sprite)) != 0);
    }
    uint16_t guard[3] = {1, 2, 3};
    assert(!muse_pet_sprite_render(MUSE_PET_POSE_COUNT, guard, 3));
    assert(!muse_pet_sprite_render(MUSE_PET_IDLE, guard, 3));
    assert(!muse_pet_sprite_render(MUSE_PET_IDLE, NULL, MUSE_PET_SPRITE_PIXELS));
    assert(guard[0] == 1 && guard[1] == 2 && guard[2] == 3);

    assert(muse_pet_select_pose(false, false, true, false, 0, 2) == MUSE_PET_WAIT);
    assert(muse_pet_select_pose(false, true, true, true, 60, 3) == MUSE_PET_WAIT);
    assert(muse_pet_select_pose(false, true, false, true, 60, 3) == MUSE_PET_LISTEN);
    assert(muse_pet_select_pose(false, true, false, false, 60, 2) == MUSE_PET_TYPE_A);
    assert(muse_pet_select_pose(false, true, false, false, 60, 3) == MUSE_PET_TYPE_B);
    assert(muse_pet_select_pose(true, false, false, false, 60, 0) == MUSE_PET_HAPPY);
    assert(muse_pet_select_pose(false, false, false, false, 30, 0) == MUSE_PET_SLEEP);
    assert(muse_pet_select_pose(false, false, false, false, 29, 3) == MUSE_PET_WALK);
    assert(muse_pet_select_pose(false, false, false, false, 29, 5) == MUSE_PET_IDLE);
    /* Ended is deliberately mapped by the caller to no agent activity. */
    assert(muse_pet_select_pose(false, false, false, false, 60, 2) == MUSE_PET_SLEEP);
    /* The timed sequence must expose every added idle action within one cycle. */
    bool seen[MUSE_PET_POSE_COUNT] = {false};
    for (uint32_t tick = 0; tick < 70; ++tick) {
        muse_pet_pose_t pose = muse_pet_select_frame(false, false, false, false, 0, tick);
        assert(pose < MUSE_PET_POSE_COUNT);
        seen[pose] = true;
        assert(muse_pet_select_frame(true, true, true, true, 60, tick) == MUSE_PET_WAIT);
        muse_pet_pose_t listening = muse_pet_select_frame(true, true, false, true, 60, tick);
        assert(listening == MUSE_PET_LISTEN || listening == MUSE_PET_BLINK);
        muse_pet_pose_t working = muse_pet_select_frame(true, true, false, false, 60, tick);
        assert(working == MUSE_PET_TYPE_A || working == MUSE_PET_TYPE_B);
    }
    assert(seen[MUSE_PET_IDLE] && seen[MUSE_PET_BLINK] && seen[MUSE_PET_TILT]);
    assert(seen[MUSE_PET_GROOM_A] && seen[MUSE_PET_GROOM_B]);
    assert(seen[MUSE_PET_TAIL] && seen[MUSE_PET_WALK]);
    assert(muse_pet_select_frame(false, false, false, false, 30, 0) == MUSE_PET_CURL_A);
    assert(muse_pet_select_frame(false, false, false, false, 30, 6) == MUSE_PET_CURL_B);
    /* Breathing and licking pairs must change actual pixels, not only their label. */
    const muse_pet_pose_t pairs[][2] = {
        {MUSE_PET_CURL_A, MUSE_PET_CURL_B}, {MUSE_PET_GROOM_A, MUSE_PET_GROOM_B}
    };
    for (size_t i = 0; i < sizeof(pairs) / sizeof(pairs[0]); ++i) {
        assert(muse_pet_sprite_render(pairs[i][0], reference, MUSE_PET_SPRITE_PIXELS));
        assert(muse_pet_sprite_render(pairs[i][1], sprite, MUSE_PET_SPRITE_PIXELS));
        assert(memcmp(reference, sprite, sizeof(sprite)) != 0);
    }
    /* Toys animate for six seconds, expire, and never enqueue another action. */
    const muse_pet_play_t toys[] = {MUSE_PET_PLAY_BALL, MUSE_PET_PLAY_WAND, MUSE_PET_PLAY_FOOD};
    for (size_t i = 0; i < sizeof(toys) / sizeof(toys[0]); ++i) {
        muse_pet_pose_t first = muse_pet_play_frame(toys[i], 0);
        muse_pet_pose_t second = muse_pet_play_frame(toys[i], 3);
        assert(first != second);
        assert(muse_pet_sprite_render(first, reference, MUSE_PET_SPRITE_PIXELS));
        assert(muse_pet_sprite_render(second, sprite, MUSE_PET_SPRITE_PIXELS));
        assert(memcmp(reference, sprite, sizeof(sprite)) != 0);
        assert(muse_pet_play_frame(toys[i], 29) != MUSE_PET_IDLE);
        assert(muse_pet_play_frame(toys[i], 30) == MUSE_PET_IDLE);
        assert(muse_pet_play_frame(toys[i], UINT32_MAX) == MUSE_PET_IDLE);
    }
    assert(muse_pet_play_frame(MUSE_PET_PLAY_NONE, 0) == MUSE_PET_IDLE);
    assert(muse_pet_play_frame((muse_pet_play_t)99, 0) == MUSE_PET_IDLE);
    puts("pet_animation native tests PASS");
    return 0;
}
