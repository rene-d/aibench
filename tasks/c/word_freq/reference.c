#include <stdlib.h>
#include <string.h>

typedef struct {
    char  *word;
    size_t count;
} WordCount;

size_t word_freq(const char *text, size_t k, WordCount **out);
void   word_freq_free(WordCount *counts, size_t n);

static int is_word_byte(unsigned char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

static unsigned long hash_bytes(const char *s, size_t n) {
    unsigned long h = 5381;
    for (size_t i = 0; i < n; i++) {
        h = h * 33u + (unsigned char)s[i];
    }
    return h;
}

/* Table de hachage à adressage ouvert, sondage linéaire. */
typedef struct {
    WordCount *slots;
    size_t     cap;   /* puissance de deux */
    size_t     used;
} Table;

static int table_init(Table *t, size_t cap) {
    t->slots = calloc(cap, sizeof *t->slots);
    if (t->slots == NULL) {
        return -1;
    }
    t->cap = cap;
    t->used = 0;
    return 0;
}

static void table_destroy(Table *t) {
    for (size_t i = 0; i < t->cap; i++) {
        free(t->slots[i].word);
    }
    free(t->slots);
}

static int table_grow(Table *t);

/* `word` n'est pas terminé par '\0' : c'est une tranche du texte, déjà minuscule. */
static int table_bump(Table *t, const char *word, size_t len) {
    if ((t->used + 1) * 4 >= t->cap * 3 && table_grow(t) != 0) {
        return -1;
    }
    size_t mask = t->cap - 1;
    size_t i = (size_t)hash_bytes(word, len) & mask;
    while (t->slots[i].word != NULL) {
        if (strlen(t->slots[i].word) == len && memcmp(t->slots[i].word, word, len) == 0) {
            t->slots[i].count++;
            return 0;
        }
        i = (i + 1) & mask;
    }
    char *copy = malloc(len + 1);
    if (copy == NULL) {
        return -1;
    }
    memcpy(copy, word, len);
    copy[len] = '\0';
    t->slots[i].word = copy;
    t->slots[i].count = 1;
    t->used++;
    return 0;
}

static int table_grow(Table *t) {
    Table bigger;
    if (table_init(&bigger, t->cap * 2) != 0) {
        return -1;
    }
    size_t mask = bigger.cap - 1;
    for (size_t i = 0; i < t->cap; i++) {
        if (t->slots[i].word == NULL) {
            continue;
        }
        size_t len = strlen(t->slots[i].word);
        size_t j = (size_t)hash_bytes(t->slots[i].word, len) & mask;
        while (bigger.slots[j].word != NULL) {
            j = (j + 1) & mask;
        }
        bigger.slots[j] = t->slots[i]; /* on transfère la propriété du mot */
    }
    bigger.used = t->used;
    free(t->slots);
    *t = bigger;
    return 0;
}

static int by_count_then_word(const void *pa, const void *pb) {
    const WordCount *a = pa, *b = pb;
    if (a->count != b->count) {
        return a->count < b->count ? 1 : -1;
    }
    return strcmp(a->word, b->word);
}

size_t word_freq(const char *text, size_t k, WordCount **out) {
    *out = NULL;
    if (text == NULL || k == 0) {
        return 0;
    }

    /* Minusculisation dans une copie de travail, pour pouvoir comparer des
       tranches sans réallouer à chaque mot. */
    size_t len = strlen(text);
    char *lower = malloc(len + 1);
    if (lower == NULL) {
        return 0;
    }
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)text[i];
        lower[i] = (c >= 'A' && c <= 'Z') ? (char)(c - 'A' + 'a') : (char)c;
    }
    lower[len] = '\0';

    Table t;
    if (table_init(&t, 64) != 0) {
        free(lower);
        return 0;
    }
    for (size_t i = 0; i < len;) {
        if (!is_word_byte((unsigned char)lower[i])) {
            i++;
            continue;
        }
        size_t start = i;
        while (i < len && is_word_byte((unsigned char)lower[i])) {
            i++;
        }
        if (table_bump(&t, lower + start, i - start) != 0) {
            table_destroy(&t);
            free(lower);
            return 0;
        }
    }
    free(lower);

    if (t.used == 0) {
        table_destroy(&t);
        return 0;
    }

    WordCount *all = malloc(t.used * sizeof *all);
    if (all == NULL) {
        table_destroy(&t);
        return 0;
    }
    size_t n = 0;
    for (size_t i = 0; i < t.cap; i++) {
        if (t.slots[i].word != NULL) {
            all[n++] = t.slots[i]; /* propriété transférée au tableau */
        }
    }
    free(t.slots); /* les mots appartiennent maintenant à `all` */

    qsort(all, n, sizeof *all, by_count_then_word);

    if (k >= n) {
        *out = all;
        return n;
    }
    for (size_t i = k; i < n; i++) {
        free(all[i].word);
    }
    WordCount *trimmed = realloc(all, k * sizeof *all);
    *out = trimmed != NULL ? trimmed : all;
    return k;
}

void word_freq_free(WordCount *counts, size_t n) {
    if (counts == NULL) {
        return;
    }
    for (size_t i = 0; i < n; i++) {
        free(counts[i].word);
    }
    free(counts);
}
