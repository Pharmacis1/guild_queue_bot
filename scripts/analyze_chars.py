
def analyze(text):
    print(f"Analyzing: {text}")
    for char in text:
        print(f"  {char}: U+{ord(char):04X} ({char.encode('unicode_escape')})")

examples = [
    "ｏｆｆｅｎｓｅ",
    "ｒｅｄ",
    "ｙｅｌｌｏｗ"
]

for ex in examples:
    analyze(ex)
    # Simulate JS logic: 0xFF01 - 0xFF5E -> -0xFEE0
    normalized = ""
    for char in ex:
        code = ord(char)
        if 0xFF01 <= code <= 0xFF5E:
            normalized += chr(code - 0xFEE0)
        elif code == 0x3000:
            normalized += " "
        else:
            normalized += char
    print(f"  Result: {normalized}")
