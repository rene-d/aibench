#include <stdlib.h>
#include <string.h>

char *rle_encode(const char *input);
char *rle_decode(const char *input);

#define RLE_MAX_COUNT 1000000

static size_t count_digits(size_t n) {
    size_t d = 1;
    while (n >= 10) {
        n /= 10;
        d++;
    }
    return d;
}

char *rle_encode(const char *input) {
    if (input == NULL) {
        return NULL;
    }
    size_t n = strlen(input);
    /* Une suite de longueur 1 coûte 1 octet, une suite de longueur L >= 2 en
       coûte au plus L : la sortie ne dépasse jamais l'entrée. */
    char *out = malloc(n + 2);
    if (out == NULL) {
        return NULL;
    }
    size_t w = 0;
    for (size_t i = 0; i < n;) {
        size_t run = 1;
        while (i + run < n && input[i + run] == input[i]) {
            run++;
        }
        if (run > 1) {
            size_t d = count_digits(run), rest = run;
            for (size_t k = 0; k < d; k++) {
                out[w + d - 1 - k] = (char)('0' + rest % 10);
                rest /= 10;
            }
            w += d;
        }
        out[w++] = input[i];
        i += run;
    }
    out[w] = '\0';
    return out;
}

char *rle_decode(const char *input) {
    if (input == NULL) {
        return NULL;
    }
    /* Première passe : validation et calcul de la taille exacte. */
    size_t total = 0;
    for (const char *p = input; *p != '\0';) {
        size_t count = 1;
        if (*p >= '0' && *p <= '9') {
            if (*p == '0') {
                return NULL;
            }
            count = 0;
            while (*p >= '0' && *p <= '9') {
                count = count * 10 + (size_t)(*p - '0');
                if (count > RLE_MAX_COUNT) {
                    return NULL;
                }
                p++;
            }
            if (*p == '\0') {
                return NULL; /* compteur sans caractère derrière */
            }
        }
        p++; /* le caractère répété */
        total += count;
    }

    char *out = malloc(total + 1);
    if (out == NULL) {
        return NULL;
    }
    size_t w = 0;
    for (const char *p = input; *p != '\0';) {
        size_t count = 1;
        if (*p >= '0' && *p <= '9') {
            count = 0;
            while (*p >= '0' && *p <= '9') {
                count = count * 10 + (size_t)(*p - '0');
                p++;
            }
        }
        char c = *p++;
        memset(out + w, c, count);
        w += count;
    }
    out[w] = '\0';
    return out;
}
