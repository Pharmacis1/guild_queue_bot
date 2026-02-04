import re

def check_brackets(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove comments
    # valid for both // and /* */
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return " " # note: a space
        else:
            return s
            
    pattern = r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"|`(?:\\.|[^\\`])*`'
    
    # We want to remove comments but KEEP strings so we don't count brackets inside strings
    # Actually, we want to remove strings too from the counting process?
    # Yes, remove everything that is not code structure.
    
    cleaned = re.sub(pattern, replacer, content, flags=re.DOTALL | re.MULTILINE)
    
    stack = []
    errors = []
    
    lines = cleaned.split('\n')
    
    # We'll traverse the cleaned text but tracking lines is hard if we stripped newlines.
    # Let's iterate char by char on the full text but skip "masked" regions? Hard.
    # Simpler: Just count total.
    
    for i, char in enumerate(cleaned):
        if char in '{[(':
            stack.append((char, i))
        elif char in '}])':
            if not stack:
                errors.append(f"Unexpected closing {char} at char {i}")
                continue
            
            last, pos = stack.pop()
            expected = '{' if char == '}' else '[' if char == ']' else '('
            if last != expected:
                errors.append(f"Mismatched {last} (at {pos}) with {char} at {i}")
                
    if stack:
        for char, pos in stack:
            errors.append(f"Unclosed {char} at char {pos}")
            
    if not errors:
        print("✅ No bracket errors found.")
    else:
        print("❌ Errors found:")
        for e in errors[:10]:
            print(e)
            
        print("\nLast 200 chars around error:")
        if errors:
            # extract pos from string if possible or just print end
            pass

if __name__ == "__main__":
    check_brackets("static/js/script.js")
