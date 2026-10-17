---
name: konsey
description: Runs a multi-model LLM council (karpathy/llm-council style) over locally installed agent CLIs - Codex, Antigravity, OpenCode, Claude Code - plus NVIDIA API models, with anonymized peer review and a chair synthesis, via konsey-cli. Use when the user asks for a council, debate, second opinions from several models, or personas arguing a strategy or design decision. Not for coding tasks or single-model questions.
---

# Konsey (konsey-cli)

## Steps

1. **Locate the tool.** Use `python3` on macOS/Linux and `python` on Windows. Find `council.py` from the konsey-cli clone; ask the user if it
   is not on disk. Check which CLIs are installed and logged in (`codex`, `agy`,
   `opencode`, `claude`) and only seat members whose CLI exists.
2. **Write the question** to a file. Put shared background in a separate context file.
   Context is inlined into every prompt, so keep it focused.
3. **Pick or write a config.**
   - `examples/fleet.toml` is a general council with lenses.
   - `examples/personas.toml` gives each member a stakeholder persona.
   - `examples/smoke.toml` is a cheap check.
   - Set `language` to the user's language.
   - Put the most important persona on the strongest model.
4. **Run it in the background.** A run takes 5–30 min, so use a long timeout:
   ```
   python council.py --config <toml> --question-file <q.md> [--context-file <ctx.md>] --out <dir>
   ```
   - `--no-review` skips peer ranking.
   - `--boss none` skips synthesis, for when you will synthesize yourself.
5. **Read the outputs.**
   - `final.md` is the chair's answer.
   - `stage1/*.md` are the anonymized answers; `stage2/review-*.md` are the reviews.
   - `run.json` holds the ranking and errors.
   - `mapping-private.json` records who wrote what. Read it only after judging.
6. **Report to the user:**
   - The ranking, with the note that reviewers tend to prefer their own model's answer.
   - The decision, the key disagreements, and claims marked "verify".
   - Which members failed, if any.

## Gotchas

- **Rate limits:** On a quota error (e.g. agy 429), rerun with that member swapped for
  another backend.
- **Secrets:** Never put secrets in the question or context. They go to every member's
  provider.
