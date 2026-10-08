#include "muse_pet_logic.h"
#include <stddef.h>
#include <string.h>

#define PET_COUNTER_MAX 99999u

static uint32_t checksum_word(uint32_t value, uint32_t hash)
{
    for (unsigned int byte = 0; byte < 4; ++byte) {
        hash ^= (value >> (byte * 8u)) & 0xffu;
        hash *= 16777619u;
    }
    return hash;
}

static uint32_t checksum(const muse_pet_save_t *state)
{
    uint32_t hash = 2166136261u;
    hash = checksum_word(state->magic, hash);
    hash = checksum_word(state->version, hash);
    hash = checksum_word(state->pats, hash);
    hash = checksum_word(state->treats, hash);
    hash = checksum_word(state->harvests, hash);
    for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i)
        hash = checksum_word(state->plots[i], hash);
    return hash;
}

void muse_pet_seal(muse_pet_save_t *state)
{
    if (state) {
        state->reserved = 0;
        state->checksum = checksum(state);
    }
}

void muse_pet_reset(muse_pet_save_t *state)
{
    if (!state) return;
    memset(state, 0, sizeof(*state));
    state->magic = MUSE_PET_MAGIC;
    state->version = MUSE_PET_SCHEMA_VERSION;
    muse_pet_seal(state);
}

bool muse_pet_valid(const muse_pet_save_t *state)
{
    if (!state || state->magic != MUSE_PET_MAGIC ||
        state->version != MUSE_PET_SCHEMA_VERSION ||
        state->reserved || state->pats > PET_COUNTER_MAX ||
        state->treats > PET_COUNTER_MAX || state->harvests > PET_COUNTER_MAX)
        return false;
    for (unsigned int i = 0; i < MUSE_PET_PLOTS; ++i)
        if (state->plots[i] > MUSE_PLOT_READY) return false;
    return state->checksum == checksum(state);
}

bool muse_pet_pat(muse_pet_save_t *state)
{
    if (!muse_pet_valid(state)) return false;
    if (state->pats < PET_COUNTER_MAX) ++state->pats;
    muse_pet_seal(state);
    return true;
}

bool muse_pet_feed(muse_pet_save_t *state)
{
    if (!muse_pet_valid(state)) return false;
    if (state->treats < PET_COUNTER_MAX) ++state->treats;
    muse_pet_seal(state);
    return true;
}

bool muse_pet_plot_tap(muse_pet_save_t *state, unsigned int plot)
{
    if (!muse_pet_valid(state) || plot >= MUSE_PET_PLOTS) return false;
    switch (state->plots[plot]) {
    case MUSE_PLOT_EMPTY: state->plots[plot] = MUSE_PLOT_SEEDED; break;
    case MUSE_PLOT_SEEDED: state->plots[plot] = MUSE_PLOT_GROWING; break;
    case MUSE_PLOT_READY:
        state->plots[plot] = MUSE_PLOT_EMPTY;
        if (state->harvests < PET_COUNTER_MAX) ++state->harvests;
        break;
    case MUSE_PLOT_GROWING: return false;  /* Tap never accelerates growth. */
    default: return false;
    }
    muse_pet_seal(state);
    return true;
}

bool muse_pet_mature(muse_pet_save_t *state, unsigned int plot)
{
    if (!muse_pet_valid(state) || plot >= MUSE_PET_PLOTS ||
        state->plots[plot] != MUSE_PLOT_GROWING)
        return false;
    state->plots[plot] = MUSE_PLOT_READY;
    muse_pet_seal(state);
    return true;
}
