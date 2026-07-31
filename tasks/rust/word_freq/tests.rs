use task::top_k;

fn owned(pairs: &[(&str, usize)]) -> Vec<(String, usize)> {
    pairs.iter().map(|(w, c)| ((*w).to_string(), *c)).collect()
}

const PANGRAM: &str = "the quick brown fox jumps over the lazy dog the fox";

#[test]
fn basic_top_three() {
    assert_eq!(
        top_k(PANGRAM, 3),
        owned(&[("the", 3), ("fox", 2), ("brown", 1)])
    );
}

#[test]
fn ties_are_sorted_lexicographically() {
    // counts 1 for: brown, dog, jumps, lazy, over, quick
    assert_eq!(
        top_k(PANGRAM, 6),
        owned(&[
            ("the", 3),
            ("fox", 2),
            ("brown", 1),
            ("dog", 1),
            ("jumps", 1),
            ("lazy", 1),
        ])
    );
}

#[test]
fn k_larger_than_vocabulary() {
    assert_eq!(top_k("a b a", 100), owned(&[("a", 2), ("b", 1)]));
}

#[test]
fn k_zero_is_empty() {
    assert_eq!(top_k(PANGRAM, 0), Vec::<(String, usize)>::new());
}

#[test]
fn empty_text_is_empty() {
    assert_eq!(top_k("", 3), Vec::<(String, usize)>::new());
}

#[test]
fn punctuation_only_is_empty() {
    assert_eq!(top_k("!!! ... ,;:", 3), Vec::<(String, usize)>::new());
}

#[test]
fn case_is_folded() {
    assert_eq!(top_k("Hello, hello! HELLO?", 5), owned(&[("hello", 3)]));
}

#[test]
fn digits_are_part_of_words() {
    assert_eq!(top_k("a1 a1 b2", 5), owned(&[("a1", 2), ("b2", 1)]));
}

#[test]
fn punctuation_splits_words() {
    assert_eq!(
        top_k("rust-lang rust lang", 3),
        owned(&[("lang", 2), ("rust", 2)])
    );
}

#[test]
fn unicode_lowercasing() {
    assert_eq!(top_k("Élan élan ÉLAN naïve", 2), owned(&[("élan", 3), ("naïve", 1)]));
}
