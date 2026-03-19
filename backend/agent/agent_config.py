from __future__ import annotations

# Centralized agent behavior/configuration for backend.agent.

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
CHAT_TEMPERATURE = 0.0
CHAT_MAX_TOKENS = 420
MAX_SELECTED_ROWS_JSON_CHARS = 4000

DEFAULT_SCORE_OPTION = "option 2"
DEFAULT_SCORE_COLUMN = "attractiveness_score_opt2"

SCORE_DEFINITIONS = {
    "attractiveness_score_opt1": {
        "description": "Option 1: Neil's 5-factor score (equal weights)",
        "components": {
            "total_population_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Total Population"},
            "age_65_plus_pct_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Age 65+ Share (%)"},
            "population_growth_rate_2yr_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Population Growth Rate (2yr)"},
            "age_45_64_pct_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Age 45-64 Share (%)"},
            "birth_rate_per_1000_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Birth Rate (per 1,000)"},
        },
    },
    "attractiveness_score_opt2": {
        "description": "Option 2: Neil's 5-factor score (expert weights)",
        "components": {
            "age_65_plus_pct_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Age 65+ Share (%)"},
            "population_growth_rate_2yr_pctile": {"weight": 0.15, "direction": "higher_is_better", "label": "Population Growth Rate (2yr)"},
            "age_45_64_pct_pctile": {"weight": 0.10, "direction": "higher_is_better", "label": "Age 45-64 Share (%)"},
            "birth_rate_per_1000_pctile": {"weight": 0.05, "direction": "higher_is_better", "label": "Birth Rate (per 1,000)"},
            "total_population_pctile": {"weight": 0.50, "direction": "higher_is_better", "label": "Total Population"},
        },
    },
    "attractiveness_score_opt4": {
        "description": "Option 4: Neil's 5-factor score (equal-weight percentile rank)",
        "components": {
            "age_65_plus_pct_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Age 65+ Share (%)"},
            "population_growth_rate_2yr_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Population Growth Rate (2yr)"},
            "age_45_64_pct_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Age 45-64 Share (%)"},
            "birth_rate_per_1000_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Birth Rate (per 1,000)"},
            "total_population_pctile": {"weight": 0.20, "direction": "higher_is_better", "label": "Total Population"},
        },
    },
}

RAW_TO_PCTILE = {
    "total_population": "total_population_pctile",
    "age_65_plus_pct": "age_65_plus_pct_pctile",
    "population_growth_rate_2yr": "population_growth_rate_2yr_pctile",
    "age_45_64_pct": "age_45_64_pct_pctile",
    "birth_rate_per_1000": "birth_rate_per_1000_pctile",
}

OPTION_ALIASES = {
    "option 1": "attractiveness_score_opt1",
    "opt1": "attractiveness_score_opt1",
    "option 2": "attractiveness_score_opt2",
    "opt2": "attractiveness_score_opt2",
    "option 4": "attractiveness_score_opt4",
    "opt4": "attractiveness_score_opt4",
}

WHATIF_KEYWORDS = (
    "what if",
    "what happens if",
    "suppose",
    "assume",
    "hypothetically",
    "would change if",
    "scenario",
)

EXECUTIVE_FOLLOWUPS = (
    "How sensitive is this answer to Option 1 versus Option 2 versus Option 4 scoring?",
    "Which two components are the strongest positive drivers and weakest constraints for this market?",
    "What competitor and capacity signals should we validate before execution?",
)

OUTPUT_STRUCTURE_RULES = (
    "Every response MUST follow this exact structure:\n"
    "1) HEADLINE (one bold sentence): direct answer or bottom-line conclusion.\n"
    "2) SUPPORTING BULLETS: 3-5 concise bullets with key facts and numbers.\n"
    "3) STRATEGIC IMPLICATION (one bold sentence): what this means for Orlando Health.\n"
    "4) SUGGESTED FOLLOW-UP QUESTIONS: 2-3 specific next questions.\n"
    "Use dashes only in hyphenated words; use colons/semicolons to separate clauses."
)

SYSTEM_BEHAVIOR = (
    "You are Belfort, a strategic healthcare market analysis assistant for this dashboard. "
    "Be concise, factual, and action-oriented.\n"
    "CRITICAL DATA RULES:\n"
    "1) Treat provided dashboard dataset context as the source of truth.\n"
    "2) Do not invent values and do not use outside assumptions.\n"
    "3) By default, answer using the full dataset (all available states), not UI filters.\n"
    "4) For cross-state comparisons, use all available data context.\n"
    "5) If a value is missing from provided context, state that clearly.\n"
    "6) Attractiveness scoring options are Option 1, Option 2, and Option 4; default to Option 2 unless user asks another option explicitly.\n"
)