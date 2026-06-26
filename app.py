"""
app.py — FastAPI server for the Chess Coaching application.

Routes:
  GET  /             → Serves the frontend (index.html)
  GET  /get_puzzle    → Returns a puzzle appropriate for the user's current level
  POST /evaluate      → Evaluates the user's move and returns analysis + progression
  POST /reset         → Resets the user's state to defaults
  GET  /state         → Returns the current user state (for debugging / UI sync)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any module that reads env vars
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from agents import (
    AnalystAgent,
    DirectorAgent,
    PuzzleMasterAgent,
)
from chess_tools import (
    startup_validation,
    validate_move,
    reset_served_tracker,
    get_turn,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App & Agents
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global user_state, current_puzzle
    summary = startup_validation()
    logger.info("Built-in puzzle validation: %s", summary)
    user_state = DirectorAgent.create_initial_state()
    current_puzzle = None
    yield

app = FastAPI(title="Chess Coach AI", version="1.0.0", lifespan=lifespan)

puzzle_master = PuzzleMasterAgent()
analyst = AnalystAgent()
director = DirectorAgent()

# In-memory user state (single-user, local app)
user_state: dict = DirectorAgent.create_initial_state()

# Current puzzle being solved (stored server-side so the solution isn't leaked)
current_puzzle: dict | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_frontend() -> HTMLResponse:
    """Serve the single-page frontend."""
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/get_puzzle")
def get_puzzle() -> JSONResponse:
    """
    Ask Agent 3 for the current level, then Agent 1 for a matching puzzle.
    Returns the FEN, hint, level info, and coaching message to the frontend.
    The solution is kept server-side.
    """
    global current_puzzle

    try:
        # Agent 3 — determine level & category
        level_info = director.get_level_info(user_state)
        
        # Load long-term memory context
        profile = director.load_session_profile()

        # Agent 1 — generate / select a puzzle
        puzzle = puzzle_master.generate_puzzle(
            category=level_info["category"],
            difficulty=level_info["difficulty_key"],
            memory_context=profile,
        )

        current_puzzle = puzzle

        return JSONResponse(content={
            "success": True,
            "fen": puzzle["fen"],
            "hint": puzzle.get("hint", ""),
            "theme": puzzle.get("theme", ""),
            "turn": get_turn(puzzle["fen"]),
            "level_info": {
                "level": level_info["level"],
                "name": level_info["name"],
                "description": level_info["description"],
            },
            "coaching_notes": user_state.get("coaching_notes", ""),
            "stats": _build_stats(),
        })
    except Exception as exc:
        logger.exception("Error in /get_puzzle")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)},
        )


@app.post("/evaluate")
async def evaluate(request: Request) -> JSONResponse:
    """
    Receive the user's move, pass it through Agent 2 (Analyst) and Agent 3
    (Director), then return the analysis and updated state.
    """
    global current_puzzle

    try:
        body = await request.json()
        user_move: str = body.get("user_move", "").strip()

        if not user_move:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No move provided."},
            )

        if current_puzzle is None:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No active puzzle. Call /get_puzzle first."},
            )

        fen = current_puzzle["fen"]
        solution = current_puzzle["solution"]
        
        # Get the current step of the puzzle
        step = current_puzzle.get("step", 0)
        expected_moves = solution[step:]

        # 1. ABSOLUTE SECURITY GUARDRAIL: Pre-Agent Move Validation
        from chess_tools import get_legal_moves, apply_move
        legal_moves = get_legal_moves(fen)
        if user_move not in legal_moves:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "error_type": "ILLEGAL_MOVE",
                    "feedback": "That move is illegal according to official chess rules. Try again!"
                },
            )

        # Agent 2 — analyse the move against the remaining steps of the solution
        analysis = analyst.analyze_move(fen, expected_moves, user_move)

        is_correct = analysis.get("accuracy_delta", 0) > 0
        puzzle_completed = False
        opponent_reply = None
        correct_move = analysis.get("correct_move", expected_moves[0] if expected_moves else "")

        if is_correct:
            if step + 1 < len(solution):
                opponent_reply = solution[step + 1]
                # Update FEN locally
                new_fen = apply_move(fen, user_move)
                if new_fen and opponent_reply:
                    new_fen = apply_move(new_fen, opponent_reply)
                    if new_fen:
                        current_puzzle["fen"] = new_fen
                
                # Advance step by 2 (user move + opponent move)
                current_puzzle["step"] = step + 2
                
                if current_puzzle["step"] >= len(solution):
                    puzzle_completed = True
            else:
                puzzle_completed = True
        else:
            puzzle_completed = True

        # Agent 3 — update progression only when the puzzle finishes
        if puzzle_completed:
            director.update_state(user_state, analysis)

        return JSONResponse(content={
            "success": True,
            "correct": is_correct,
            "puzzle_completed": puzzle_completed,
            "opponent_reply": opponent_reply,
            "user_move": user_move,
            "correct_move": correct_move,
            "analysis": analysis.get("performance_summary", ""),
            "explanation": analysis.get("explanation", ""),
            "tactical_blindspots": analysis.get("tactical_blindspots", []),
            "coaching_notes": user_state.get("coaching_notes", ""),
            "stats": _build_stats(),
            "level_info": {
                "level": director.get_level_info(user_state)["level"],
                "name": director.get_level_info(user_state)["name"],
            },
        })
    except Exception as exc:
        logger.exception("Error in /evaluate")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)},
        )


@app.post("/reset")
def reset_state() -> JSONResponse:
    """Reset the user's state and puzzle tracker."""
    global user_state, current_puzzle
    user_state = DirectorAgent.create_initial_state()
    current_puzzle = None
    reset_served_tracker()
    return JSONResponse(content={
        "success": True,
        "message": "Progress reset. Let's start fresh!",
        "stats": _build_stats(),
    })


@app.get("/state")
def get_state() -> JSONResponse:
    """Return the raw user state (useful for debugging)."""
    return JSONResponse(content={
        "success": True,
        "user_state": user_state,
        "level_info": director.get_level_info(user_state),
        "has_puzzle": current_puzzle is not None,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_stats() -> dict:
    return {
        "total": user_state["total_puzzles"],
        "correct": user_state["correct"],
        "wrong": user_state["wrong"],
        "streak": user_state["streak"],
        "best_streak": user_state["best_streak"],
        "accuracy": (
            round(user_state["correct"] / user_state["total_puzzles"] * 100)
            if user_state["total_puzzles"] > 0
            else 0
        ),
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host=host, port=port, reload=True)
