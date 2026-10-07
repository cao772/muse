#pragma once
#include <stdbool.h>

typedef enum {
    MUSE_CONFIGURED, MUSE_WIFI_UP, MUSE_WIFI_DOWN,
    MUSE_WS_UP, MUSE_WS_DOWN, MUSE_HELLO, MUSE_PONG, MUSE_PONG_EXPIRED
} muse_event_t;

typedef struct {
    bool configured, wifi, gateway, authenticated, heartbeat, ever_connected;
} muse_status_t;

void muse_status_apply(muse_status_t *status, muse_event_t event);
const char *muse_status_title(const muse_status_t *status);
