#include <string.h>
#include "muse_status.h"

void muse_status_apply(muse_status_t *s, muse_event_t event)
{
    switch (event) {
    case MUSE_CONFIGURED: s->configured = true; break;
    case MUSE_WIFI_UP: s->wifi = true; break;
    case MUSE_WIFI_DOWN:
        s->wifi = false;
        // Loss of Wi-Fi invalidates the transport and handshake too.
        /* fall through */
    case MUSE_WS_DOWN:
    case MUSE_PONG_EXPIRED:
        s->gateway = s->authenticated = s->heartbeat = false;
        break;
    case MUSE_WS_UP:
        s->gateway = true;
        s->authenticated = s->heartbeat = false;
        break;
    case MUSE_HELLO:
        if (s->wifi && s->gateway) s->authenticated = true;
        break;
    case MUSE_PONG:
        if (s->wifi && s->gateway && s->authenticated) {
            s->heartbeat = s->ever_connected = true;
        }
        break;
    }
}

const char *muse_status_title(const muse_status_t *s)
{
    if (!s->configured) return "USB setup";
    if (s->wifi && s->gateway && s->authenticated && s->heartbeat) return "Connected";
    if (s->ever_connected) return "Reconnecting";
    if (s->authenticated) return "Checking heartbeat";
    if (s->gateway) return "Verifying";
    return "Connecting";
}


const char *muse_execution_label(const char *state) {
    if (!state) return "Unknown";
    if (!strcmp(state, "starting") || !strcmp(state, "queued")) return "Starting";
    if (!strcmp(state, "running")) return "Working";
    if (!strcmp(state, "waiting")) return "Waiting";
    if (!strcmp(state, "finished")) return "Ended";
    if (!strcmp(state, "failed")) return "Failed";
    return "Unknown";
}
