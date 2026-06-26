import csv
import chess

puzzles = []

with open('mates.csv', 'r') as f:
    reader = csv.reader(f)
    for row in reader:
        if not row: continue
        puzzle_id = row[0]
        fen = row[1]
        uci_moves = row[2].split()
        theme = row[7].replace(' ', ', ')
        
        try:
            board = chess.Board(fen)
            san_moves = []
            for uci in uci_moves:
                move = chess.Move.from_uci(uci)
                san = board.san(move)
                board.push(move)
                san_moves.append(san)
            
            puzzles.append({
                "fen": fen,
                "solution": san_moves,
                "hint": "Try to find the forced mate in 3.",
                "theme": theme,
                "full_line": " ".join(san_moves)
            })
        except Exception as e:
            print("Error parsing", puzzle_id, e)

import json
print("Found", len(puzzles), "puzzles.")
with open('new_puzzles.json', 'w') as f:
    json.dump({"mate_in_3": puzzles}, f, indent=4)
