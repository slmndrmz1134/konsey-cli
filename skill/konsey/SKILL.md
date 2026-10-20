---
name: konsey
description: Runs a multi-model LLM council (karpathy/llm-council style) over locally installed agent CLIs - Codex, Antigravity, OpenCode, Claude Code - plus NVIDIA API models, with anonymized peer review and a chair synthesis, via konsey-cli. Use when the user asks for a council, debate, second opinions from several models, or personas arguing a strategy or design decision. Not for coding tasks or single-model questions.
---

# Konsey (konsey-cli)

## Steps

1. **Locate the tool.** Use `python3` on macOS/Linux and `python` on Windows. Find `council.py`
   from the konsey-cli clone; ask the user if it is not on disk.
2. **First run: let the user choose the council.** If there is no `default.toml` next to
   `council.py`, do not just run an example config. Its model names belong to the author's
   fleet and may not exist on this user's accounts.
   - Run `python council.py --list-models --json`. It reports, per CLI (`codex`, `agy`,
     `opencode`, `claude`), either "not installed" or the models that account offers with
     their effort levels.
   - Ask the setup as short multiple-choice questions, this-or-that, using the question
     tool if you have one (a few questions per round, the recommended option first).
     Build the options from the listed models only, never from model names you remember.
     1. Language of the answers.
     2. Members: "Suggested: one strong model per provider (<the specs>)" vs "I'll pick".
        If they pick, ask how many (3–5 from different providers is a good default), then
        offer the listed models as options, grouped by provider.
     3. Effort for seats that have levels (suggest `xhigh` or the highest non-`ultra`
        level for the strongest seat, `high` for the others).
     4. Reviewers: "the paid members" vs "no peer review".
     5. Chair: "you (Claude) synthesize" (`boss = "none"`) vs one of the members, plus a
        `boss_fallback` from another provider.
   - A user working in a plain terminal without you can run `python council.py --setup`,
     which asks the same questions with numbered options and writes `default.toml`.
   - Mention that every seat spends the user's own quota for that provider, and that the
     `claude:` backend spends their Claude quota.
   - Write the choices to `default.toml` (gitignored), then run
     `python council.py --config default.toml --check`. Report which seats failed and fix or
     drop them with the user before a real run.
   - On later runs reuse `default.toml` without asking. Ask again only if the user wants to
     change members or `--check` starts failing.
3. **Write the question** to a file. Put shared background in a separate context file.
   Context is inlined into every prompt, so keep it focused.
4. **Pick the config for this question.**
   - Use `default.toml` for a general council.
   - For personas, copy it next to the question and give each `[[member]]` a `role`. Put the
     most important persona on the strongest model.
   - Set `language` to the user's language.
   - **Documents members should read:** pick the files this question actually needs (the
     paper, the two scripts in question, the result files) and pass each with `--file`
     (globs allowed, e.g. `--file "results/*.json"`), plus `--root <project>` to keep the
     folder layout. Only those files are copied; every prompt lists them with their paths,
     and all backends can open them. Do not hand over a whole project; tell the user which
     files you chose. Use `--context-file` for a short brief everyone must see inline.
   - `workspace = "<dir>"` in the config copies a whole folder instead; `--file` overrides it.
5. **Tell the user it will take a while.** A run takes 5–30 min. Then run it in the background
   with a long timeout:
   ```
   python council.py --config <toml> --question-file <q.md> [--context-file <ctx.md>]        [--root <project> --file <path> ...] --out <dir>
   ```
   - `--no-review` skips peer ranking.
   - `--boss none` skips synthesis, for when you will synthesize yourself.
6. **Read the outputs.**
   - `final.md` is the chair's answer. Its sections are: decision, agreements,
     disagreements, unique findings, plan, verify list, and decisions left to the human.
   - `stage1/*.md` are the anonymized answers; `stage2/review-*.md` are the reviews.
   - `run.json` holds the ranking, errors and fallbacks used. The ranking already excludes
     a reviewer's vote on its own model's answer.
   - `mapping-private.json` records who wrote what. Read it only after judging.
7. **Report to the user:**
   - The ranking.
   - The decision and the key disagreements.
   - Findings raised by only one member. These are often the most valuable; say whether
     each was checked.
   - Claims marked "verify".
   - Which seats failed or ran on a fallback.

## Gotchas

- **Rate limits and empty answers:** The tool retries once and then tries the seat's
  `fallback`. If a seat keeps failing, swap it for another backend and tell the user.
- **Secrets:** Never put secrets in the question or context. They go to every member's
  provider.
