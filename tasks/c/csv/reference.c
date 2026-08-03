#include <stdlib.h>
#include <string.h>

typedef enum {
    CSV_OK = 0,
    CSV_UNTERMINATED_QUOTE,
    CSV_BARE_QUOTE,
    CSV_NOMEM
} CsvError;

typedef struct {
    char ***rows;
    size_t  *ncols;
    size_t   nrows;
} CsvTable;

CsvError csv_parse(const char *input, CsvTable **out);
void     csv_free(CsvTable *t);

/* Tampon de caractères à croissance géométrique. */
typedef struct {
    char  *data;
    size_t len;
    size_t cap;
} Buf;

static int buf_push(Buf *b, char c) {
    if (b->len + 1 >= b->cap) {
        size_t cap = b->cap ? b->cap * 2 : 32;
        char *bigger = realloc(b->data, cap);
        if (bigger == NULL) {
            return -1;
        }
        b->data = bigger;
        b->cap = cap;
    }
    b->data[b->len++] = c;
    return 0;
}

static char *buf_take(Buf *b) {
    if (buf_push(b, '\0') != 0) {
        return NULL;
    }
    char *s = b->data;
    b->data = NULL;
    b->len = b->cap = 0;
    return s;
}

/* Ligne en construction : tableau de champs possédés. */
typedef struct {
    char **fields;
    size_t n;
    size_t cap;
} Row;

static int row_push(Row *r, char *field) {
    if (r->n == r->cap) {
        size_t cap = r->cap ? r->cap * 2 : 8;
        char **bigger = realloc(r->fields, cap * sizeof *bigger);
        if (bigger == NULL) {
            return -1;
        }
        r->fields = bigger;
        r->cap = cap;
    }
    r->fields[r->n++] = field;
    return 0;
}

static void row_destroy(Row *r) {
    for (size_t i = 0; i < r->n; i++) {
        free(r->fields[i]);
    }
    free(r->fields);
    r->fields = NULL;
    r->n = r->cap = 0;
}

static int table_push(CsvTable *t, size_t *cap, Row *r) {
    if (t->nrows == *cap) {
        size_t next = *cap ? *cap * 2 : 8;
        char ***rows = realloc(t->rows, next * sizeof *rows);
        if (rows == NULL) {
            return -1;
        }
        t->rows = rows;
        size_t *ncols = realloc(t->ncols, next * sizeof *ncols);
        if (ncols == NULL) {
            return -1;
        }
        t->ncols = ncols;
        *cap = next;
    }
    t->rows[t->nrows] = r->fields;
    t->ncols[t->nrows] = r->n;
    t->nrows++;
    r->fields = NULL; /* propriété transférée à la table */
    r->n = r->cap = 0;
    return 0;
}

static int is_record_end(const char *p) {
    return *p == '\0' || *p == '\n' || (*p == '\r' && p[1] == '\n');
}

CsvError csv_parse(const char *input, CsvTable **out) {
    *out = NULL;
    CsvTable *t = calloc(1, sizeof *t);
    if (t == NULL) {
        return CSV_NOMEM;
    }
    if (input == NULL || *input == '\0') {
        *out = t;
        return CSV_OK;
    }

    Buf buf = {NULL, 0, 0};
    Row row = {NULL, 0, 0};
    size_t rows_cap = 0;
    CsvError err = CSV_OK;
    const char *p = input;

    for (;;) {
        /* --- un enregistrement --- */
        for (;;) {
            /* --- un champ --- */
            if (*p == '"') {
                p++;
                for (;;) {
                    if (*p == '\0') {
                        err = CSV_UNTERMINATED_QUOTE;
                        goto done;
                    }
                    if (*p == '"') {
                        if (p[1] == '"') {
                            if (buf_push(&buf, '"') != 0) {
                                err = CSV_NOMEM;
                                goto done;
                            }
                            p += 2;
                            continue;
                        }
                        p++;
                        break; /* guillemet fermant */
                    }
                    if (buf_push(&buf, *p++) != 0) {
                        err = CSV_NOMEM;
                        goto done;
                    }
                }
                if (*p != ',' && !is_record_end(p)) {
                    err = CSV_BARE_QUOTE;
                    goto done;
                }
            } else {
                while (*p != ',' && !is_record_end(p)) {
                    if (*p == '"') {
                        err = CSV_BARE_QUOTE;
                        goto done;
                    }
                    if (buf_push(&buf, *p++) != 0) {
                        err = CSV_NOMEM;
                        goto done;
                    }
                }
            }

            char *field = buf_take(&buf);
            if (field == NULL || row_push(&row, field) != 0) {
                free(field);
                err = CSV_NOMEM;
                goto done;
            }
            if (*p != ',') {
                break;
            }
            p++;
        }

        if (table_push(t, &rows_cap, &row) != 0) {
            err = CSV_NOMEM;
            goto done;
        }

        if (*p == '\r') {
            p += 2;
        } else if (*p == '\n') {
            p += 1;
        } else {
            break; /* fin de l'entrée */
        }
        if (*p == '\0') {
            break; /* saut de ligne final : pas d'enregistrement vide en plus */
        }
    }

done:
    free(buf.data);
    row_destroy(&row);
    if (err != CSV_OK) {
        csv_free(t);
        return err;
    }
    *out = t;
    return CSV_OK;
}

void csv_free(CsvTable *t) {
    if (t == NULL) {
        return;
    }
    for (size_t i = 0; i < t->nrows; i++) {
        for (size_t j = 0; j < t->ncols[i]; j++) {
            free(t->rows[i][j]);
        }
        free(t->rows[i]);
    }
    free(t->rows);
    free(t->ncols);
    free(t);
}
