"""
agents.py — Three-agent chess coaching system.

Agent 1 (Puzzle Master):  Generates / selects puzzles by category & difficulty.
Agent 2 (The Analyst):    Compares the user's move to the solution and produces feedback.
Agent 3 (The Director):   Manages user progression, difficulty, and coaching notes.

Each agent falls back to deterministic logic when the LLM is unavailable, so the
app works fully offline with the built-in puzzle database.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from openai import OpenAI

from chess_tools import (
    get_builtin_puzzle,
    validate_fen,
    validate_move,
    validate_solution,
    apply_move,
    get_legal_moves,
    is_checkmate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Client — uses an OpenAI-compatible API.
# Set environment variables to point at any endpoint (OpenAI, Ollama, etc.)
# ---------------------------------------------------------------------------

_api_key = os.getenv("OPENAI_API_KEY", "")
_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_model = os.getenv("LLM_MODEL", "gpt-4")

# Only create the client when a key is configured.
_client: Optional[OpenAI] = None
if _api_key and _api_key != "your-api-key-here":
    try:
        _client = OpenAI(api_key=_api_key, base_url=_base_url)
        logger.info("OpenAI client initialised (base_url=%s, model=%s)", _base_url, _model)
    except Exception as exc:
        logger.warning("Could not initialise OpenAI client: %s", exc)


def _llm_available() -> bool:
    return _client is not None


def _safe_json_parse(text: str) -> Optional[dict]:
    """Attempt to parse JSON from an LLM response, stripping markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove ```json ... ``` wrappers
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed: %s — raw text: %.300s", exc, text)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 1 — Puzzle Master
# ═══════════════════════════════════════════════════════════════════════════════

class PuzzleMasterAgent:
    """
    Generates chess puzzles.  Prefers the built-in database for speed and
    reliability; falls back to LLM generation for variety at higher levels.
    """

    SYSTEM_PROMPT = """You are a world-class chess puzzle composer.
Given a category and difficulty, generate ONE original chess puzzle.

Rules:
- The FEN must represent a valid, legal chess position.
- The solution array must contain legal moves in Standard Algebraic Notation (SAN).
- For checkmate puzzles the final move MUST end in checkmate.
- For tactics puzzles, the first move should give a clear, forcing advantage.
- Include a short, helpful hint (no spoilers).

Return ONLY a JSON object with these keys:
{
  "fen": "<valid FEN>",
  "solution": ["<SAN move 1>", "<SAN move 2 (if applicable)>"],
  "hint": "<short hint>",
  "theme": "<tactical theme>"
}"""

    def generate_puzzle(
        self,
        category: str = "checkmate",
        difficulty: str = "mate_in_1",
        exclude_fens: Optional[list[str]] = None,
        memory_context: Optional[dict] = None,
    ) -> dict:
        """
        Return a puzzle dict with keys: fen, solution, hint, theme, difficulty, source.
        """
        # 1) Try built-in database first (fast, reliable)
        # Note: In a production system, we could filter built-in puzzles by memory_context.
        # Here we prioritize LLM if memory_context is rich, but the code falls back below.
        builtin = get_builtin_puzzle(difficulty, exclude_fens=exclude_fens)
        if builtin and not memory_context:
            return builtin

        # 2) Try LLM generation
        if _llm_available():
            puzzle = self._generate_via_llm(category, difficulty, memory_context)
            if puzzle:
                return puzzle
            
        if builtin:
            return builtin

        # 2) Try LLM generation
        if _llm_available():
            puzzle = self._generate_via_llm(category, difficulty)
            if puzzle:
                return puzzle

        # 3) Fallback — serve any available puzzle
        for fallback_diff in ["mate_in_3"]:
            fb = get_builtin_puzzle(fallback_diff, exclude_fens=exclude_fens)
            if fb:
                fb["difficulty"] = difficulty  # label with requested difficulty
                return fb

        # Should never reach here if the built-in DB is intact
        return {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "solution": ["e4"],
            "hint": "Start the game!",
            "theme": "opening",
            "difficulty": difficulty,
            "source": "fallback",
        }

    def _generate_via_llm(self, category: str, difficulty: str, memory_context: Optional[dict] = None) -> Optional[dict]:
        """Ask the LLM to compose a puzzle. Returns None on any failure."""
        try:
            context_str = json.dumps(memory_context) if memory_context else "None"
            user_msg = (
                f"Category: {category}\n"
                f"Difficulty: {difficulty}\n"
                f"User Profile / Memory Context: {context_str}\n"
                f"Adapt the puzzle choice to the user's historical blindspots if any, and tailor hints to help them.\n"
                f"Generate a unique chess puzzle."
            )
            resp = _client.chat.completions.create(  # type: ignore[union-attr]
                model=_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.8,
                max_tokens=500,
            )
            data = _safe_json_parse(resp.choices[0].message.content or "")
            if not data:
                return None

            fen = data.get("fen", "")
            solution = data.get("solution", [])
            if not validate_fen(fen) or not validate_solution(fen, solution):
                logger.warning("LLM-generated puzzle failed validation — FEN=%s", fen)
                return None

            return {
                "fen": fen,
                "solution": solution,
                "hint": data.get("hint", ""),
                "theme": data.get("theme", ""),
                "difficulty": difficulty,
                "source": "llm",
            }
        except Exception as exc:
            logger.error("PuzzleMasterAgent LLM call failed: %s", exc)
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 2 — The Analyst
# ═══════════════════════════════════════════════════════════════════════════════

class AnalystAgent:
    """
    Compares the user's move against the correct solution and returns a
    structured analysis JSON.
    """

    SYSTEM_PROMPT = """You are a supportive but rigorous chess coach.
Analyse the student's move compared to the correct solution.

Context you will receive:
- The starting FEN
- The correct solution (sequence of SAN moves)
- The student's move (SAN)

Return ONLY a JSON object:
{
  "performance_summary": "<2-3 sentence analysis>",
  "accuracy_delta": 1 or -1,
  "tactical_blindspots": ["<concept the student missed>", ...],
  "explanation": "<why the correct move works>"
}

Guidelines:
- accuracy_delta is 1 if the student's move matches the first move of the solution, else -1.
- Be encouraging even when the move is wrong.
- Identify specific tactical concepts the student missed (e.g. "back rank weakness",
  "unprotected piece", "discovered attack").
- Keep explanations concise but insightful."""

    def analyze_move(
        self,
        fen: str,
        solution: list[str],
        user_move: str,
    ) -> dict:
        """
        Return an analysis dict with keys:
        performance_summary, accuracy_delta, tactical_blindspots, explanation, correct_move.
        """
        correct_move = solution[0] if solution else ""
        is_correct = self._moves_match(fen, user_move, correct_move)

        # 1) Try LLM for rich, natural-language analysis
        if _llm_available():
            llm_result = self._analyze_via_llm(fen, solution, user_move, is_correct)
            if llm_result:
                llm_result["correct_move"] = correct_move
                return llm_result

        # 2) Deterministic fallback
        return self._deterministic_analysis(fen, solution, user_move, is_correct)

    def _moves_match(self, fen: str, user_move: str, correct_move: str) -> bool:
        """
        Compare two SAN strings, tolerating minor notation differences
        (e.g. "Re8" vs "Re8#" where the engine adds mate symbols).
        """
        # Strip check / mate indicators for comparison
        def normalise(m: str) -> str:
            return m.rstrip("+#").strip()

        if normalise(user_move) == normalise(correct_move):
            return True

        # Compare by resulting board position
        result_user = apply_move(fen, user_move)
        result_correct = apply_move(fen, correct_move)
        if result_user and result_correct and result_user == result_correct:
            return True

        return False

    def _analyze_via_llm(
        self, fen: str, solution: list[str], user_move: str, is_correct: bool
    ) -> Optional[dict]:
        try:
            user_msg = (
                f"Position (FEN): {fen}\n"
                f"Correct solution: {json.dumps(solution)}\n"
                f"Student's move: {user_move}\n"
                f"Is correct: {is_correct}"
            )
            resp = _client.chat.completions.create(  # type: ignore[union-attr]
                model=_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.6,
                max_tokens=500,
            )
            data = _safe_json_parse(resp.choices[0].message.content or "")
            if data and "performance_summary" in data:
                # Enforce correct accuracy_delta regardless of LLM opinion
                data["accuracy_delta"] = 1 if is_correct else -1
                return data
        except Exception as exc:
            logger.error("AnalystAgent LLM call failed: %s", exc)
        return None

    def _deterministic_analysis(
        self, fen: str, solution: list[str], user_move: str, is_correct: bool
    ) -> dict:
        correct_move = solution[0] if solution else "?"

        if is_correct:
            # Check if the move leads to checkmate
            result_fen = apply_move(fen, user_move)
            mate_suffix = ""
            if result_fen and is_checkmate(result_fen):
                mate_suffix = " Checkmate!"

            return {
                "performance_summary": (
                    f"Excellent! {user_move} is the correct move.{mate_suffix} "
                    f"You found the key idea in this position."
                ),
                "accuracy_delta": 1,
                "tactical_blindspots": [],
                "explanation": (
                    f"The move {correct_move} exploits the weaknesses in the opponent's "
                    f"position. Well played!"
                ),
                "correct_move": correct_move,
            }
        else:
            # Identify what the user might have missed
            blindspots = []
            result_correct = apply_move(fen, correct_move)
            if result_correct and is_checkmate(result_correct):
                blindspots.append("missed forced checkmate")
            if "x" in correct_move:
                blindspots.append("missed a capture opportunity")
            if "+" in correct_move or "#" in correct_move:
                blindspots.append("missed a checking move")
            if not blindspots:
                blindspots.append("alternative move selection")

            return {
                "performance_summary": (
                    f"Not quite! You played {user_move}, but the best move was "
                    f"{correct_move}. Take a closer look at the position — "
                    f"there's a stronger continuation available."
                ),
                "accuracy_delta": -1,
                "tactical_blindspots": blindspots,
                "explanation": (
                    f"The correct move {correct_move} is stronger because it creates "
                    f"a forcing threat that the opponent cannot adequately answer."
                ),
                "correct_move": correct_move,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 3 — The Director
# ═══════════════════════════════════════════════════════════════════════════════

# Difficulty progression table
DIFFICULTY_LEVELS = [
    {
        "level": 1,
        "name": "Mate in 3",
        "category": "checkmate",
        "difficulty_key": "mate_in_3",
        "description": "Find the correct 3-move checkmate sequence.",
    }
]

# Number of consecutive correct answers required to level up
STREAK_TO_LEVEL_UP = 3


class DirectorAgent:
    """
    Manages the user's progression through difficulty levels.
    Consumes the Analyst's JSON output to decide whether to promote,
    retain, or adjust the user's training focus.
    """

    SYSTEM_PROMPT = """You are a chess coaching director. Based on the student's
performance data, decide the appropriate next difficulty and provide brief
coaching advice.

Return ONLY a JSON object:
{
  "coaching_notes": "<1-2 sentence advice>",
  "focus_areas": ["<area1>", "<area2>"]
}"""

    @staticmethod
    def create_initial_state() -> dict:
        """Return a fresh user state dictionary."""
        return {
            "level": 1,
            "total_puzzles": 0,
            "correct": 0,
            "wrong": 0,
            "streak": 0,
            "best_streak": 0,
            "blindspots": [],
            "history": [],
            "coaching_notes": "Welcome! Let's start with some checkmate puzzles.",
        }

    @staticmethod
    def get_level_info(user_state: dict) -> dict:
        """Return the DIFFICULTY_LEVELS entry for the user's current level."""
        idx = min(user_state["level"] - 1, len(DIFFICULTY_LEVELS) - 1)
        return dict(DIFFICULTY_LEVELS[idx])

    def load_session_profile(self) -> dict:
        profile_path = "user_session_profile.json"
        if os.path.exists(profile_path):
            with open(profile_path, "r") as f:
                return json.load(f)
        return {
            "current_elo_rating": 800,
            "streak_count": 0,
            "historical_blindspots": [],
            "session_notes": "User is starting their journey."
        }

    def save_session_profile(self, profile: dict) -> None:
        profile_path = "user_session_profile.json"
        with open(profile_path, "w") as f:
            json.dump(profile, f, indent=2)

    def update_state(self, user_state: dict, analysis: dict) -> dict:
        """
        Mutate and return *user_state* based on the analyst's *analysis*.
        Handles levelling up, streak tracking, and blindspot accumulation.
        """
        delta = analysis.get("accuracy_delta", 0)
        user_state["total_puzzles"] += 1
        
        profile = self.load_session_profile()

        if delta > 0:
            # ── Correct answer ──
            user_state["correct"] += 1
            user_state["streak"] += 1
            profile["streak_count"] += 1
            profile["current_elo_rating"] += 10
            user_state["best_streak"] = max(
                user_state["best_streak"], user_state["streak"]
            )

            if (
                user_state["streak"] >= STREAK_TO_LEVEL_UP
                and user_state["level"] < len(DIFFICULTY_LEVELS)
            ):
                user_state["level"] += 1
                user_state["streak"] = 0
                new_level = self.get_level_info(user_state)
                user_state["coaching_notes"] = (
                    f"🎉 Level up! You've advanced to **{new_level['name']}**. "
                    f"{new_level['description']}"
                )
            else:
                remaining = STREAK_TO_LEVEL_UP - user_state["streak"]
                user_state["coaching_notes"] = (
                    f"Great job! {remaining} more correct answer{'s' if remaining != 1 else ''} "
                    f"to advance to the next level."
                )
        else:
            # ── Incorrect answer ──
            user_state["wrong"] += 1
            user_state["streak"] = 0
            profile["streak_count"] = 0
            profile["current_elo_rating"] = max(100, profile["current_elo_rating"] - 10)

            # Record blindspots (keep the last 20)
            new_blindspots = analysis.get("tactical_blindspots", [])
            if new_blindspots:
                profile["historical_blindspots"].extend(new_blindspots)
                
            user_state["blindspots"] = (
                user_state["blindspots"] + new_blindspots
            )[-20:]

            current_level = self.get_level_info(user_state)
            focus = ", ".join(new_blindspots) if new_blindspots else "general pattern recognition"
            user_state["coaching_notes"] = (
                f"Keep practising **{current_level['name']}** puzzles. "
                f"Focus on: {focus}."
            )

        self.save_session_profile(profile)

        # Append to history (keep last 50)
        user_state["history"] = (
            user_state["history"]
            + [
                {
                    "delta": delta,
                    "blindspots": analysis.get("tactical_blindspots", []),
                    "level": user_state["level"],
                }
            ]
        )[-50:]

        # Optionally enrich coaching_notes via LLM
        self._enrich_coaching_notes(user_state, analysis)

        return user_state

    def _enrich_coaching_notes(self, user_state: dict, analysis: dict) -> None:
        """Use the LLM to add personalised coaching flavour (non-critical)."""
        if not _llm_available():
            return
        try:
            user_msg = (
                f"Level: {user_state['level']}, "
                f"Streak: {user_state['streak']}, "
                f"Recent blindspots: {user_state['blindspots'][-5:]}, "
                f"Latest analysis: {json.dumps(analysis)}"
            )
            resp = _client.chat.completions.create(  # type: ignore[union-attr]
                model=_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            data = _safe_json_parse(resp.choices[0].message.content or "")
            if data and "coaching_notes" in data:
                user_state["coaching_notes"] = data["coaching_notes"]
        except Exception as exc:
            logger.debug("Director LLM enrichment skipped: %s", exc)
