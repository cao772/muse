#include <assert.h>
#include <math.h>
#include "muse_audio_stats.h"

int main(void)
{
    muse_audio_stats_t s;
    const int16_t zero[] = {0, 0, 0, 0};
    muse_audio_measure(zero, 2, &s);
    assert(s.frames == 2 && s.equal_frames == 2 && s.peak[0] == 0);
    assert(s.rms_dbfs[0] == -96 && s.clipped[0] == 0);
    const int16_t different[] = {1000, 2000, -1000, -2000};
    muse_audio_measure(different, 2, &s);
    assert(s.peak[0] == 1000 && s.peak[1] == 2000 && s.equal_frames == 0);
    assert(fabsf(s.rms[0] - 1000) < .01 && fabsf(s.rms[1] - 2000) < .01);
    assert(fabsf(s.rms_dbfs[1] - s.rms_dbfs[0] - 6.0206f) < .001f);
    const int16_t extremes[] = {INT16_MIN, INT16_MAX, INT16_MAX, 0};
    muse_audio_measure(extremes, 2, &s);
    assert(s.peak[0] == 32768 && s.peak[1] == 32767);
    assert(s.clipped[0] == 2 && s.clipped[1] == 1);
    assert(s.rms[0] > 32767 && isfinite(s.rms_dbfs[0]));
    muse_audio_measure(NULL, 0, &s);
    assert(s.frames == 0 && s.rms[0] == 0 && s.rms_dbfs[0] == -96);
    return 0;
}
