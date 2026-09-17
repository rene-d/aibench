#include "harness.h"
#include <stddef.h>

struct ring;
struct ring *ring_new(size_t capacity);
void ring_free(struct ring *r);
int ring_push(struct ring *r, int value);
int ring_pop(struct ring *r, int *out);
size_t ring_len(const struct ring *r);
size_t ring_capacity(const struct ring *r);

TEST(new_refuse_capacite_nulle) {
    CHECK_NULL(ring_new(0));
}

TEST(free_accepte_null) {
    ring_free(NULL);
}

TEST(longueur_et_capacite_sur_null) {
    CHECK_UINT_EQ(ring_len(NULL), 0u);
    CHECK_UINT_EQ(ring_capacity(NULL), 0u);
}

TEST(push_pop_sur_null) {
    int out = 0;
    CHECK_INT_EQ(ring_push(NULL, 1), -1);
    CHECK_INT_EQ(ring_pop(NULL, &out), -1);
}

TEST(pop_sur_vide) {
    struct ring *r = ring_new(2);
    int out = 42;
    CHECK_INT_EQ(ring_pop(r, &out), -1);
    CHECK_INT_EQ(out, 42);
    ring_free(r);
}

TEST(capacite_est_conservee) {
    struct ring *r = ring_new(7);
    CHECK_UINT_EQ(ring_capacity(r), 7u);
    CHECK_INT_EQ(ring_push(r, 1), 0);
    CHECK_UINT_EQ(ring_capacity(r), 7u);
    ring_free(r);
}

TEST(longueur_suit_les_ajouts_et_retraits) {
    struct ring *r = ring_new(3);
    CHECK_UINT_EQ(ring_len(r), 0u);
    ring_push(r, 1);
    CHECK_UINT_EQ(ring_len(r), 1u);
    ring_push(r, 2);
    ring_push(r, 3);
    CHECK_UINT_EQ(ring_len(r), 3u);
    int out = 0;
    ring_pop(r, &out);
    CHECK_UINT_EQ(ring_len(r), 2u);
    ring_free(r);
}

TEST(push_refuse_quand_plein) {
    struct ring *r = ring_new(2);
    CHECK_INT_EQ(ring_push(r, 1), 0);
    CHECK_INT_EQ(ring_push(r, 2), 0);
    CHECK_INT_EQ(ring_push(r, 3), -1);
    CHECK_UINT_EQ(ring_len(r), 2u);
    ring_free(r);
}

TEST(ordre_fifo_simple) {
    struct ring *r = ring_new(4);
    for (int i = 1; i <= 4; i++) {
        CHECK_INT_EQ(ring_push(r, i), 0);
    }
    for (int i = 1; i <= 4; i++) {
        int out = 0;
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, i);
    }
    ring_free(r);
}

TEST(pop_accepte_out_null) {
    struct ring *r = ring_new(2);
    ring_push(r, 9);
    CHECK_INT_EQ(ring_pop(r, NULL), 0);
    CHECK_UINT_EQ(ring_len(r), 0u);
    ring_free(r);
}

TEST(enroulement_capacite_un) {
    struct ring *r = ring_new(1);
    int out = 0;
    for (int i = 0; i < 5; i++) {
        CHECK_INT_EQ(ring_push(r, i), 0);
        CHECK_INT_EQ(ring_push(r, i), -1);
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, i);
    }
    ring_free(r);
}

TEST(enroulement_partiel) {
    struct ring *r = ring_new(3);
    int out = 0;
    ring_push(r, 1);
    ring_push(r, 2);
    CHECK_INT_EQ(ring_pop(r, &out), 0);
    CHECK_INT_EQ(out, 1);
    ring_push(r, 3);
    ring_push(r, 4);
    CHECK_UINT_EQ(ring_len(r), 3u);
    CHECK_INT_EQ(ring_push(r, 5), -1);
    int attendus[] = {2, 3, 4};
    for (int i = 0; i < 3; i++) {
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, attendus[i]);
    }
    ring_free(r);
}

TEST(long_cycle_reste_fifo) {
    struct ring *r = ring_new(5);
    int out = 0;
    int attendu = 0;
    int prochain = 0;
    for (int i = 0; i < 4; i++) {
        CHECK_INT_EQ(ring_push(r, prochain++), 0);
    }
    /* le tampon reste presque plein : chaque tour repasse par le début */
    for (int i = 0; i < 200; i++) {
        CHECK_INT_EQ(ring_push(r, prochain++), 0);
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, attendu++);
    }
    while (ring_len(r) > 0) {
        CHECK_INT_EQ(ring_pop(r, &out), 0);
        CHECK_INT_EQ(out, attendu++);
    }
    CHECK_INT_EQ(attendu, prochain);
    ring_free(r);
}

TEST(vider_puis_reremplir) {
    struct ring *r = ring_new(3);
    int out = 0;
    for (int i = 0; i < 3; i++) {
        ring_push(r, i);
    }
    while (ring_pop(r, &out) == 0) {
    }
    CHECK_UINT_EQ(ring_len(r), 0u);
    CHECK_INT_EQ(ring_push(r, 77), 0);
    CHECK_INT_EQ(ring_pop(r, &out), 0);
    CHECK_INT_EQ(out, 77);
    ring_free(r);
}

TEST(deux_tampons_independants) {
    struct ring *a = ring_new(2);
    struct ring *b = ring_new(2);
    int out = 0;
    ring_push(a, 1);
    ring_push(b, 2);
    CHECK_INT_EQ(ring_pop(a, &out), 0);
    CHECK_INT_EQ(out, 1);
    CHECK_INT_EQ(ring_pop(b, &out), 0);
    CHECK_INT_EQ(out, 2);
    ring_free(a);
    ring_free(b);
}
