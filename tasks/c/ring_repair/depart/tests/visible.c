/* Test fourni avec l'énoncé. Il fait partie du contrat : ne le modifie pas. */
#include "harness.h"
#include <stddef.h>

struct ring;
struct ring *ring_new(size_t capacity);
void ring_free(struct ring *r);
int ring_push(struct ring *r, int value);
int ring_pop(struct ring *r, int *out);
size_t ring_len(const struct ring *r);
size_t ring_capacity(const struct ring *r);

TEST(longueur_apres_ajouts) {
    struct ring *r = ring_new(4);
    CHECK_NOT_NULL(r);
    CHECK_UINT_EQ(ring_len(r), 0u);
    CHECK_INT_EQ(ring_push(r, 10), 0);
    CHECK_INT_EQ(ring_push(r, 20), 0);
    CHECK_UINT_EQ(ring_len(r), 2u);
    CHECK_UINT_EQ(ring_capacity(r), 4u);
    ring_free(r);
}

TEST(fifo_apres_plusieurs_tours) {
    struct ring *r = ring_new(3);
    CHECK_NOT_NULL(r);
    int out = 0;
    for (int tour = 0; tour < 4; tour++) {
        CHECK_INT_EQ(ring_push(r, tour * 10 + 1), 0);
        CHECK_INT_EQ(ring_push(r, tour * 10 + 2), 0);
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, tour * 10 + 1);
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, tour * 10 + 2);
        CHECK_UINT_EQ(ring_len(r), 0u);
    }
    ring_free(r);
}
