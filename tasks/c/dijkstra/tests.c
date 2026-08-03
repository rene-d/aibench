#include "harness.h"
#include <limits.h>
#include <stdint.h>
#include <time.h>

typedef struct Graph Graph;

Graph *graph_new(size_t n);
void   graph_free(Graph *g);
int    graph_add_edge(Graph *g, size_t u, size_t v, long long w);
size_t graph_order(const Graph *g);
int    dijkstra(const Graph *g, size_t src, long long *dist, size_t *prev);
size_t dijkstra_path(const Graph *g, size_t src, size_t dst,
                     size_t *out, size_t out_cap);

TEST(new_free_and_order) {
    Graph *g = graph_new(5);
    CHECK_NOT_NULL(g);
    CHECK_UINT_EQ(graph_order(g), 5);
    graph_free(g);
    graph_free(NULL);
    CHECK_UINT_EQ(graph_order(NULL), 0);
}

TEST(empty_graph_is_valid) {
    Graph *g = graph_new(0);
    CHECK_NOT_NULL(g);
    CHECK_UINT_EQ(graph_order(g), 0);
    CHECK_INT_EQ(dijkstra(g, 0, NULL, NULL), -1);
    graph_free(g);
}

TEST(add_edge_rejects_bad_arguments) {
    Graph *g = graph_new(3);
    CHECK_INT_EQ(graph_add_edge(g, 0, 3, 1), -1);   /* v hors bornes */
    CHECK_INT_EQ(graph_add_edge(g, 3, 0, 1), -1);   /* u hors bornes */
    CHECK_INT_EQ(graph_add_edge(g, 0, 1, 0), -1);   /* poids nul */
    CHECK_INT_EQ(graph_add_edge(g, 0, 1, -5), -1);  /* poids négatif */
    CHECK_INT_EQ(graph_add_edge(NULL, 0, 1, 1), -1);
    CHECK_INT_EQ(graph_add_edge(g, 0, 1, 1), 0);
    long long dist[3];
    CHECK_INT_EQ(dijkstra(g, 0, dist, NULL), 0);
    CHECK_INT_EQ(dist[1], 1);
    CHECK(dist[2] == LLONG_MAX);
    graph_free(g);
}

TEST(spec_example) {
    Graph *g = graph_new(5);
    graph_add_edge(g, 0, 1, 4);
    graph_add_edge(g, 0, 2, 1);
    graph_add_edge(g, 2, 1, 2);
    graph_add_edge(g, 1, 3, 1);
    graph_add_edge(g, 2, 3, 5);
    long long dist[5];
    size_t prev[5];
    CHECK_INT_EQ(dijkstra(g, 0, dist, prev), 0);
    CHECK_INT_EQ(dist[0], 0);
    CHECK_INT_EQ(dist[1], 3);
    CHECK_INT_EQ(dist[2], 1);
    CHECK_INT_EQ(dist[3], 4);
    CHECK(dist[4] == LLONG_MAX);
    CHECK(prev[0] == SIZE_MAX);
    CHECK_UINT_EQ(prev[1], 2);
    CHECK_UINT_EQ(prev[2], 0);
    CHECK_UINT_EQ(prev[3], 1);
    CHECK(prev[4] == SIZE_MAX);

    size_t path[5];
    CHECK_UINT_EQ(dijkstra_path(g, 0, 3, path, 5), 4);
    CHECK_UINT_EQ(path[0], 0);
    CHECK_UINT_EQ(path[1], 2);
    CHECK_UINT_EQ(path[2], 1);
    CHECK_UINT_EQ(path[3], 3);
    graph_free(g);
}

TEST(edges_are_directed) {
    Graph *g = graph_new(2);
    graph_add_edge(g, 0, 1, 7);
    long long dist[2];
    CHECK_INT_EQ(dijkstra(g, 1, dist, NULL), 0);
    CHECK_INT_EQ(dist[1], 0);
    CHECK(dist[0] == LLONG_MAX);
    graph_free(g);
}

TEST(parallel_edges_keep_the_lightest) {
    Graph *g = graph_new(2);
    graph_add_edge(g, 0, 1, 9);
    graph_add_edge(g, 0, 1, 2);
    graph_add_edge(g, 0, 1, 5);
    long long dist[2];
    CHECK_INT_EQ(dijkstra(g, 0, dist, NULL), 0);
    CHECK_INT_EQ(dist[1], 2);
    graph_free(g);
}

TEST(self_loops_are_harmless) {
    Graph *g = graph_new(2);
    CHECK_INT_EQ(graph_add_edge(g, 0, 0, 3), 0);
    graph_add_edge(g, 0, 1, 1);
    long long dist[2];
    size_t prev[2];
    CHECK_INT_EQ(dijkstra(g, 0, dist, prev), 0);
    CHECK_INT_EQ(dist[0], 0);
    CHECK_INT_EQ(dist[1], 1);
    CHECK(prev[0] == SIZE_MAX);
    graph_free(g);
}

TEST(prev_may_be_null) {
    Graph *g = graph_new(3);
    graph_add_edge(g, 0, 1, 1);
    graph_add_edge(g, 1, 2, 1);
    long long dist[3];
    CHECK_INT_EQ(dijkstra(g, 0, dist, NULL), 0);
    CHECK_INT_EQ(dist[2], 2);
    graph_free(g);
}

TEST(dijkstra_rejects_bad_arguments) {
    Graph *g = graph_new(2);
    long long dist[2];
    CHECK_INT_EQ(dijkstra(NULL, 0, dist, NULL), -1);
    CHECK_INT_EQ(dijkstra(g, 2, dist, NULL), -1);
    CHECK_INT_EQ(dijkstra(g, 0, NULL, NULL), -1);
    graph_free(g);
}

TEST(tie_break_picks_the_smallest_predecessor) {
    /* 0→1→3 et 0→2→3 coûtent 2 : prev[3] doit valoir 1 */
    for (int order = 0; order < 2; order++) {
        Graph *g = graph_new(4);
        if (order == 0) {
            graph_add_edge(g, 0, 1, 1);
            graph_add_edge(g, 0, 2, 1);
            graph_add_edge(g, 1, 3, 1);
            graph_add_edge(g, 2, 3, 1);
        } else {
            /* ordre d'insertion inversé : le résultat ne doit pas changer */
            graph_add_edge(g, 2, 3, 1);
            graph_add_edge(g, 1, 3, 1);
            graph_add_edge(g, 0, 2, 1);
            graph_add_edge(g, 0, 1, 1);
        }
        long long dist[4];
        size_t prev[4];
        dijkstra(g, 0, dist, prev);
        int ok = dist[3] == 2 && prev[3] == 1;
        graph_free(g);
        if (!ok) {
            TH_FAILF("ordre %d : prev[3] devait valoir 1 pour dist[3] == 2", order);
        }
    }
}

TEST(tie_break_across_different_depths) {
    /* vers 4 : 0→3→4 (10+5) et 0→1→2→4 (2+3+10) coûtent tous 15 */
    Graph *g = graph_new(5);
    graph_add_edge(g, 0, 1, 2);
    graph_add_edge(g, 1, 2, 3);
    graph_add_edge(g, 2, 4, 10);
    graph_add_edge(g, 0, 3, 10);
    graph_add_edge(g, 3, 4, 5);
    long long dist[5];
    size_t prev[5];
    dijkstra(g, 0, dist, prev);
    CHECK_INT_EQ(dist[4], 15);
    CHECK_UINT_EQ(prev[4], 2);   /* min(2, 3) */

    size_t path[5];
    CHECK_UINT_EQ(dijkstra_path(g, 0, 4, path, 5), 4);
    CHECK_UINT_EQ(path[0], 0);
    CHECK_UINT_EQ(path[1], 1);
    CHECK_UINT_EQ(path[2], 2);
    CHECK_UINT_EQ(path[3], 4);
    graph_free(g);
}

TEST(unreachable_vertices) {
    Graph *g = graph_new(4);
    graph_add_edge(g, 0, 1, 1);
    graph_add_edge(g, 2, 3, 1);
    long long dist[4];
    size_t prev[4];
    dijkstra(g, 0, dist, prev);
    CHECK(dist[2] == LLONG_MAX);
    CHECK(dist[3] == LLONG_MAX);
    CHECK(prev[2] == SIZE_MAX);
    CHECK(prev[3] == SIZE_MAX);
    size_t path[4];
    CHECK_UINT_EQ(dijkstra_path(g, 0, 3, path, 4), 0);
    graph_free(g);
}

TEST(path_from_a_vertex_to_itself) {
    Graph *g = graph_new(3);
    graph_add_edge(g, 0, 1, 1);
    size_t path[3] = {99, 99, 99};
    CHECK_UINT_EQ(dijkstra_path(g, 1, 1, path, 3), 1);
    CHECK_UINT_EQ(path[0], 1);
    CHECK_UINT_EQ(path[1], 99);
    graph_free(g);
}

TEST(path_does_not_write_when_the_buffer_is_too_small) {
    Graph *g = graph_new(3);
    graph_add_edge(g, 0, 1, 1);
    graph_add_edge(g, 1, 2, 1);
    size_t path[3] = {77, 77, 77};
    CHECK_UINT_EQ(dijkstra_path(g, 0, 2, path, 2), 3);
    CHECK_UINT_EQ(path[0], 77);
    CHECK_UINT_EQ(path[1], 77);
    CHECK_UINT_EQ(path[2], 77);
    CHECK_UINT_EQ(dijkstra_path(g, 0, 2, NULL, 0), 3);
    CHECK_UINT_EQ(dijkstra_path(g, 0, 2, path, 3), 3);
    CHECK_UINT_EQ(path[0], 0);
    CHECK_UINT_EQ(path[2], 2);
    graph_free(g);
}

TEST(path_rejects_bad_arguments) {
    Graph *g = graph_new(2);
    size_t path[2];
    CHECK_UINT_EQ(dijkstra_path(NULL, 0, 1, path, 2), 0);
    CHECK_UINT_EQ(dijkstra_path(g, 2, 1, path, 2), 0);
    CHECK_UINT_EQ(dijkstra_path(g, 0, 2, path, 2), 0);
    graph_free(g);
}

TEST(large_weights_do_not_overflow) {
    Graph *g = graph_new(4);
    long long big = 1000000000000LL;
    graph_add_edge(g, 0, 1, big);
    graph_add_edge(g, 1, 2, big);
    graph_add_edge(g, 2, 3, big);
    long long dist[4];
    dijkstra(g, 0, dist, NULL);
    CHECK_INT_EQ(dist[3], 3 * big);
    graph_free(g);
}

TEST(greedy_shortcut_is_not_the_shortest_path) {
    /* l'arête directe 0→4 coûte 100, le détour n'en coûte que 40 */
    Graph *g = graph_new(5);
    graph_add_edge(g, 0, 4, 100);
    graph_add_edge(g, 0, 1, 10);
    graph_add_edge(g, 1, 2, 10);
    graph_add_edge(g, 2, 3, 10);
    graph_add_edge(g, 3, 4, 10);
    long long dist[5];
    size_t prev[5];
    dijkstra(g, 0, dist, prev);
    CHECK_INT_EQ(dist[4], 40);
    CHECK_UINT_EQ(prev[4], 3);
    size_t path[5];
    CHECK_UINT_EQ(dijkstra_path(g, 0, 4, path, 5), 5);
    graph_free(g);
}

TEST(grid_of_shortest_paths) {
    /* grille 20×20 orientée droite/bas, poids 1 : dist(coin, coin) == 38 */
    enum { N = 20 };
    Graph *g = graph_new(N * N);
    for (size_t r = 0; r < N; r++) {
        for (size_t c = 0; c < N; c++) {
            size_t id = r * N + c;
            if (c + 1 < N) {
                graph_add_edge(g, id, id + 1, 1);
            }
            if (r + 1 < N) {
                graph_add_edge(g, id, id + N, 1);
            }
        }
    }
    long long *dist = malloc(N * N * sizeof *dist);
    size_t *prev = malloc(N * N * sizeof *prev);
    CHECK_NOT_NULL(dist);
    CHECK_NOT_NULL(prev);
    CHECK_INT_EQ(dijkstra(g, 0, dist, prev), 0);
    CHECK_INT_EQ(dist[N * N - 1], 2 * (N - 1));
    /* départage : le prédécesseur d'indice minimal est celui du dessus */
    CHECK_UINT_EQ(prev[N * N - 1], N * N - 1 - N);
    free(dist);
    free(prev);
    graph_free(g);
}

TEST(runs_in_log_time) {
    enum { N = 50000 };
    Graph *g = graph_new(N);
    CHECK_NOT_NULL(g);
    /* chemin de coût 1 par pas, raccourcis plus chers, et arêtes leurres */
    for (size_t i = 0; i + 1 < N; i++) {
        graph_add_edge(g, i, i + 1, 1);
    }
    for (size_t i = 0; i + 2 < N; i++) {
        graph_add_edge(g, i, i + 2, 3);
    }
    for (size_t i = 0; i < N; i++) {
        graph_add_edge(g, i, (i * 7919 + 13) % N, 1000000);
    }
    long long *dist = malloc(N * sizeof *dist);
    CHECK_NOT_NULL(dist);
    clock_t t0 = clock();
    int rc = dijkstra(g, 0, dist, NULL);
    double secs = (double)(clock() - t0) / CLOCKS_PER_SEC;
    long long last = dist[N - 1];
    free(dist);
    graph_free(g);
    CHECK_INT_EQ(rc, 0);
    CHECK_INT_EQ(last, N - 1);
    if (secs > 5.0) {
        TH_FAILF("%.1f s pour 50 000 sommets : la file de priorité manque", secs);
    }
}
