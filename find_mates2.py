import chess

puzzles = [
    {
        "fen": "r5rk/5p1p/5R2/4B3/8/8/7P/7K w - - 0 1",
        "solution": ["Rg6+", "f6", "Bxf6+", "Rg7", "Bxg7#"]
    },
    {
        "fen": "4r1k1/5ppp/8/8/8/8/5PPP/R2R2K1 w - - 0 1",
        "solution": ["Ra8", "Rxa8", "Rd8+", "Rxd8", "Rxd8#"]
    },
    {
        "fen": "k7/p1p5/1pP5/8/8/8/5PPP/R2R2K1 w - - 0 1",
        "solution": ["Rd8+", "Rxd8", "Rxd8#"] # wait this is mate in 2.
    }
]

for p in puzzles:
    try:
        board = chess.Board(p['fen'])
        for m in p['solution']:
            board.push_san(m)
        if board.is_checkmate():
            print("VALID", p['fen'])
        else:
            print("INVALID MATE", p['fen'])
    except Exception as e:
        print("ERROR", p['fen'], e)
