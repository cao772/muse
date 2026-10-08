#include "muse_endpoint.h"
void muse_endpoint_init(muse_endpoint_t *state, float noise)
{
    *state = (muse_endpoint_t){0};
    if (!(noise >= 0)) noise = 0;
    if (noise > 300) noise = 300;
    state->threshold = noise * 3;
    if (state->threshold < 120) state->threshold = 120;
}
muse_endpoint_result_t muse_endpoint_push(muse_endpoint_t *state, float rms, uint32_t frames)
{
    if (!frames || frames > MUSE_ENDPOINT_RATE) return MUSE_ENDPOINT_LIMIT;
    state->total += frames;
    if (rms >= state->threshold) {
        state->voiced += frames;
        state->quiet = 0;
        if (state->voiced >= MUSE_ENDPOINT_RATE / 5) state->speech = true;
    } else {
        if (!state->speech) state->voiced = 0;
        state->quiet += frames;
    }
    if (state->speech && state->quiet >= MUSE_ENDPOINT_SILENCE_FRAMES) return MUSE_ENDPOINT_DONE;
    if (!state->speech && state->total >= 5u * MUSE_ENDPOINT_RATE) return MUSE_ENDPOINT_EMPTY;
    if (state->total >= MUSE_ENDPOINT_MAX_SECONDS * MUSE_ENDPOINT_RATE) return MUSE_ENDPOINT_LIMIT;
    return MUSE_ENDPOINT_LISTEN;
}
