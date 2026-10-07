#pragma once
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t peak[2], clipped[2];
    float rms[2], rms_dbfs[2];
    size_t frames, equal_frames;
} muse_audio_stats_t;

void muse_audio_measure(const int16_t *pcm, size_t frames, muse_audio_stats_t *stats);
