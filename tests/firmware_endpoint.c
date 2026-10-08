#include <assert.h>
#include "muse_endpoint.h"
static muse_endpoint_result_t blocks(muse_endpoint_t *s, float rms, int count)
{
    muse_endpoint_result_t r = MUSE_ENDPOINT_LISTEN;
    for (int i = 0; i < count; i++) r = muse_endpoint_push(s, rms, 1600);
    return r;
}
int main(void)
{
    muse_endpoint_t s;
    muse_endpoint_init(&s, 30);
    assert(blocks(&s, 500, 60) == MUSE_ENDPOINT_LISTEN); /* speaks longer than old 5s */
    assert(blocks(&s, 0, 20) == MUSE_ENDPOINT_LISTEN); /* two-second pause */
    assert(blocks(&s, 500, 20) == MUSE_ENDPOINT_LISTEN); /* continues speech */
    assert(blocks(&s, 0, 29) == MUSE_ENDPOINT_LISTEN);
    assert(blocks(&s, 0, 1) == MUSE_ENDPOINT_DONE); /* full 3-second pause */
    muse_endpoint_init(&s, 30);
    assert(blocks(&s, 0, 49) == MUSE_ENDPOINT_LISTEN);
    assert(blocks(&s, 0, 1) == MUSE_ENDPOINT_EMPTY);
    muse_endpoint_init(&s, 30);
    assert(blocks(&s, 500, 199) == MUSE_ENDPOINT_LISTEN);
    assert(blocks(&s, 500, 1) == MUSE_ENDPOINT_LIMIT);
    muse_endpoint_init(&s, 100);
    assert(blocks(&s, 200, 50) == MUSE_ENDPOINT_EMPTY); /* background below calibrated threshold */
    muse_endpoint_init(&s, 30);
    assert(blocks(&s, 500, 1) == MUSE_ENDPOINT_LISTEN); /* isolated click is not speech */
    assert(blocks(&s, 0, 49) == MUSE_ENDPOINT_EMPTY);
    return 0;
}
