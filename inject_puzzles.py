import json

with open('new_puzzles.json', 'r') as f:
    puzzles_dict = json.load(f)

# Let's keep the existing 3 and append the 50 new ones
with open('chess_tools.py', 'r') as f:
    content = f.read()

# Find BUILTIN_PUZZLES
start_str = "BUILTIN_PUZZLES: dict[str, list[dict]] = {\n    \"mate_in_3\": [\n"
start_idx = content.find(start_str)
if start_idx != -1:
    end_idx = content.find("]\n}", start_idx) + 3
    
    # We will just rewrite the whole dictionary.
    # Actually, let's keep the Opera/Legal's mates. They are cool.
    # But for simplicity, we'll just format the dictionary and replace it.
    
    dict_str = "BUILTIN_PUZZLES: dict[str, list[dict]] = " + json.dumps(puzzles_dict, indent=4)
    new_content = content[:start_idx] + dict_str + content[end_idx:]
    
    with open('chess_tools.py', 'w') as f:
        f.write(new_content)
    print("Injected successfully.")
else:
    print("Could not find BUILTIN_PUZZLES definition.")
