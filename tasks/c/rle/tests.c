#include "harness.h"

char *rle_encode(const char *input);
char *rle_decode(const char *input);

TEST(encode_empty) {
    char *got = rle_encode("");
    CHECK_NOT_NULL(got);
    CHECK_STR_EQ(got, "");
    free(got);
}

TEST(encode_single_characters) {
    char *got = rle_encode("XYZ");
    CHECK_STR_EQ(got, "XYZ");
    free(got);
}

TEST(encode_simple_runs) {
    char *got = rle_encode("AABBBCCCC");
    CHECK_STR_EQ(got, "2A3B4C");
    free(got);
}

TEST(encode_with_whitespace) {
    char *got = rle_encode("  hsqq qww  ");
    CHECK_STR_EQ(got, "2 hs2q q2w2 ");
    free(got);
}

TEST(encode_multi_digit_counts) {
    char *got = rle_encode("WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB");
    CHECK_STR_EQ(got, "12WB12W3B24WB");
    free(got);
}

TEST(encode_case_is_significant) {
    char *got = rle_encode("aAaA");
    CHECK_STR_EQ(got, "aAaA");
    free(got);
}

TEST(encode_single_long_run) {
    char buf[101];
    memset(buf, 'Z', 100);
    buf[100] = '\0';
    char *got = rle_encode(buf);
    CHECK_STR_EQ(got, "100Z");
    free(got);
}

TEST(encode_null_input) {
    CHECK_NULL(rle_encode(NULL));
}

TEST(decode_empty) {
    char *got = rle_decode("");
    CHECK_NOT_NULL(got);
    CHECK_STR_EQ(got, "");
    free(got);
}

TEST(decode_simple) {
    char *got = rle_decode("2A3B4C");
    CHECK_STR_EQ(got, "AABBBCCCC");
    free(got);
}

TEST(decode_multi_digit_counts) {
    char *got = rle_decode("12WB12W3B24WB");
    CHECK_STR_EQ(got, "WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB");
    free(got);
}

TEST(decode_no_counts) {
    char *got = rle_decode("XYZ");
    CHECK_STR_EQ(got, "XYZ");
    free(got);
}

TEST(decode_whitespace_runs) {
    char *got = rle_decode("2 hs2q q2w2 ");
    CHECK_STR_EQ(got, "  hsqq qww  ");
    free(got);
}

TEST(decode_rejects_dangling_count) {
    CHECK_NULL(rle_decode("3"));
    CHECK_NULL(rle_decode("AB12"));
}

TEST(decode_rejects_leading_zero) {
    CHECK_NULL(rle_decode("0A"));
    CHECK_NULL(rle_decode("03A"));
    CHECK_NULL(rle_decode("2A0B"));
}

TEST(decode_rejects_huge_count) {
    CHECK_NULL(rle_decode("1000001A"));
    CHECK_NULL(rle_decode("99999999999999999999A"));
}

TEST(decode_null_input) {
    CHECK_NULL(rle_decode(NULL));
}

TEST(round_trip) {
    const char *samples[] = {
        "",
        "a",
        "aaabbbccc",
        "  ",
        "The quick brown fox jumps over the lazy dog",
        "MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMz",
    };
    for (size_t i = 0; i < sizeof samples / sizeof samples[0]; i++) {
        char *enc = rle_encode(samples[i]);
        CHECK_NOT_NULL(enc);
        char *dec = rle_decode(enc);
        if (dec == NULL) {
            free(enc);
            TH_FAILF("rle_decode(rle_encode(\"%s\")) a renvoyé NULL", samples[i]);
        }
        int same = strcmp(dec, samples[i]) == 0;
        free(enc);
        free(dec);
        if (!same) {
            TH_FAILF("aller-retour cassé pour \"%s\"", samples[i]);
        }
    }
}

TEST(results_are_independent_allocations) {
    char *a = rle_encode("AAB");
    char *b = rle_encode("CCD");
    CHECK_NOT_NULL(a);
    CHECK_NOT_NULL(b);
    CHECK(a != b);
    CHECK_STR_EQ(a, "2AB");
    CHECK_STR_EQ(b, "2CD");
    free(a);
    free(b);
}
