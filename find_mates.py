import chess

puzzles = [
    {
        "fen": "r5rk/5p1p/5R2/4B3/8/8/7P/7K w - - 0 1",
        "solution": ["Rg6+", "f6", "Bxf6+", "Rg7", "Bxg7#"]
    },
    {
        "fen": "2r3k1/1p3p1p/p2p2p1/3P4/P1q5/5P2/1B4PP/4Q2K w - - 0 1",
        "solution": ["Qe8+", "Rxe8", "Rxe8#"] # Wait, White doesn't have a rook.
    }
]

for p in puzzles:
    board = chess.Board(p['fen'])
    valid = True
    for move_san in p['solution']:
        try:
            move = board.parse_san(move_san)
            board.push(move)
        except:
            print("Invalid:", move_san)
            valid = False
            break
    if valid and board.is_checkmate():
        print("Valid mate in 3 FEN:", p['fen'])
