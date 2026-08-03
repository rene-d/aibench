#include "harness.h"

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

#define U(s) ((const unsigned char *)(s))
#define LEN(a) (sizeof(a) - 1)

/* ------------------------------------------------------------------ */
/* Décodage d'un TLV primitif                                          */
/* ------------------------------------------------------------------ */

TEST(primitive_octet_string) {
    static const char d[] = "\x04\x03" "abc";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_NOT_NULL(t);
    CHECK_INT_EQ(t->tag_class, BER_UNIVERSAL);
    CHECK_INT_EQ(t->constructed, 0);
    CHECK_UINT_EQ(t->tag_number, 4);
    CHECK_UINT_EQ(t->value_len, 3);
    CHECK_MEM_EQ(t->value, "abc", 3);
    CHECK_UINT_EQ(t->child_count, 0);
    CHECK_NULL(t->children);
    ber_free(t);
}

TEST(value_points_into_the_input_buffer) {
    static const char d[] = "\x04\x03" "abc";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK(t->value == U(d) + 2);
    ber_free(t);
}

TEST(empty_content) {
    static const char d[] = "\x05\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->tag_number, 5);
    CHECK_UINT_EQ(t->value_len, 0);
    ber_free(t);
}

TEST(tag_classes) {
    static const char universal[] = "\x02\x01\x00";
    static const char application[] = "\x42\x01\x00";
    static const char context[] = "\x82\x01\x00";
    static const char private_[] = "\xc2\x01\x00";
    const char *cases[] = {universal, application, context, private_};
    BerClass want[] = {BER_UNIVERSAL, BER_APPLICATION, BER_CONTEXT, BER_PRIVATE};
    for (int i = 0; i < 4; i++) {
        BerTlv *t = NULL;
        CHECK_INT_EQ(ber_decode(U(cases[i]), 3, &t), BER_OK);
        int ok = t != NULL && t->tag_class == want[i] && t->tag_number == 2;
        ber_free(t);
        if (!ok) {
            TH_FAILF("classe mal décodée pour le cas %d", i);
        }
    }
}

TEST(constructed_bit) {
    static const char d[] = "\x30\x03\x02\x01\x07";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_INT_EQ(t->constructed, 1);
    CHECK_NULL(t->value);
    CHECK_UINT_EQ(t->value_len, 0);
    CHECK_UINT_EQ(t->child_count, 1);
    ber_free(t);
}

/* ------------------------------------------------------------------ */
/* Tags en forme longue                                                */
/* ------------------------------------------------------------------ */

TEST(long_form_tag_128) {
    static const char d[] = "\x9f\x81\x00\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_INT_EQ(t->tag_class, BER_CONTEXT);
    CHECK_INT_EQ(t->constructed, 0);
    CHECK_UINT_EQ(t->tag_number, 128);
    CHECK_UINT_EQ(t->value_len, 0);
    ber_free(t);
}

TEST(long_form_tag_31) {
    /* 31 est le plus petit numéro qui exige la forme longue */
    static const char d[] = "\x1f\x1f\x01\x41";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->tag_number, 31);
    CHECK_UINT_EQ(t->value_len, 1);
    CHECK_INT_EQ(t->value[0], 'A');
    ber_free(t);
}

TEST(long_form_tag_three_bytes) {
    /* 0x81 0x80 0x00 = 1<<14 = 16384 */
    static const char d[] = "\xbf\x81\x80\x00\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->tag_number, 16384);
    CHECK_INT_EQ(t->tag_class, BER_CONTEXT);
    CHECK_INT_EQ(t->constructed, 1);
    CHECK_UINT_EQ(t->child_count, 0);
    ber_free(t);
}

TEST(long_form_tag_truncated) {
    static const char d[] = "\x9f\x81";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_TRUNCATED);
    CHECK_NULL(t);
}

TEST(long_form_tag_overflow) {
    static const char d[] = "\x9f\xff\xff\xff\xff\xff\xff\xff\xff\xff\x7f\x00";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OVERFLOW);
    CHECK_NULL(t);
}

/* ------------------------------------------------------------------ */
/* Longueurs                                                           */
/* ------------------------------------------------------------------ */

TEST(long_form_length_one_byte) {
    unsigned char d[203];
    d[0] = 0x04;
    d[1] = 0x81;
    d[2] = 0xc8;                 /* 200 */
    memset(d + 3, 'z', 200);
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(d, sizeof d, &t), BER_OK);
    CHECK_UINT_EQ(t->value_len, 200);
    CHECK_INT_EQ(t->value[199], 'z');
    ber_free(t);
}

TEST(long_form_length_two_bytes) {
    unsigned char d[260];
    d[0] = 0x04;
    d[1] = 0x82;
    d[2] = 0x01;
    d[3] = 0x00;                 /* 256 */
    memset(d + 4, 'q', 256);
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(d, sizeof d, &t), BER_OK);
    CHECK_UINT_EQ(t->value_len, 256);
    ber_free(t);
}

TEST(long_form_length_missing_bytes) {
    static const char d[] = "\x04\x82\x01";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_TRUNCATED);
    CHECK_NULL(t);
}

TEST(long_form_length_too_many_bytes) {
    static const char d[] = "\x04\x89\x01\x02\x03\x04\x05\x06\x07\x08\x09";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OVERFLOW);
    CHECK_NULL(t);
}

TEST(reserved_length_byte) {
    static const char d[] = "\x04\xff\x01";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_RESERVED_LENGTH);
    CHECK_NULL(t);
}

TEST(truncated_content) {
    static const char d[] = "\x04\x05" "ab";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_TRUNCATED);
    CHECK_NULL(t);
}

TEST(empty_input) {
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(""), 0, &t), BER_EMPTY);
    CHECK_NULL(t);
    t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(NULL, 0, &t), BER_EMPTY);
    CHECK_NULL(t);
}

TEST(trailing_bytes) {
    static const char d[] = "\x04\x01\x41\x00";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_TRAILING);
    CHECK_NULL(t);
    static const char two[] = "\x02\x01\x01\x02\x01\x02";
    t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(two), LEN(two), &t), BER_TRAILING);
    CHECK_NULL(t);
}

/* ------------------------------------------------------------------ */
/* Longueur indéfinie                                                  */
/* ------------------------------------------------------------------ */

TEST(indefinite_length_sequence) {
    static const char d[] = "\x30\x80\x02\x01\x2a\x04\x02\x68\x69\x00\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_INT_EQ(t->constructed, 1);
    CHECK_UINT_EQ(t->child_count, 2);
    CHECK_UINT_EQ(t->children[0]->tag_number, 2);
    CHECK_UINT_EQ(t->children[0]->value_len, 1);
    CHECK_INT_EQ(t->children[0]->value[0], 0x2a);
    CHECK_UINT_EQ(t->children[1]->tag_number, 4);
    CHECK_MEM_EQ(t->children[1]->value, "hi", 2);
    ber_free(t);
}

TEST(empty_indefinite_length_sequence) {
    static const char d[] = "\x30\x80\x00\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->child_count, 0);
    ber_free(t);
}

TEST(nested_indefinite_lengths) {
    static const char d[] = "\x30\x80\x30\x80\x02\x01\x07\x00\x00\x00\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->child_count, 1);
    CHECK_UINT_EQ(t->children[0]->child_count, 1);
    CHECK_UINT_EQ(t->children[0]->children[0]->tag_number, 2);
    CHECK_INT_EQ(t->children[0]->children[0]->value[0], 7);
    ber_free(t);
}

TEST(indefinite_length_on_primitive_is_rejected) {
    static const char d[] = "\x04\x80\x41\x00\x00";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_INDEFINITE_PRIMITIVE);
    CHECK_NULL(t);
}

TEST(unterminated_indefinite_length) {
    static const char d[] = "\x30\x80\x02\x01\x2a";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_UNTERMINATED);
    CHECK_NULL(t);
    static const char bare[] = "\x30\x80";
    t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(bare), LEN(bare), &t), BER_UNTERMINATED);
    CHECK_NULL(t);
}

TEST(indefinite_inside_definite) {
    static const char d[] = "\x30\x06\x30\x80\x05\x00\x00\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->child_count, 1);
    CHECK_UINT_EQ(t->children[0]->child_count, 1);
    CHECK_UINT_EQ(t->children[0]->children[0]->tag_number, 5);
    ber_free(t);
}

/* ------------------------------------------------------------------ */
/* Imbrication                                                         */
/* ------------------------------------------------------------------ */

TEST(nested_sequences) {
    static const char d[] = "\x30\x0a\x02\x01\x01\x30\x05\x02\x01\x02\x05\x00";
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_OK);
    CHECK_UINT_EQ(t->child_count, 2);
    CHECK_UINT_EQ(t->children[0]->tag_number, 2);
    CHECK_INT_EQ(t->children[0]->value[0], 1);
    CHECK_INT_EQ(t->children[1]->constructed, 1);
    CHECK_UINT_EQ(t->children[1]->child_count, 2);
    CHECK_INT_EQ(t->children[1]->children[0]->value[0], 2);
    CHECK_UINT_EQ(t->children[1]->children[1]->tag_number, 5);
    CHECK_UINT_EQ(t->children[1]->children[1]->value_len, 0);
    ber_free(t);
}

TEST(child_overruns_its_parent) {
    /* la SEQUENCE annonce 3 octets, l'enfant en réclame 5 */
    static const char d[] = "\x30\x03\x04\x05\x41";
    BerTlv *t = (BerTlv *)0x1;
    CHECK_INT_EQ(ber_decode(U(d), LEN(d), &t), BER_TRUNCATED);
    CHECK_NULL(t);
}

TEST(deeply_nested_sequences) {
    /* 40 SEQUENCE imbriquées, chacune contenant la suivante */
    enum { DEPTH = 40 };
    unsigned char d[2 * DEPTH];
    for (int i = 0; i < DEPTH; i++) {
        d[2 * i] = 0x30;
        d[2 * i + 1] = (unsigned char)(2 * (DEPTH - i - 1));
    }
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(d, sizeof d, &t), BER_OK);
    BerTlv *cur = t;
    for (int i = 0; i < DEPTH - 1; i++) {
        if (cur->child_count != 1) {
            ber_free(t);
            TH_FAILF("profondeur %d : un seul enfant attendu, %zu trouvés",
                     i, cur->child_count);
        }
        cur = cur->children[0];
    }
    CHECK_UINT_EQ(cur->child_count, 0);
    ber_free(t);
}

TEST(free_null_is_a_noop) {
    ber_free(NULL);
    CHECK(1);
}

/* ------------------------------------------------------------------ */
/* ber_decode_integer                                                  */
/* ------------------------------------------------------------------ */

TEST(integer_positive) {
    long long v = -1;
    CHECK_INT_EQ(ber_decode_integer(U("\x7f"), 1, &v), BER_OK);
    CHECK_INT_EQ(v, 127);
    CHECK_INT_EQ(ber_decode_integer(U("\x00\x80"), 2, &v), BER_OK);
    CHECK_INT_EQ(v, 128);
    CHECK_INT_EQ(ber_decode_integer(U("\x00"), 1, &v), BER_OK);
    CHECK_INT_EQ(v, 0);
    CHECK_INT_EQ(ber_decode_integer(U("\x12\x34\x56\x78"), 4, &v), BER_OK);
    CHECK_INT_EQ(v, 305419896);
}

TEST(integer_negative) {
    long long v = 0;
    CHECK_INT_EQ(ber_decode_integer(U("\x80"), 1, &v), BER_OK);
    CHECK_INT_EQ(v, -128);
    CHECK_INT_EQ(ber_decode_integer(U("\xff\x7f"), 2, &v), BER_OK);
    CHECK_INT_EQ(v, -129);
    CHECK_INT_EQ(ber_decode_integer(U("\xff"), 1, &v), BER_OK);
    CHECK_INT_EQ(v, -1);
    CHECK_INT_EQ(ber_decode_integer(U("\xff\xff\xff\xff"), 4, &v), BER_OK);
    CHECK_INT_EQ(v, -1);
}

TEST(integer_eight_bytes) {
    long long v = 0;
    CHECK_INT_EQ(ber_decode_integer(U("\x7f\xff\xff\xff\xff\xff\xff\xff"), 8, &v), BER_OK);
    CHECK_INT_EQ(v, 9223372036854775807LL);
    CHECK_INT_EQ(ber_decode_integer(U("\x80\x00\x00\x00\x00\x00\x00\x00"), 8, &v), BER_OK);
    CHECK_INT_EQ(v, -9223372036854775807LL - 1);
}

TEST(integer_errors) {
    long long v = 4242;
    CHECK_INT_EQ(ber_decode_integer(U(""), 0, &v), BER_INVALID);
    CHECK_INT_EQ(v, 4242);
    CHECK_INT_EQ(ber_decode_integer(U("\x01\x02\x03\x04\x05\x06\x07\x08\x09"), 9, &v),
                 BER_OVERFLOW);
}

/* ------------------------------------------------------------------ */
/* ber_decode_oid                                                      */
/* ------------------------------------------------------------------ */

TEST(oid_rsa) {
    char *s = NULL;
    CHECK_INT_EQ(ber_decode_oid(U("\x2a\x86\x48\x86\xf7\x0d"), 6, &s), BER_OK);
    CHECK_STR_EQ(s, "1.2.840.113549");
    free(s);
}

TEST(oid_common_name) {
    char *s = NULL;
    CHECK_INT_EQ(ber_decode_oid(U("\x55\x04\x03"), 3, &s), BER_OK);
    CHECK_STR_EQ(s, "2.5.4.3");
    free(s);
}

TEST(oid_second_arc_above_39) {
    char *s = NULL;
    CHECK_INT_EQ(ber_decode_oid(U("\x81\x34"), 2, &s), BER_OK);
    CHECK_STR_EQ(s, "2.100");
    free(s);
}

TEST(oid_first_byte_boundaries) {
    char *s = NULL;
    CHECK_INT_EQ(ber_decode_oid(U("\x00"), 1, &s), BER_OK);
    CHECK_STR_EQ(s, "0.0");
    free(s);
    CHECK_INT_EQ(ber_decode_oid(U("\x27"), 1, &s), BER_OK);   /* 39 */
    CHECK_STR_EQ(s, "0.39");
    free(s);
    CHECK_INT_EQ(ber_decode_oid(U("\x28"), 1, &s), BER_OK);   /* 40 */
    CHECK_STR_EQ(s, "1.0");
    free(s);
    CHECK_INT_EQ(ber_decode_oid(U("\x4f"), 1, &s), BER_OK);   /* 79 */
    CHECK_STR_EQ(s, "1.39");
    free(s);
    CHECK_INT_EQ(ber_decode_oid(U("\x50"), 1, &s), BER_OK);   /* 80 */
    CHECK_STR_EQ(s, "2.0");
    free(s);
}

TEST(oid_snmp) {
    char *s = NULL;
    CHECK_INT_EQ(ber_decode_oid(U("\x2b\x06\x01\x02\x01"), 5, &s), BER_OK);
    CHECK_STR_EQ(s, "1.3.6.1.2.1");
    free(s);
}

TEST(oid_errors) {
    char *s = (char *)0x1;
    CHECK_INT_EQ(ber_decode_oid(U(""), 0, &s), BER_INVALID);
    CHECK_NULL(s);
    s = (char *)0x1;
    CHECK_INT_EQ(ber_decode_oid(U("\x2a\x86"), 2, &s), BER_INVALID);
    CHECK_NULL(s);
    s = (char *)0x1;
    CHECK_INT_EQ(ber_decode_oid(U("\x2a\xff\xff\xff\xff\xff\xff\xff\xff\xff\x7f"), 11, &s),
                 BER_OVERFLOW);
    CHECK_NULL(s);
}

/* ------------------------------------------------------------------ */
/* PDU SNMP complète                                                   */
/* ------------------------------------------------------------------ */

TEST(snmp_get_request_pdu) {
    static const unsigned char pdu[] = {
        0x30, 0x26,
            0x02, 0x01, 0x00,
            0x04, 0x06, 'p', 'u', 'b', 'l', 'i', 'c',
            0xA0, 0x19,
                0x02, 0x04, 0x12, 0x34, 0x56, 0x78,
                0x02, 0x01, 0x00,
                0x02, 0x01, 0x00,
                0x30, 0x0B,
                    0x30, 0x09,
                        0x06, 0x05, 0x2B, 0x06, 0x01, 0x02, 0x01,
                        0x05, 0x00,
    };
    BerTlv *t = NULL;
    CHECK_INT_EQ(ber_decode(pdu, sizeof pdu, &t), BER_OK);
    CHECK_NOT_NULL(t);
    CHECK_INT_EQ(t->constructed, 1);
    CHECK_UINT_EQ(t->tag_number, 16);
    CHECK_UINT_EQ(t->child_count, 3);

    long long version = -1;
    CHECK_INT_EQ(ber_decode_integer(t->children[0]->value,
                                    t->children[0]->value_len, &version), BER_OK);
    CHECK_INT_EQ(version, 0);

    CHECK_UINT_EQ(t->children[1]->value_len, 6);
    CHECK_MEM_EQ(t->children[1]->value, "public", 6);

    BerTlv *req = t->children[2];
    CHECK_INT_EQ(req->tag_class, BER_CONTEXT);
    CHECK_INT_EQ(req->constructed, 1);
    CHECK_UINT_EQ(req->tag_number, 0);
    CHECK_UINT_EQ(req->child_count, 4);

    long long id = 0;
    CHECK_INT_EQ(ber_decode_integer(req->children[0]->value,
                                    req->children[0]->value_len, &id), BER_OK);
    CHECK_INT_EQ(id, 305419896);

    BerTlv *varbind = req->children[3]->children[0];
    CHECK_UINT_EQ(varbind->child_count, 2);
    char *oid = NULL;
    CHECK_INT_EQ(ber_decode_oid(varbind->children[0]->value,
                                varbind->children[0]->value_len, &oid), BER_OK);
    CHECK_STR_EQ(oid, "1.3.6.1.2.1");
    free(oid);
    CHECK_UINT_EQ(varbind->children[1]->tag_number, 5);
    CHECK_UINT_EQ(varbind->children[1]->value_len, 0);
    ber_free(t);
}
