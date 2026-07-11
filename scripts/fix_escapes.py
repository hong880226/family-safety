"""Fix escape sequences in gen_p2_module1.py."""
from pathlib import Path

p = Path("E:/codeRepo/familysafety/scripts/gen_p2_module1.py")
text = p.read_text(encoding="utf-8")

# The file has literal characters: \"
# In Python source, we want them to just be: "
# Replace the backslash before quote pairs in regex/JSON contexts

# Simple approach: just replace every \" (literal) with "
new_text = text.replace('\\"', '"')

if new_text != text:
    p.write_text(new_text, encoding="utf-8")
    print(f"Fixed: {text.count(chr(92) + chr(34))} replacements")
else:
    print("No changes needed")

print(f"File size: {len(new_text)} bytes")