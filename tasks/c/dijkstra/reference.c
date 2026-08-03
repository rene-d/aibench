#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct Graph Graph;

Graph *graph_new(size_t n);
void   graph_free(Graph *g);
int    graph_add_edge(Graph *g, size_t u, size_t v, long long w);
size_t graph_order(const Graph *g);
int    dijkstra(const Graph *g, size_t src, long long *dist, size_t *prev);
size_t dijkstra_path(const Graph *g, size_t src, size_t dst,
                     size_t *out, size_t out_cap);

typedef struct Edge {
    size_t       to;
    long long    w;
    struct Edge *next;
} Edge;

struct Graph {
    Edge  **adj;
    size_t  n;
};

Graph *graph_new(size_t n) {
    Graph *g = calloc(1, sizeof *g);
    if (g == NULL) {
        return NULL;
    }
    g->n = n;
    if (n > 0) {
        g->adj = calloc(n, sizeof *g->adj);
        if (g->adj == NULL) {
            free(g);
            return NULL;
        }
    }
    return g;
}

void graph_free(Graph *g) {
    if (g == NULL) {
        return;
    }
    for (size_t i = 0; i < g->n; i++) {
        Edge *e = g->adj[i];
        while (e != NULL) {
            Edge *next = e->next;
            free(e);
            e = next;
        }
    }
    free(g->adj);
    free(g);
}

int graph_add_edge(Graph *g, size_t u, size_t v, long long w) {
    if (g == NULL || u >= g->n || v >= g->n || w <= 0) {
        return -1;
    }
    Edge *e = malloc(sizeof *e);
    if (e == NULL) {
        return -1;
    }
    e->to = v;
    e->w = w;
    e->next = g->adj[u];
    g->adj[u] = e;
    return 0;
}

size_t graph_order(const Graph *g) {
    return g == NULL ? 0 : g->n;
}

/* Tas binaire min sur (distance, sommet), avec suppression paresseuse. */
typedef struct {
    long long d;
    size_t    v;
} HeapItem;

typedef struct {
    HeapItem *a;
    size_t    len;
    size_t    cap;
} Heap;

static int heap_less(const HeapItem *x, const HeapItem *y) {
    if (x->d != y->d) {
        return x->d < y->d;
    }
    return x->v < y->v;
}

static int heap_push(Heap *h, long long d, size_t v) {
    if (h->len == h->cap) {
        size_t cap = h->cap ? h->cap * 2 : 64;
        HeapItem *a = realloc(h->a, cap * sizeof *a);
        if (a == NULL) {
            return -1;
        }
        h->a = a;
        h->cap = cap;
    }
    size_t i = h->len++;
    h->a[i].d = d;
    h->a[i].v = v;
    while (i > 0) {
        size_t parent = (i - 1) / 2;
        if (!heap_less(&h->a[i], &h->a[parent])) {
            break;
        }
        HeapItem tmp = h->a[i];
        h->a[i] = h->a[parent];
        h->a[parent] = tmp;
        i = parent;
    }
    return 0;
}

static HeapItem heap_pop(Heap *h) {
    HeapItem top = h->a[0];
    h->a[0] = h->a[--h->len];
    size_t i = 0;
    for (;;) {
        size_t l = 2 * i + 1, r = l + 1, best = i;
        if (l < h->len && heap_less(&h->a[l], &h->a[best])) {
            best = l;
        }
        if (r < h->len && heap_less(&h->a[r], &h->a[best])) {
            best = r;
        }
        if (best == i) {
            break;
        }
        HeapItem tmp = h->a[i];
        h->a[i] = h->a[best];
        h->a[best] = tmp;
        i = best;
    }
    return top;
}

int dijkstra(const Graph *g, size_t src, long long *dist, size_t *prev) {
    if (g == NULL || dist == NULL || src >= g->n) {
        return -1;
    }
    for (size_t i = 0; i < g->n; i++) {
        dist[i] = LLONG_MAX;
        if (prev != NULL) {
            prev[i] = SIZE_MAX;
        }
    }
    char *done = calloc(g->n, sizeof *done);
    if (done == NULL) {
        return -1;
    }
    Heap h = {NULL, 0, 0};
    dist[src] = 0;
    if (heap_push(&h, 0, src) != 0) {
        free(done);
        free(h.a);
        return -1;
    }
    while (h.len > 0) {
        HeapItem top = heap_pop(&h);
        size_t u = top.v;
        if (done[u]) {
            continue; /* entrée périmée */
        }
        done[u] = 1;
        for (Edge *e = g->adj[u]; e != NULL; e = e->next) {
            long long cand = dist[u] + e->w;
            if (cand < dist[e->to]) {
                dist[e->to] = cand;
                if (prev != NULL) {
                    prev[e->to] = u;
                }
                if (heap_push(&h, cand, e->to) != 0) {
                    free(done);
                    free(h.a);
                    return -1;
                }
            } else if (cand == dist[e->to] && prev != NULL && u < prev[e->to]) {
                /* même distance : on garde le plus petit prédécesseur */
                prev[e->to] = u;
            }
        }
    }
    free(done);
    free(h.a);
    return 0;
}

size_t dijkstra_path(const Graph *g, size_t src, size_t dst,
                     size_t *out, size_t out_cap) {
    if (g == NULL || src >= g->n || dst >= g->n) {
        return 0;
    }
    long long *dist = malloc(g->n * sizeof *dist);
    size_t *prev = malloc(g->n * sizeof *prev);
    if (dist == NULL || prev == NULL) {
        free(dist);
        free(prev);
        return 0;
    }
    if (dijkstra(g, src, dist, prev) != 0 || dist[dst] == LLONG_MAX) {
        free(dist);
        free(prev);
        return 0;
    }

    size_t len = 1;
    for (size_t v = dst; v != src; v = prev[v]) {
        len++;
    }
    if (out != NULL && out_cap >= len) {
        size_t i = len;
        for (size_t v = dst;; v = prev[v]) {
            out[--i] = v;
            if (v == src) {
                break;
            }
        }
    }
    free(dist);
    free(prev);
    return len;
}
