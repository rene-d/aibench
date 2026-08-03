#include <stdlib.h>
#include <string.h>

typedef struct LruCache LruCache;

LruCache *lru_new(size_t capacity);
void      lru_free(LruCache *c);
int       lru_get(LruCache *c, int key, int *out_value);
int       lru_put(LruCache *c, int key, int value);
size_t    lru_len(const LruCache *c);
size_t    lru_keys(const LruCache *c, int *out, size_t out_cap);

typedef struct Node {
    int          key;
    int          value;
    struct Node *prev;   /* vers le plus récent */
    struct Node *next;   /* vers le moins récent */
    struct Node *hnext;  /* chaînage dans le seau */
} Node;

struct LruCache {
    Node   **buckets;
    size_t   nbuckets;   /* puissance de deux */
    size_t   capacity;
    size_t   len;
    Node    *head;       /* le plus récemment utilisé */
    Node    *tail;       /* le moins récemment utilisé */
};

static size_t bucket_of(const LruCache *c, int key) {
    /* mélange rapide : les clés séquentielles ne doivent pas s'agglutiner */
    unsigned long h = (unsigned long)(unsigned int)key * 2654435761u;
    return (size_t)(h >> 8) & (c->nbuckets - 1);
}

LruCache *lru_new(size_t capacity) {
    if (capacity == 0) {
        return NULL;
    }
    LruCache *c = calloc(1, sizeof *c);
    if (c == NULL) {
        return NULL;
    }
    size_t n = 8;
    while (n < capacity * 2) {
        n *= 2;
    }
    c->buckets = calloc(n, sizeof *c->buckets);
    if (c->buckets == NULL) {
        free(c);
        return NULL;
    }
    c->nbuckets = n;
    c->capacity = capacity;
    return c;
}

void lru_free(LruCache *c) {
    if (c == NULL) {
        return;
    }
    Node *n = c->head;
    while (n != NULL) {
        Node *next = n->next;
        free(n);
        n = next;
    }
    free(c->buckets);
    free(c);
}

static Node *find(const LruCache *c, int key) {
    for (Node *n = c->buckets[bucket_of(c, key)]; n != NULL; n = n->hnext) {
        if (n->key == key) {
            return n;
        }
    }
    return NULL;
}

static void unlink_lru(LruCache *c, Node *n) {
    if (n->prev != NULL) {
        n->prev->next = n->next;
    } else {
        c->head = n->next;
    }
    if (n->next != NULL) {
        n->next->prev = n->prev;
    } else {
        c->tail = n->prev;
    }
    n->prev = n->next = NULL;
}

static void push_front(LruCache *c, Node *n) {
    n->prev = NULL;
    n->next = c->head;
    if (c->head != NULL) {
        c->head->prev = n;
    }
    c->head = n;
    if (c->tail == NULL) {
        c->tail = n;
    }
}

static void touch(LruCache *c, Node *n) {
    if (c->head == n) {
        return;
    }
    unlink_lru(c, n);
    push_front(c, n);
}

int lru_get(LruCache *c, int key, int *out_value) {
    if (c == NULL) {
        return 0;
    }
    Node *n = find(c, key);
    if (n == NULL) {
        return 0;
    }
    if (out_value != NULL) {
        *out_value = n->value;
    }
    touch(c, n);
    return 1;
}

static void hash_remove(LruCache *c, Node *victim) {
    Node **slot = &c->buckets[bucket_of(c, victim->key)];
    while (*slot != NULL) {
        if (*slot == victim) {
            *slot = victim->hnext;
            return;
        }
        slot = &(*slot)->hnext;
    }
}

int lru_put(LruCache *c, int key, int value) {
    if (c == NULL) {
        return -1;
    }
    Node *n = find(c, key);
    if (n != NULL) {
        n->value = value;
        touch(c, n);
        return 0;
    }
    n = malloc(sizeof *n);
    if (n == NULL) {
        return -1;
    }
    if (c->len == c->capacity) {
        Node *victim = c->tail;
        unlink_lru(c, victim);
        hash_remove(c, victim);
        free(victim);
        c->len--;
    }
    n->key = key;
    n->value = value;
    size_t b = bucket_of(c, key);
    n->hnext = c->buckets[b];
    c->buckets[b] = n;
    push_front(c, n);
    c->len++;
    return 0;
}

size_t lru_len(const LruCache *c) {
    return c == NULL ? 0 : c->len;
}

size_t lru_keys(const LruCache *c, int *out, size_t out_cap) {
    if (c == NULL || out == NULL) {
        return 0;
    }
    size_t w = 0;
    for (Node *n = c->head; n != NULL && w < out_cap; n = n->next) {
        out[w++] = n->key;
    }
    return w;
}
