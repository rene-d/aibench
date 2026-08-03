#include "harness.h"
#include <time.h>

typedef struct LruCache LruCache;

LruCache *lru_new(size_t capacity);
void      lru_free(LruCache *c);
int       lru_get(LruCache *c, int key, int *out_value);
int       lru_put(LruCache *c, int key, int value);
size_t    lru_len(const LruCache *c);
size_t    lru_keys(const LruCache *c, int *out, size_t out_cap);

TEST(new_and_free) {
    LruCache *c = lru_new(4);
    CHECK_NOT_NULL(c);
    CHECK_UINT_EQ(lru_len(c), 0);
    lru_free(c);
}

TEST(zero_capacity_is_null) {
    CHECK_NULL(lru_new(0));
}

TEST(free_null_is_a_noop) {
    lru_free(NULL);
    CHECK(1);
}

TEST(put_then_get) {
    LruCache *c = lru_new(2);
    int v = -1;
    CHECK_INT_EQ(lru_put(c, 1, 10), 0);
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 10);
    CHECK_UINT_EQ(lru_len(c), 1);
    lru_free(c);
}

TEST(missing_key_leaves_out_value_alone) {
    LruCache *c = lru_new(2);
    int v = 4242;
    CHECK_INT_EQ(lru_get(c, 7, &v), 0);
    CHECK_INT_EQ(v, 4242);
    lru_free(c);
}

TEST(zero_is_a_normal_value) {
    LruCache *c = lru_new(2);
    lru_put(c, 1, 0);
    int v = -1;
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 0);
    CHECK_INT_EQ(lru_get(c, 2, &v), 0);
    lru_free(c);
}

TEST(update_existing_key) {
    LruCache *c = lru_new(2);
    lru_put(c, 1, 10);
    lru_put(c, 1, 20);
    int v = 0;
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 20);
    CHECK_UINT_EQ(lru_len(c), 1);
    lru_free(c);
}

TEST(leetcode_146_scenario) {
    LruCache *c = lru_new(2);
    int v = 0;
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 1);
    lru_put(c, 3, 3);                       /* évince 2 */
    CHECK_INT_EQ(lru_get(c, 2, &v), 0);
    lru_put(c, 4, 4);                       /* évince 1 */
    CHECK_INT_EQ(lru_get(c, 1, &v), 0);
    CHECK_INT_EQ(lru_get(c, 3, &v), 1);
    CHECK_INT_EQ(v, 3);
    CHECK_INT_EQ(lru_get(c, 4, &v), 1);
    CHECK_INT_EQ(v, 4);
    CHECK_UINT_EQ(lru_len(c), 2);
    lru_free(c);
}

TEST(keys_are_ordered_most_recent_first) {
    LruCache *c = lru_new(3);
    int k[3] = {0, 0, 0};
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    lru_put(c, 3, 3);
    CHECK_UINT_EQ(lru_keys(c, k, 3), 3);
    CHECK_INT_EQ(k[0], 3);
    CHECK_INT_EQ(k[1], 2);
    CHECK_INT_EQ(k[2], 1);
    lru_get(c, 1, NULL);
    CHECK_UINT_EQ(lru_keys(c, k, 3), 3);
    CHECK_INT_EQ(k[0], 1);
    CHECK_INT_EQ(k[1], 3);
    CHECK_INT_EQ(k[2], 2);
    lru_free(c);
}

TEST(get_with_null_out_still_refreshes) {
    LruCache *c = lru_new(2);
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    CHECK_INT_EQ(lru_get(c, 1, NULL), 1);   /* 1 devient le plus récent */
    lru_put(c, 3, 3);                       /* doit évincer 2, pas 1 */
    int v = 0;
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 1);
    CHECK_INT_EQ(lru_get(c, 2, &v), 0);
    lru_free(c);
}

TEST(update_does_not_evict) {
    LruCache *c = lru_new(2);
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    lru_put(c, 1, 100);      /* mise à jour : rien ne doit sauter */
    CHECK_UINT_EQ(lru_len(c), 2);
    int v = 0;
    CHECK_INT_EQ(lru_get(c, 2, &v), 1);
    CHECK_INT_EQ(v, 2);
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 100);
    lru_free(c);
}

TEST(update_refreshes_recency) {
    LruCache *c = lru_new(2);
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    lru_put(c, 1, 100);      /* 1 devient le plus récent */
    lru_put(c, 3, 3);        /* doit évincer 2 */
    int v = 0;
    CHECK_INT_EQ(lru_get(c, 2, &v), 0);
    CHECK_INT_EQ(lru_get(c, 1, &v), 1);
    CHECK_INT_EQ(v, 100);
    lru_free(c);
}

TEST(capacity_one) {
    LruCache *c = lru_new(1);
    int v = 0;
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    CHECK_UINT_EQ(lru_len(c), 1);
    CHECK_INT_EQ(lru_get(c, 1, &v), 0);
    CHECK_INT_EQ(lru_get(c, 2, &v), 1);
    CHECK_INT_EQ(v, 2);
    lru_put(c, 2, 22);
    CHECK_UINT_EQ(lru_len(c), 1);
    CHECK_INT_EQ(lru_get(c, 2, &v), 1);
    CHECK_INT_EQ(v, 22);
    lru_free(c);
}

TEST(keys_truncates_to_out_cap) {
    LruCache *c = lru_new(4);
    int k[2] = {0, 0};
    lru_put(c, 1, 1);
    lru_put(c, 2, 2);
    lru_put(c, 3, 3);
    CHECK_UINT_EQ(lru_keys(c, k, 2), 2);
    CHECK_INT_EQ(k[0], 3);
    CHECK_INT_EQ(k[1], 2);
    CHECK_UINT_EQ(lru_keys(c, k, 0), 0);
    lru_free(c);
}

TEST(negative_keys) {
    LruCache *c = lru_new(3);
    int v = 0;
    lru_put(c, -1, 11);
    lru_put(c, -2147483647 - 1, 22);
    lru_put(c, 2147483647, 33);
    CHECK_INT_EQ(lru_get(c, -1, &v), 1);
    CHECK_INT_EQ(v, 11);
    CHECK_INT_EQ(lru_get(c, -2147483647 - 1, &v), 1);
    CHECK_INT_EQ(v, 22);
    CHECK_INT_EQ(lru_get(c, 2147483647, &v), 1);
    CHECK_INT_EQ(v, 33);
    lru_free(c);
}

TEST(eviction_stays_correct_over_many_rounds) {
    /* la fenêtre glisse : à tout instant seules les 8 dernières clés sont là */
    LruCache *c = lru_new(8);
    for (int i = 0; i < 500; i++) {
        lru_put(c, i, i * 3);
    }
    CHECK_UINT_EQ(lru_len(c), 8);
    int v = 0;
    for (int i = 492; i < 500; i++) {
        if (lru_get(c, i, &v) != 1 || v != i * 3) {
            lru_free(c);
            TH_FAILF("la clé %d devait être présente avec la valeur %d", i, i * 3);
        }
    }
    for (int i = 0; i < 492; i++) {
        if (lru_get(c, i, &v) != 0) {
            lru_free(c);
            TH_FAILF("la clé %d aurait dû être évincée", i);
        }
    }
    lru_free(c);
}

TEST(operations_are_constant_time) {
    enum { CAP = 20000, OPS = 200000 };
    LruCache *c = lru_new(CAP);
    CHECK_NOT_NULL(c);
    clock_t t0 = clock();
    unsigned long rng = 12345;
    int v = 0;
    for (int i = 0; i < OPS; i++) {
        rng = rng * 1103515245u + 12345u;
        int key = (int)((rng >> 16) % (CAP * 2));
        if (i % 3 == 0) {
            lru_get(c, key, &v);
        } else {
            lru_put(c, key, key ^ 0x5a5a);
        }
        if ((i & 1023) == 0 &&
            (double)(clock() - t0) / CLOCKS_PER_SEC > 10.0) {
            lru_free(c);
            TH_FAILF("plus de 10 s pour %d opérations : les accès ne sont pas en O(1)", i);
        }
    }
    CHECK_UINT_EQ(lru_len(c), CAP);
    lru_free(c);
}
