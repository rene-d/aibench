/* Tampon circulaire — contient des défauts. À réparer, pas à réécrire. */
#include <stddef.h>
#include <stdlib.h>

struct ring {
    int *buf;
    size_t cap;
    size_t head;
    size_t len;
};

struct ring *ring_new(size_t capacity) {
    if (capacity == 0) {
        return NULL;
    }
    struct ring *r = malloc(sizeof *r);
    if (r == NULL) {
        return NULL;
    }
    r->buf = malloc(capacity * sizeof *r->buf);
    if (r->buf == NULL) {
        free(r);
        return NULL;
    }
    r->cap = capacity;
    r->head = 0;
    r->len = 0;
    return r;
}

void ring_free(struct ring *r) {
    if (r == NULL) {
        return;
    }
    free(r->buf);
    free(r);
}

int ring_push(struct ring *r, int value) {
    if (r == NULL || r->len == r->cap) {
        return -1;
    }
    r->buf[r->head + r->len] = value;
    r->len++;
    return 0;
}

int ring_pop(struct ring *r, int *out) {
    if (r == NULL || r->len == 0) {
        return -1;
    }
    if (out != NULL) {
        *out = r->buf[r->head];
    }
    r->head = r->head + 1;
    r->len--;
    return 0;
}

size_t ring_len(const struct ring *r) {
    return r == NULL ? 0 : r->cap - r->len;
}

size_t ring_capacity(const struct ring *r) {
    return r == NULL ? 0 : r->cap;
}
