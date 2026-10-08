#pragma once
#include <stdbool.h>
#include <stdint.h>
#define MUSE_ENDPOINT_RATE 16000u
#define MUSE_ENDPOINT_MAX_SECONDS 20u
#define MUSE_ENDPOINT_SILENCE_FRAMES (3u * MUSE_ENDPOINT_RATE)
typedef enum { MUSE_ENDPOINT_LISTEN, MUSE_ENDPOINT_DONE, MUSE_ENDPOINT_EMPTY, MUSE_ENDPOINT_LIMIT } muse_endpoint_result_t;
typedef struct {
    uint32_t total, voiced, quiet;
    float threshold;
    bool speech;
} muse_endpoint_t;
void muse_endpoint_init(muse_endpoint_t *state, float noise);
muse_endpoint_result_t muse_endpoint_push(muse_endpoint_t *state, float rms, uint32_t frames);
