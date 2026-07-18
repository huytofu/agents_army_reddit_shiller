"""One-shot: convert identity YAMLs from preferred_subreddits to X search fields."""

from pathlib import Path

import yaml

OVERRIDES = {
    "maya_habits": {
        "search_queries": [
            "habit building",
            "morning routine consistency",
            "study habits productivity",
        ],
        "hashtags": ["habits", "productivity", "selfimprovement"],
        "seed_accounts": ["JamesClear", "calnewport"],
    },
    "jordan_stoic": {
        "search_queries": ["stoicism daily practice", "emotional regulation", "memento mori"],
        "hashtags": ["Stoicism", "philosophy", "mindset"],
        "seed_accounts": ["dailystoic", "RyanHoliday"],
    },
    "riley_blog": {
        "search_queries": ["personal growth blog", "life lessons reflection", "self discovery"],
        "hashtags": ["personalgrowth", "reflection", "writing"],
        "seed_accounts": [],
    },
    "alex_night_owl": {
        "search_queries": ["night owl productivity", "sleep schedule struggle", "late night focus"],
        "hashtags": ["nightowl", "sleep", "productivity"],
        "seed_accounts": [],
    },
    "sam_nofap": {
        "search_queries": [
            "habit replacement addiction recovery",
            "urge surfing",
            "dopamine detox tips",
        ],
        "hashtags": ["nofap", "selfdiscipline", "recovery"],
        "seed_accounts": [],
    },
    "priya_busy_parent": {
        "search_queries": ["busy parent routines", "working parent habits", "family time balance"],
        "hashtags": ["parenting", "routines", "worklifebalance"],
        "seed_accounts": [],
    },
    "chris_data_nerd": {
        "search_queries": ["habit tracking data", "quantified self", "streak analytics"],
        "hashtags": ["quantifiedself", "data", "habits"],
        "seed_accounts": [],
    },
    "lee_minimalist": {
        "search_queries": ["minimalist habits", "simple living routines", "less but better"],
        "hashtags": ["minimalism", "simpleliving", "habits"],
        "seed_accounts": [],
    },
    "taylor_community": {
        "search_queries": ["accountability community", "habit buddies", "shared goals"],
        "hashtags": ["accountability", "community", "goals"],
        "seed_accounts": [],
    },
    "casey_relationships": {
        "search_queries": [
            "healthy relationships advice",
            "communication in dating",
            "attachment styles",
        ],
        "hashtags": ["relationships", "dating", "growth"],
        "seed_accounts": [],
    },
    "avery_love": {
        "search_queries": ["love and self worth", "romantic growth", "dating with intention"],
        "hashtags": ["love", "selfworth", "dating"],
        "seed_accounts": [],
    },
    "devon_purpose": {
        "search_queries": ["finding purpose", "career meaning", "ikigai"],
        "hashtags": ["purpose", "meaning", "career"],
        "seed_accounts": [],
    },
    "harper_philosophy": {
        "search_queries": ["practical philosophy", "ethics everyday life", "existential questions"],
        "hashtags": ["philosophy", "ethics", "thinking"],
        "seed_accounts": [],
    },
    "morgan_blog": {
        "search_queries": ["creative writing tips", "blogger lifestyle", "storytelling craft"],
        "hashtags": ["writing", "blogging", "creativity"],
        "seed_accounts": [],
    },
    "nova_inspiration": {
        "search_queries": [
            "daily inspiration quotes",
            "motivation without hustle",
            "encouragement",
        ],
        "hashtags": ["inspiration", "motivation", "mindfulness"],
        "seed_accounts": [],
    },
    "elliot_reflection": {
        "search_queries": ["journaling reflections", "evening review habit", "mindful reflection"],
        "hashtags": ["journaling", "reflection", "mindfulness"],
        "seed_accounts": [],
    },
}


def main() -> None:
    ident_dir = Path(__file__).resolve().parent.parent / "x_manager" / "identities"
    for path in sorted(ident_dir.glob("*.yaml")):
        if path.name == "activation.yaml":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        iid = data.get("id", path.stem)
        ov = OVERRIDES.get(iid)
        if not ov:
            subs = data.get("preferred_subreddits") or []
            ov = {
                "search_queries": [str(s).replace("_", " ") for s in subs]
                or ["self improvement"],
                "hashtags": ["selfimprovement"],
                "seed_accounts": [],
            }
        data.pop("preferred_subreddits", None)
        data["search_queries"] = ov["search_queries"]
        data["hashtags"] = ov["hashtags"]
        data["seed_accounts"] = ov["seed_accounts"]
        path.write_text(
            yaml.dump(data, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        print("updated", path.name)


if __name__ == "__main__":
    main()
