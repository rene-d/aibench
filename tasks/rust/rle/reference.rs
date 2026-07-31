pub fn encode(input: &str) -> String {
    let mut out = String::new();
    let mut chars = input.chars().peekable();
    while let Some(c) = chars.next() {
        let mut count = 1usize;
        while chars.peek() == Some(&c) {
            chars.next();
            count += 1;
        }
        if count > 1 {
            out.push_str(&count.to_string());
        }
        out.push(c);
    }
    out
}

pub fn decode(input: &str) -> String {
    let mut out = String::new();
    let mut num = String::new();
    for c in input.chars() {
        if c.is_ascii_digit() {
            num.push(c);
        } else {
            let n: usize = num.parse().unwrap_or(1);
            for _ in 0..n {
                out.push(c);
            }
            num.clear();
        }
    }
    out
}
