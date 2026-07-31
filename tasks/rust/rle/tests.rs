use task::{decode, encode};

#[test]
fn encode_empty() {
    assert_eq!(encode(""), "");
}

#[test]
fn encode_single_characters() {
    assert_eq!(encode("XYZ"), "XYZ");
}

#[test]
fn encode_simple_runs() {
    assert_eq!(encode("AABBBCCCC"), "2A3B4C");
}

#[test]
fn encode_with_whitespace() {
    assert_eq!(encode("  hsqq qww  "), "2 hs2q q2w2 ");
}

#[test]
fn encode_multi_digit_counts() {
    let input = "WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB";
    assert_eq!(encode(input), "12WB12W3B24WB");
}

#[test]
fn encode_lowercase_and_uppercase_are_distinct() {
    assert_eq!(encode("aaAA"), "2a2A");
}

#[test]
fn decode_empty() {
    assert_eq!(decode(""), "");
}

#[test]
fn decode_single_characters() {
    assert_eq!(decode("XYZ"), "XYZ");
}

#[test]
fn decode_simple_runs() {
    assert_eq!(decode("2A3B4C"), "AABBBCCCC");
}

#[test]
fn decode_with_whitespace() {
    assert_eq!(decode("2 hs2q q2w2 "), "  hsqq qww  ");
}

#[test]
fn decode_multi_digit_counts() {
    let expected = "WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB";
    assert_eq!(decode("12WB12W3B24WB"), expected);
}

#[test]
fn round_trip() {
    let input = "zzz ZZ  zZ";
    assert_eq!(decode(&encode(input)), input);
}
