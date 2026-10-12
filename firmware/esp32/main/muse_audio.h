#pragma once
#include <stdbool.h>
#include "muse_audio_stats.h"

#define MUSE_AUDIO_RATE 16000
#define MUSE_AUDIO_MAX_SECONDS 5

typedef struct {
    bool available, stale, tests_known, event_known;
    unsigned int revision, projects, registered, index, task_index, tasks, passed, failed, event_age;
    char alias[73], title[97], state[24], progress[121], profile[16], effort[12], source[24], file[65], action[16], instruction[241];
} muse_board_snapshot_t;

typedef struct {
    muse_board_snapshot_t board;
    muse_audio_stats_t stats;
    bool ready, failed, recording, exporting;
    bool speaker_ready, receiving, playing;
    bool voice_active, voice_ready;
    const char *voice_state;
    const char *codex_state, *codex_profile;
    bool codex_needs_user;
    bool attention_known;
    unsigned int attention_count;
    const char *wechat_status;
    unsigned int wechat_count, wechat_sync_age;
    unsigned int wechat_mentions, wechat_tasks, wechat_blockers;
    char codex_title[25];
} muse_audio_snapshot_t;

void muse_audio_start(void);
void muse_audio_snapshot(muse_audio_snapshot_t *out);

bool muse_audio_request_capture(unsigned int seconds);
bool muse_audio_request_auto_capture(void);
