#include "harness.h"

typedef struct {
    char  *word;
    size_t count;
} WordCount;

size_t word_freq(const char *text, size_t k, WordCount **out);
void   word_freq_free(WordCount *counts, size_t n);

TEST(struct_layout_is_word_then_count) {
    CHECK_UINT_EQ(sizeof(WordCount), sizeof(char *) + sizeof(size_t));
}

TEST(simple_top_k) {
    WordCount *w = NULL;
    size_t n = word_freq("the quick brown fox jumps over the lazy dog the fox", 3, &w);
    CHECK_UINT_EQ(n, 3);
    CHECK_NOT_NULL(w);
    CHECK_STR_EQ(w[0].word, "the");
    CHECK_UINT_EQ(w[0].count, 3);
    CHECK_STR_EQ(w[1].word, "fox");
    CHECK_UINT_EQ(w[1].count, 2);
    CHECK_STR_EQ(w[2].word, "brown");
    CHECK_UINT_EQ(w[2].count, 1);
    word_freq_free(w, n);
}

TEST(case_is_folded) {
    WordCount *w = NULL;
    size_t n = word_freq("Hello, hello! HELLO?", 5, &w);
    CHECK_UINT_EQ(n, 1);
    CHECK_STR_EQ(w[0].word, "hello");
    CHECK_UINT_EQ(w[0].count, 3);
    word_freq_free(w, n);
}

TEST(ties_are_broken_lexicographically) {
    WordCount *w = NULL;
    size_t n = word_freq("pear apple pear banana apple cherry", 4, &w);
    CHECK_UINT_EQ(n, 4);
    CHECK_STR_EQ(w[0].word, "apple");
    CHECK_UINT_EQ(w[0].count, 2);
    CHECK_STR_EQ(w[1].word, "pear");
    CHECK_UINT_EQ(w[1].count, 2);
    CHECK_STR_EQ(w[2].word, "banana");
    CHECK_STR_EQ(w[3].word, "cherry");
    word_freq_free(w, n);
}

TEST(digits_are_part_of_words) {
    WordCount *w = NULL;
    size_t n = word_freq("x1 x1 x2 42 42 42", 3, &w);
    CHECK_UINT_EQ(n, 3);
    CHECK_STR_EQ(w[0].word, "42");
    CHECK_UINT_EQ(w[0].count, 3);
    CHECK_STR_EQ(w[1].word, "x1");
    CHECK_UINT_EQ(w[1].count, 2);
    CHECK_STR_EQ(w[2].word, "x2");
    word_freq_free(w, n);
}

TEST(punctuation_splits_words) {
    WordCount *w = NULL;
    size_t n = word_freq("it's a dog-eat-dog world,isn't it?", 10, &w);
    CHECK_UINT_EQ(n, 8);
    CHECK_STR_EQ(w[0].word, "dog");
    CHECK_UINT_EQ(w[0].count, 2);
    CHECK_STR_EQ(w[1].word, "it");
    CHECK_UINT_EQ(w[1].count, 2);
    CHECK_STR_EQ(w[2].word, "a");
    CHECK_STR_EQ(w[3].word, "eat");
    CHECK_STR_EQ(w[4].word, "isn");
    CHECK_STR_EQ(w[5].word, "s");
    CHECK_STR_EQ(w[6].word, "t");
    CHECK_STR_EQ(w[7].word, "world");
    word_freq_free(w, n);
}

TEST(k_larger_than_distinct_words) {
    WordCount *w = NULL;
    size_t n = word_freq("a b a", 100, &w);
    CHECK_UINT_EQ(n, 2);
    CHECK_STR_EQ(w[0].word, "a");
    CHECK_UINT_EQ(w[0].count, 2);
    CHECK_STR_EQ(w[1].word, "b");
    word_freq_free(w, n);
}

TEST(k_zero_yields_null) {
    WordCount *w = (WordCount *)0x1;
    size_t n = word_freq("a b c", 0, &w);
    CHECK_UINT_EQ(n, 0);
    CHECK_NULL(w);
    word_freq_free(w, n);
}

TEST(empty_text_yields_null) {
    WordCount *w = (WordCount *)0x1;
    size_t n = word_freq("", 3, &w);
    CHECK_UINT_EQ(n, 0);
    CHECK_NULL(w);
}

TEST(text_without_words_yields_null) {
    WordCount *w = (WordCount *)0x1;
    size_t n = word_freq("... --- !!! \n\t", 3, &w);
    CHECK_UINT_EQ(n, 0);
    CHECK_NULL(w);
}

TEST(null_text_yields_null) {
    WordCount *w = (WordCount *)0x1;
    size_t n = word_freq(NULL, 3, &w);
    CHECK_UINT_EQ(n, 0);
    CHECK_NULL(w);
}

TEST(words_are_owned_copies) {
    char *text = malloc(64);
    CHECK_NOT_NULL(text);
    strcpy(text, "alpha beta alpha gamma");
    WordCount *w = NULL;
    size_t n = word_freq(text, 2, &w);
    memset(text, 'X', 63); /* on piétine le texte d'origine… */
    text[63] = '\0';
    free(text);            /* …puis on le libère */
    CHECK_UINT_EQ(n, 2);
    CHECK_STR_EQ(w[0].word, "alpha");
    CHECK_UINT_EQ(w[0].count, 2);
    CHECK_STR_EQ(w[1].word, "beta");
    word_freq_free(w, n);
}

TEST(free_null_is_a_noop) {
    word_freq_free(NULL, 0);
    CHECK(1);
}

TEST(many_distinct_words) {
    /* 1000 mots distincts, w0000..w0999, le mot w0500 répété 5 fois */
    size_t cap = 1000 * 7 + 64;
    char *text = malloc(cap);
    CHECK_NOT_NULL(text);
    size_t pos = 0;
    for (int i = 0; i < 1000; i++) {
        pos += (size_t)snprintf(text + pos, cap - pos, "W%04d ", i);
    }
    for (int i = 0; i < 4; i++) {
        pos += (size_t)snprintf(text + pos, cap - pos, "w0500 ");
    }
    WordCount *w = NULL;
    size_t n = word_freq(text, 3, &w);
    free(text);
    CHECK_UINT_EQ(n, 3);
    CHECK_STR_EQ(w[0].word, "w0500");
    CHECK_UINT_EQ(w[0].count, 5);
    CHECK_STR_EQ(w[1].word, "w0000");
    CHECK_UINT_EQ(w[1].count, 1);
    CHECK_STR_EQ(w[2].word, "w0001");
    word_freq_free(w, n);
}

TEST(high_bytes_are_separators) {
    /* octets >= 0x80 : ni alphanumériques ASCII, ni signés positifs */
    WordCount *w = NULL;
    size_t n = word_freq("caf\xc3\xa9 caf\xc3\xa9 the", 3, &w);
    CHECK_UINT_EQ(n, 2);
    CHECK_STR_EQ(w[0].word, "caf");
    CHECK_UINT_EQ(w[0].count, 2);
    CHECK_STR_EQ(w[1].word, "the");
    CHECK_UINT_EQ(w[1].count, 1);
    word_freq_free(w, n);
}
