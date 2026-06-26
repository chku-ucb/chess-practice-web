# ♔ Chess Coach AI

An intelligent, autonomous 3-agent chess coaching web application focused on helping users master advanced **Mate in 3** tactical combinations. 

Unlike standard puzzle trainers that simply tell you "Right" or "Wrong," this application uses a multi-agent AI system to analyze *why* a move works, identify your tactical blindspots, and provide personalized coaching notes that evolve as you play.

## ✨ Features

- **Master-Level Database**: 50+ authentic, high-quality "Mate in 3" puzzles sourced from the real-world Lichess database.
- **Multi-step Execution**: Play through entire combinations. The backend engine automatically calculates and plays the opponent's forced replies.
- **Performance Reviews**: An automated UI modal pops up every 5 puzzles tracking your accuracy, current/best streaks, and highlighting specific tactical concepts you need to focus on.
- **Server-Side Guardrails**: Absolute move validation using `python-chess` ensures the AI never hallucinates illegal positions.
- **Beautiful UI**: Modern glassmorphism design, smooth piece animations, and clear visual move highlighting.

## 🧠 Three-Agent Architecture

The core of the coaching experience is driven by three distinct AI agents working in tandem:

1. **Agent 1: The Puzzle Master**
   Looks at your current skill level and memory context, then retrieves a tailored "Mate in 3" puzzle perfectly suited for your progression.
2. **Agent 2: The Analyst**
   Acts as your strict-but-encouraging coach. It compares your move against the exact solution sequence, identifies any tactical blindspots you might have missed, and generates a personalized explanation for your move.
3. **Agent 3: The Director**
   Operating in the background, the Director receives the Analyst's report and updates your global profile. It tracks your streaks, adjusts your coaching notes, and prepares your 5-puzzle performance reviews.

## 🛠 Tech Stack

- **Backend**: Python, FastAPI, `python-chess` (for rigorous move validation)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3 (Glassmorphism design)
- **Chess UI**: `chessboard.js` (Board rendering) and `chess.js` (Client-side game logic)
- **AI Integration**: OpenAI-compatible LLM routing for the Agent system

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- A virtual environment (`venv`)

### Installation
1. Clone or navigate to the repository:
   ```bash
   cd chess-practice-web
   ```
2. Activate your virtual environment:
   ```bash
   source venv/bin/activate
   ```
3. Install the dependencies (if you haven't already):
   ```bash
   pip install fastapi uvicorn python-chess openai
   ```
4. Start the FastAPI server:
   ```bash
   uvicorn app:app --reload
   ```
5. Open your browser and navigate to `http://localhost:8000`.

## 🎮 How to Play

1. The game will automatically load a Mate in 3 puzzle for you.
2. Drag and drop a piece to make your move. 
3. If your move is correct, the opponent will automatically play their forced reply. Keep moving until you deliver checkmate!
4. If you make a mistake, the Analyst will step in, highlight the correct move, and explain why your move failed.
5. Every 5 puzzles, a **Performance Review** modal will appear detailing your progress and what you should focus on next.
