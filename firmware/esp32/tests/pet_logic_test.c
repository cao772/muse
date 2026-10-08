#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../main/muse_pet_logic.h"

int main(void)
{
    muse_pet_save_t state;
    muse_pet_reset(&state);
    assert(muse_pet_valid(&state));
    assert(state.version == MUSE_PET_SCHEMA_VERSION);
    assert(!muse_pet_plot_tap(&state, 3));
    assert(!muse_pet_mature(&state, 0));
    for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i) {
        assert(state.plots[i] == MUSE_PLOT_EMPTY);
        assert(muse_pet_plot_tap(&state, i));
        assert(state.plots[i] == MUSE_PLOT_SEEDED);
        assert(muse_pet_plot_tap(&state, i));
        assert(state.plots[i] == MUSE_PLOT_GROWING);
        assert(!muse_pet_plot_tap(&state, i)); /* No tap-to-skip maturity. */
        assert(muse_pet_mature(&state, i));
        assert(state.plots[i] == MUSE_PLOT_READY);
        assert(muse_pet_plot_tap(&state, i));
        assert(state.plots[i] == MUSE_PLOT_EMPTY);
    }
    assert(state.harvests == 3);
    assert(muse_pet_pat(&state));
    assert(muse_pet_feed(&state));
    assert(state.pats == 1 && state.treats == 1);
    assert(muse_pet_valid(&state));

    muse_pet_save_t saved = state;
    assert(muse_pet_valid(&saved));
    saved.plots[0] ^= 1;
    assert(!muse_pet_valid(&saved)); /* Detect damaged NVS payload. */
    saved = state;
    saved.version = 2;
    muse_pet_seal(&saved);
    assert(!muse_pet_valid(&saved)); /* Reject future version. */
    saved = state;
    saved.plots[0] = 250;
    muse_pet_seal(&saved);
    assert(!muse_pet_valid(&saved)); /* Reject impossible state. */
    saved = state;
    saved.reserved = 1;
    assert(!muse_pet_valid(&saved));
    assert(!muse_pet_pat(NULL) && !muse_pet_feed(NULL));
    assert(!muse_pet_plot_tap(&saved, 0));
    /* Pet and crops never die or decay for lack of interaction. */
    printf("pet_logic native tests PASS\n");
    return 0;
}
