# AI log — what the AI got wrong and how we caught it

Team: ____________________    Members: ____________________

Add a row every time an AI answer was wrong, misleading or incomplete. Three good rows is the target. This is part of your score (see `docs/rubric.md`).

| # | Lab | What we asked | What the AI got wrong | How we caught it | Fix |
|---|-----|---------------|-----------------------|------------------|-----|
| 1 | 1A  | age_factor    | `<=` 25 boundary check | boundary test 25/MOTOR returned 1.2 instead of 1.0 | Changed to `< 25` |
| 2 | 1A  | add_on_factor | Multiplied loadings (`*=`) | Read docstring rule stating each adds | Changed to `factor += available[c]` |
| 3 | 1C  | quotes route  | Used non-existent `Quote.status` | Code review against `models.py` schema | Filtered with `q.policy is None` |

