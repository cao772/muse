#pragma once
#include <stdbool.h>
#include "muse_audio_stats.h"

#define MUSE_AUDIO_RATE 16000
#define MUSE_AUDIO_MAX_SECONDS 5

typedef struct {
    muse_audio_stats_t stats;
    bool ready, failed, recording, exporting;
    bool speaker_ready, receiving, playing;
} muse_audio_snapshot_t;

void muse_audio_start(void);
void muse_audio_snapshot(muse_audio_snapshot_t *out);

bool muse_audio_request_capture(unsigned int seconds);
