#include "harness.h"

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

TEST(empty_input_gives_empty_table) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("", &t), CSV_OK);
    CHECK_NOT_NULL(t);
    CHECK_UINT_EQ(t->nrows, 0);
    csv_free(t);
}

TEST(null_input_gives_empty_table) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse(NULL, &t), CSV_OK);
    CHECK_NOT_NULL(t);
    CHECK_UINT_EQ(t->nrows, 0);
    csv_free(t);
}

TEST(single_field) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 1);
    CHECK_UINT_EQ(t->ncols[0], 1);
    CHECK_STR_EQ(t->rows[0][0], "a");
    csv_free(t);
}

TEST(three_fields_one_row) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,b,c", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 1);
    CHECK_UINT_EQ(t->ncols[0], 3);
    CHECK_STR_EQ(t->rows[0][0], "a");
    CHECK_STR_EQ(t->rows[0][1], "b");
    CHECK_STR_EQ(t->rows[0][2], "c");
    csv_free(t);
}

TEST(two_rows_with_trailing_newline) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,b\nc,d\n", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 2);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_UINT_EQ(t->ncols[1], 2);
    CHECK_STR_EQ(t->rows[0][0], "a");
    CHECK_STR_EQ(t->rows[1][1], "d");
    csv_free(t);
}

TEST(two_rows_without_trailing_newline) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,b\nc,d", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 2);
    CHECK_STR_EQ(t->rows[1][0], "c");
    csv_free(t);
}

TEST(crlf_is_a_record_separator) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,b\r\nc,d\r\n", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 2);
    CHECK_STR_EQ(t->rows[0][1], "b");
    CHECK_STR_EQ(t->rows[1][0], "c");
    csv_free(t);
}

TEST(lone_cr_is_an_ordinary_character) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a\rb,c", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 1);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_STR_EQ(t->rows[0][0], "a\rb");
    csv_free(t);
}

TEST(empty_fields_are_kept) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,,b", &t), CSV_OK);
    CHECK_UINT_EQ(t->ncols[0], 3);
    CHECK_STR_EQ(t->rows[0][0], "a");
    CHECK_STR_EQ(t->rows[0][1], "");
    CHECK_STR_EQ(t->rows[0][2], "b");
    csv_free(t);
}

TEST(row_of_two_empty_fields) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse(",\n", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 1);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_STR_EQ(t->rows[0][0], "");
    CHECK_STR_EQ(t->rows[0][1], "");
    csv_free(t);
}

TEST(blank_line_in_the_middle) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a\n\nb", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 3);
    CHECK_UINT_EQ(t->ncols[1], 1);
    CHECK_STR_EQ(t->rows[1][0], "");
    CHECK_STR_EQ(t->rows[2][0], "b");
    csv_free(t);
}

TEST(ragged_rows_are_allowed) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,b,c\nd\ne,f", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 3);
    CHECK_UINT_EQ(t->ncols[0], 3);
    CHECK_UINT_EQ(t->ncols[1], 1);
    CHECK_UINT_EQ(t->ncols[2], 2);
    csv_free(t);
}

TEST(quoted_field_with_comma) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("\"x,y\",z", &t), CSV_OK);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_STR_EQ(t->rows[0][0], "x,y");
    CHECK_STR_EQ(t->rows[0][1], "z");
    csv_free(t);
}

TEST(quoted_field_with_newline) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("\"ligne1\nligne2\",b", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 1);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_STR_EQ(t->rows[0][0], "ligne1\nligne2");
    csv_free(t);
}

TEST(quoted_field_with_crlf_inside) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("\"a\r\nb\"\r\nc", &t), CSV_OK);
    CHECK_UINT_EQ(t->nrows, 2);
    CHECK_STR_EQ(t->rows[0][0], "a\r\nb");
    CHECK_STR_EQ(t->rows[1][0], "c");
    csv_free(t);
}

TEST(escaped_quotes) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("\"a\"\"b\"", &t), CSV_OK);
    CHECK_STR_EQ(t->rows[0][0], "a\"b");
    csv_free(t);
}

TEST(field_that_is_only_two_quotes_is_empty) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("\"\",x", &t), CSV_OK);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_STR_EQ(t->rows[0][0], "");
    CHECK_STR_EQ(t->rows[0][1], "x");
    csv_free(t);
}

TEST(quoted_field_ending_the_input) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse("a,\"b\"", &t), CSV_OK);
    CHECK_UINT_EQ(t->ncols[0], 2);
    CHECK_STR_EQ(t->rows[0][1], "b");
    csv_free(t);
}

TEST(spaces_are_significant) {
    CsvTable *t = NULL;
    CHECK_INT_EQ(csv_parse(" a , b ", &t), CSV_OK);
    CHECK_STR_EQ(t->rows[0][0], " a ");
    CHECK_STR_EQ(t->rows[0][1], " b ");
    csv_free(t);
}

TEST(unterminated_quote_is_rejected) {
    CsvTable *t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("a,\"b", &t), CSV_UNTERMINATED_QUOTE);
    CHECK_NULL(t);
    t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("\"a\"\"", &t), CSV_UNTERMINATED_QUOTE);
    CHECK_NULL(t);
}

TEST(bare_quote_inside_unquoted_field_is_rejected) {
    CsvTable *t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("a\"b", &t), CSV_BARE_QUOTE);
    CHECK_NULL(t);
    t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("x,y\nz,a\"b", &t), CSV_BARE_QUOTE);
    CHECK_NULL(t);
}

TEST(text_after_closing_quote_is_rejected) {
    CsvTable *t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("\"ab\"c", &t), CSV_BARE_QUOTE);
    CHECK_NULL(t);
    t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("\"ab\" ,c", &t), CSV_BARE_QUOTE);
    CHECK_NULL(t);
}

TEST(quote_after_a_space_is_not_a_quoted_field) {
    CsvTable *t = (CsvTable *)0x1;
    CHECK_INT_EQ(csv_parse("a, \"b\"", &t), CSV_BARE_QUOTE);
    CHECK_NULL(t);
}

TEST(free_null_is_a_noop) {
    csv_free(NULL);
    CHECK(1);
}

TEST(large_input) {
    /* 2000 lignes de 4 champs, dont un champ cité contenant une virgule */
    size_t cap = 2000 * 40 + 1;
    char *text = malloc(cap);
    CHECK_NOT_NULL(text);
    size_t pos = 0;
    for (int i = 0; i < 2000; i++) {
        pos += (size_t)snprintf(text + pos, cap - pos, "%d,\"a,b\",\"c\"\"d\",e\n", i);
    }
    CsvTable *t = NULL;
    CsvError rc = csv_parse(text, &t);
    free(text);
    CHECK_INT_EQ(rc, CSV_OK);
    CHECK_UINT_EQ(t->nrows, 2000);
    CHECK_UINT_EQ(t->ncols[1999], 4);
    CHECK_STR_EQ(t->rows[0][0], "0");
    CHECK_STR_EQ(t->rows[1999][0], "1999");
    CHECK_STR_EQ(t->rows[1999][1], "a,b");
    CHECK_STR_EQ(t->rows[1999][2], "c\"d");
    CHECK_STR_EQ(t->rows[1999][3], "e");
    csv_free(t);
}
