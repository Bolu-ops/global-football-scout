"""Natural-language scouting: the LLM only translates a request into structured filters
(REQUIREMENTS §26, §38). The similarity engine produces the results."""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from gfs_core.config import get_settings

SYSTEM = """You translate football scouting requests into a structured query for a statistical
similarity engine. You never rank players yourself and never invent players.

Rules:
- If the request names a player to find look-alikes for, put the name in target_player_name.
- Position words map to canonical codes: GK, CB, LB, RB, LWB, RWB, DM, CM, AM, LW, RW, SS, ST.
  "winger" -> LW and RW; "full-back" -> LB and RB; "number 6"/"holding" -> DM; "number 10" -> AM;
  "striker"/"number 9" -> ST; "centre-back" -> CB.
- "outside the top leagues"/"top five leagues" etc. -> exclude_top_leagues true (the engine already
  excludes the strongest leagues by default; set false only if the user explicitly wants them included).
- Budget constraints (e.g. "under €30M") go into max_value_eur in euros as a number.
- Age constraints go into min_age / max_age.
- Emphasis words map to category weights (0-1): "creative/playmaker" -> passing & attacking up,
  "ball-winner/destroyer" -> defending & duels up, "dribbler" -> possession up, "goalscorer" -> attacking up.
- If something cannot be expressed, put it in unsupported_terms rather than guessing."""


class ParsedScoutingQuery(BaseModel):
    target_player_name: str | None = Field(
        None, description="Player whose profile to match, if any"
    )
    positions: list[
        Literal["GK", "CB", "LB", "RB", "LWB", "RWB", "DM", "CM", "AM", "LW", "RW", "SS", "ST"]
    ] = []
    gender: Literal["male", "female"] | None = None
    min_age: float | None = None
    max_age: float | None = None
    min_minutes: int | None = None
    max_value_eur: float | None = None
    exclude_top_leagues: bool = True
    competition_names: list[str] = Field(
        default_factory=list, description="Restrict to these competitions if named"
    )
    category_weights: dict[str, float] | None = Field(
        None,
        description="Optional emphasis: keys attacking, passing, possession, defending, duels, goalkeeping, usage",
    )
    cheaper_than_target: bool = False
    unsupported_terms: list[str] = Field(default_factory=list)
    interpretation: str = Field(..., description="One sentence restating the query as understood")


def parse_query(text: str) -> ParsedScoutingQuery:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured; natural-language search is disabled"
        )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.parse(
        model=settings.llm_model or "claude-opus-5",
        max_tokens=2048,
        system=SYSTEM,
        messages=[{"role": "user", "content": text}],
        output_format=ParsedScoutingQuery,
    )
    if response.parsed_output is None:
        raise RuntimeError("the language model did not return a structured query")
    return response.parsed_output
