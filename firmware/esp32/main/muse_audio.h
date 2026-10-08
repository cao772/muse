#pragma once
#include <stdbool.h>
#include "muse_audio_stats.h"

#define MUSE_AUDIO_RATE 16000
#define MUSE_AUDIO_MAX_SECONDS 5

typedef struct {
    muse_audio_stats_t stats;
    bool ready, failed, recording, exporting;
    bool speaker_ready, receiving, playing;
    bool voice_active, voice_ready;
    const char *voice_state;
    const char *codex_state, *codex_profile;
    bool codex_needs_user;
    char codex_title[25];
} muse_audio_snapshot_t;

void muse_audio_start(void);
void muse_audio_snapshot(muse_audio_snapshot_t *out);

bool muse_audio_request_capture(unsigned int seconds);
bool muse_audio_request_auto_capture(void);
