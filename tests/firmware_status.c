#include <assert.h>
#include <string.h>
#include "muse_status.h"

int main(void)
{
    muse_status_t s = {0};
    assert(strcmp(muse_status_title(&s), "USB setup") == 0);
    // A stale pong must not make an unauthenticated device appear connected.
    muse_status_apply(&s, MUSE_PONG);
    assert(!s.heartbeat);
    muse_status_apply(&s, MUSE_CONFIGURED);
    assert(strcmp(muse_status_title(&s), "Connecting") == 0);
    muse_status_apply(&s, MUSE_WIFI_UP);
    muse_status_apply(&s, MUSE_WS_UP);
    assert(!s.authenticated && !s.heartbeat);
    muse_status_apply(&s, MUSE_HELLO);
    assert(strcmp(muse_status_title(&s), "Checking heartbeat") == 0);
    muse_status_apply(&s, MUSE_PONG);
    assert(strcmp(muse_status_title(&s), "Connected") == 0);
    muse_status_apply(&s, MUSE_WS_DOWN);
    assert(s.wifi && !s.gateway && !s.authenticated && !s.heartbeat);
    assert(strcmp(muse_status_title(&s), "Reconnecting") == 0);
    muse_status_apply(&s, MUSE_PONG);
    assert(!s.heartbeat);
    muse_status_apply(&s, MUSE_WS_UP);
    muse_status_apply(&s, MUSE_HELLO);
    assert(!s.heartbeat);
    muse_status_apply(&s, MUSE_PONG);
    assert(strcmp(muse_status_title(&s), "Connected") == 0);
    muse_status_apply(&s, MUSE_WIFI_DOWN);
    assert(!s.wifi && !s.gateway && !s.authenticated && !s.heartbeat);
    muse_status_apply(&s, MUSE_HELLO);
    assert(!s.authenticated);
    muse_status_apply(&s, MUSE_WIFI_UP);
    muse_status_apply(&s, MUSE_WS_UP);
    muse_status_apply(&s, MUSE_HELLO);
    muse_status_apply(&s, MUSE_PONG);
    muse_status_apply(&s, MUSE_PONG_EXPIRED);
    assert(!s.gateway && !s.authenticated && !s.heartbeat);
    assert(strcmp(muse_status_title(&s), "Reconnecting") == 0);
    return 0;
}
