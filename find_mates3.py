import urllib.request, json
url = "https://lichess.org/api/puzzle/daily"
# Let's just hardcode some PGNs that lead to mate in 3 and get FEN and SAN.
import chess

games = [
    # Opera game
    "1.e4 e5 2.Nf3 d6 3.d4 Bg4 4.dxe5 Bxf3 5.Qxf3 dxe5 6.Bc4 Nf6 7.Qb3 Qe7 8.Nc3 c6 9.Bg5 b5 10.Nxb5 cxb5 11.Bxb5+ Nbd7 12.O-O-O Rd8 13.Rxd7 Rxd7 14.Rd1 Qe6 15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8#",
    # Legal trap
    "1.e4 e5 2.Nf3 Nc6 3.Bc4 d6 4.Nc3 Bg4 5.h3 Bh5 6.Nxe5 Bxd1 7.Bxf7+ Ke7 8.Nd5#",
]

for g in games:
    board = chess.Board()
    for m in g.split():
        if '.' in m: m = m.split('.')[1]
        board.push_san(m)
    
    # Go back 5 half-moves (which is 3 moves for the winner)
    # Actually Opera game: 16. Qb8+ Nxb8 17. Rd8#. That's mate in 2. (Qb8+, Nxb8, Rd8# = 3 half-moves)
