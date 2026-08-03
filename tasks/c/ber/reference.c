#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef enum {
    BER_OK = 0,
    BER_EMPTY,
    BER_TRUNCATED,
    BER_TRAILING,
    BER_INDEFINITE_PRIMITIVE,
    BER_RESERVED_LENGTH,
    BER_UNTERMINATED,
    BER_OVERFLOW,
    BER_INVALID,
    BER_NOMEM
} BerError;

typedef enum {
    BER_UNIVERSAL   = 0,
    BER_APPLICATION = 1,
    BER_CONTEXT     = 2,
    BER_PRIVATE     = 3
} BerClass;

typedef struct BerTlv {
    BerClass             tag_class;
    int                  constructed;
    unsigned long        tag_number;
    const unsigned char *value;
    size_t               value_len;
    struct BerTlv      **children;
    size_t               child_count;
} BerTlv;

BerError ber_decode(const unsigned char *data, size_t len, BerTlv **out);
void     ber_free(BerTlv *tlv);
BerError ber_decode_integer(const unsigned char *value, size_t len, long long *out);
BerError ber_decode_oid(const unsigned char *value, size_t len, char **out);

void ber_free(BerTlv *tlv) {
    if (tlv == NULL) {
        return;
    }
    for (size_t i = 0; i < tlv->child_count; i++) {
        ber_free(tlv->children[i]);
    }
    free(tlv->children);
    free(tlv);
}

static BerError add_child(BerTlv *parent, size_t *cap, BerTlv *child) {
    if (parent->child_count == *cap) {
        size_t next = *cap ? *cap * 2 : 4;
        BerTlv **kids = realloc(parent->children, next * sizeof *kids);
        if (kids == NULL) {
            return BER_NOMEM;
        }
        parent->children = kids;
        *cap = next;
    }
    parent->children[parent->child_count++] = child;
    return BER_OK;
}

/* Décode un TLV depuis *p (exclu de `end`) et avance *p derrière lui. */
static BerError parse_tlv(const unsigned char **p, const unsigned char *end,
                          BerTlv **out) {
    *out = NULL;
    if (*p >= end) {
        return BER_TRUNCATED;
    }

    unsigned char ident = *(*p)++;
    BerClass tag_class = (BerClass)(ident >> 6);
    int constructed = (ident & 0x20) != 0;
    unsigned long tag_number = ident & 0x1f;

    if (tag_number == 0x1f) { /* forme longue */
        tag_number = 0;
        unsigned char b;
        do {
            if (*p >= end) {
                return BER_TRUNCATED;
            }
            b = *(*p)++;
            if (tag_number > (ULONG_MAX >> 7)) {
                return BER_OVERFLOW;
            }
            tag_number = (tag_number << 7) | (unsigned long)(b & 0x7f);
        } while (b & 0x80);
    }

    if (*p >= end) {
        return BER_TRUNCATED;
    }
    unsigned char l0 = *(*p)++;
    int indefinite = 0;
    size_t length = 0;

    if (l0 == 0xFF) {
        return BER_RESERVED_LENGTH;
    } else if (l0 == 0x80) {
        if (!constructed) {
            return BER_INDEFINITE_PRIMITIVE;
        }
        indefinite = 1;
    } else if (l0 & 0x80) {
        size_t nbytes = l0 & 0x7f;
        if (nbytes > 8) {
            return BER_OVERFLOW;
        }
        if ((size_t)(end - *p) < nbytes) {
            return BER_TRUNCATED;
        }
        unsigned long long acc = 0;
        for (size_t i = 0; i < nbytes; i++) {
            acc = (acc << 8) | *(*p)++;
        }
        if (acc > (unsigned long long)(end - *p)) {
            return BER_TRUNCATED;
        }
        length = (size_t)acc;
    } else {
        length = l0;
    }

    if (!indefinite && length > (size_t)(end - *p)) {
        return BER_TRUNCATED;
    }

    BerTlv *node = calloc(1, sizeof *node);
    if (node == NULL) {
        return BER_NOMEM;
    }
    node->tag_class = tag_class;
    node->constructed = constructed;
    node->tag_number = tag_number;

    size_t cap = 0;
    BerError err = BER_OK;

    if (indefinite) {
        for (;;) {
            if ((size_t)(end - *p) < 2) {
                err = BER_UNTERMINATED;
                goto fail;
            }
            if ((*p)[0] == 0x00 && (*p)[1] == 0x00) {
                *p += 2;
                break;
            }
            BerTlv *child = NULL;
            err = parse_tlv(p, end, &child);
            if (err != BER_OK) {
                goto fail;
            }
            err = add_child(node, &cap, child);
            if (err != BER_OK) {
                ber_free(child);
                goto fail;
            }
        }
    } else if (constructed) {
        const unsigned char *stop = *p + length;
        while (*p < stop) {
            BerTlv *child = NULL;
            err = parse_tlv(p, stop, &child);
            if (err != BER_OK) {
                goto fail;
            }
            err = add_child(node, &cap, child);
            if (err != BER_OK) {
                ber_free(child);
                goto fail;
            }
        }
    } else {
        node->value = *p;
        node->value_len = length;
        *p += length;
    }

    *out = node;
    return BER_OK;

fail:
    ber_free(node);
    return err;
}

BerError ber_decode(const unsigned char *data, size_t len, BerTlv **out) {
    *out = NULL;
    if (data == NULL || len == 0) {
        return BER_EMPTY;
    }
    const unsigned char *p = data;
    BerTlv *root = NULL;
    BerError err = parse_tlv(&p, data + len, &root);
    if (err != BER_OK) {
        return err;
    }
    if (p != data + len) {
        ber_free(root);
        return BER_TRAILING;
    }
    *out = root;
    return BER_OK;
}

BerError ber_decode_integer(const unsigned char *value, size_t len, long long *out) {
    if (len == 0) {
        return BER_INVALID;
    }
    if (len > 8) {
        return BER_OVERFLOW;
    }
    /* accumulation non signée : décaler un négatif serait un UB */
    unsigned long long acc = (value[0] & 0x80) ? ~0ULL : 0ULL;
    for (size_t i = 0; i < len; i++) {
        acc = (acc << 8) | value[i];
    }
    *out = (long long)acc;
    return BER_OK;
}

BerError ber_decode_oid(const unsigned char *value, size_t len, char **out) {
    *out = NULL;
    if (len == 0) {
        return BER_INVALID;
    }
    if (value[len - 1] & 0x80) {
        return BER_INVALID; /* dernier octet encore en continuation */
    }

    /* au pire 20 chiffres et un point par arc, et au plus len arcs */
    size_t cap = len * 21 + 32;
    char *buf = malloc(cap);
    if (buf == NULL) {
        return BER_NOMEM;
    }
    size_t w = 0;
    int first = 1;

    size_t i = 0;
    while (i < len) {
        unsigned long sub = 0;
        for (;;) {
            if (sub > (ULONG_MAX >> 7)) {
                free(buf);
                return BER_OVERFLOW;
            }
            unsigned char b = value[i++];
            sub = (sub << 7) | (unsigned long)(b & 0x7f);
            if ((b & 0x80) == 0) {
                break;
            }
        }
        if (first) {
            unsigned long x = sub < 80 ? sub / 40 : 2;
            unsigned long y = sub < 80 ? sub % 40 : sub - 80;
            w += (size_t)snprintf(buf + w, cap - w, "%lu.%lu", x, y);
            first = 0;
        } else {
            w += (size_t)snprintf(buf + w, cap - w, ".%lu", sub);
        }
    }
    *out = buf;
    return BER_OK;
}
