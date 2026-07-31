import re


def encode(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and text[j] == text[i]:
            j += 1
        run = j - i
        if run > 1:
            out.append(str(run))
        out.append(text[i])
        i = j
    return "".join(out)


def decode(text: str) -> str:
    out = []
    for count, char in re.findall(r"(\d*)(\D)", text):
        out.append(char * (int(count) if count else 1))
    return "".join(out)
