#include "muse_audio_stats.h"
#include <math.h>
#include <string.h>

void muse_audio_measure(const int16_t *pcm, size_t frames, muse_audio_stats_t *s)
{
    memset(s, 0, sizeof(*s));
    s->frames = frames;
    uint64_t squares[2] = {0};
    for (size_t i = 0; i < frames; ++i) {
        if (pcm[2 * i] == pcm[2 * i + 1]) ++s->equal_frames;
        for (size_t ch = 0; ch < 2; ++ch) {
            int32_t sample = pcm[2 * i + ch];
            uint32_t magnitude = sample < 0 ? (uint32_t)-sample : (uint32_t)sample;
            if (magnitude > s->peak[ch]) s->peak[ch] = magnitude;
            squares[ch] += (int64_t)sample * sample;
            if (sample == INT16_MIN || sample == INT16_MAX) ++s->clipped[ch];
        }
    }
    for (size_t ch = 0; ch < 2; ++ch) {
        s->rms[ch] = frames ? sqrt((double)squares[ch] / frames) : 0;
        s->rms_dbfs[ch] = s->rms[ch] > 0 ? 20 * log10f(s->rms[ch] / 32768.0f) : -96;
        if (s->rms_dbfs[ch] < -96) s->rms_dbfs[ch] = -96;
    }
}
