# konsey-cli

*Konsey* is Turkish for *council*, and a nod to the shadowy Konsey of the Turkish TV series *Kurtlar Vadisi*.

> *Loş bir oda. Uzun bir masa. Etrafında yüzü görünmeyen beş üye.*
>
> **Başkan:** Soru masada. Herkes cevabını ayrı yazacak. Kimin ne yazdığını kimse bilmeyecek.
>
> **Üye C:** Cevabım hazır, efendim.
>
> **Başkan:** İsimler kapatıldı. Şimdi birbirinizi puanlayın.
>
> *(Üye A kendi cevabını birinci sıraya yazar. Kimse şaşırmaz.)*
>
> **Başkan:** Herkes kendi cevabını beğenir. O yüzden son sözü Konsey söyler.
>
> **Üye E** *(1800 saniyedir cevap vermiyor)***:** Merhamet edin efendim…
>
> **Başkan:** `taskkill /T /F`.
>
> *(Torunlarıyla birlikte.)*

**Run a [karpathy/llm-council](https://github.com/karpathy/llm-council)-style council across the coding-agent CLIs you already pay for:** Codex, Antigravity (Gemini and Claude), OpenCode (GLM, DeepSeek, any provider) and Claude Code. NVIDIA's API works too.

No OpenRouter key and no per-token API billing. Each member runs headless through its own CLI and your existing subscriptions. One stdlib-only Python file that runs on **Windows**, macOS and Linux.

```
stage 1  members answer independently, in parallel (each with its own persona or lens)
stage 2  reviewers rank the anonymized answers  →  mean rank per answer
stage 3  a chair model synthesizes one decisive answer from answers + reviews
```

## Why

- **Use what you already have.** Every member runs through the CLI and subscription you already use, so there is no API key or per-token billing.
- **Provider-diverse councils.** Models from different labs make different mistakes, so errors are less correlated. Personas make the disagreement explicit.
- **Anonymized review.** Reviewers and the chair see "Answer A/B/C", never model names, so they judge the argument instead of the brand.
- **Hardened subprocess handling:**
  - Every member runs in an empty scratch directory, with a hard timeout.
  - On timeout the whole process tree is killed: `taskkill /T` on Windows, a process-group kill elsewhere.
  - Secret-looking environment variables are removed before a member starts.
  - One failing member never sinks the run, and a failed chair falls back to the best-ranked answer.

## Requirements

- Python 3.11+ (only `tomllib` and the stdlib).
- Any subset of these CLIs, logged in:
  - `codex` (OpenAI Codex CLI)
  - `agy` (Google Antigravity CLI)
  - `opencode`
  - `claude` (Claude Code)
- For `nvidia:` members, `NVIDIA_API_KEY` set in the environment.

## Quick start

```bash
git clone https://github.com/slmndrmz1134/konsey-cli && cd konsey-cli
echo "Should a two-person team build its backend on Supabase or a custom Go API?" > q.md
python council.py --config examples/smoke.toml --question-file q.md --out runs/smoke
cat runs/smoke/final.md
```

Output files:

| Path | Contents |
|---|---|
| `final.md` | The chair's answer |
| `stage1/A.md …` | The anonymized member answers |
| `stage2/review-R*.md` | The reviews |
| `run.json` | Ranking, timings and per-member errors |
| `mapping-private.json` | Which model wrote which answer |

Options:
- `--context-file brief.md` (repeatable) inlines shared background into every prompt.
- `--no-review` skips stage 2.
- `--boss none` skips stage 3, for when your own agent will synthesize.

## Configuration

```toml
[council]
language = "English"          # answers, reviews and synthesis are written in this language
timeout_s = 1800              # hard per-call timeout
reviewers = ["agy:gemini-4-argon-high", "codex:gpt-6.1-sol@xhigh"]
boss = "agy:claude-opus-5-5-high"   # or "none"

[[member]]
spec = "codex:gpt-6.1-sol@xhigh"
role = "Growth strategist and devil's advocate"   # optional; default: precision/breadth/skeptic lenses

[[member]]
spec = "opencode:opencode/glm-5.3-flash-free@max"
```

Model specs have the form `<backend>:<model>[@effort]`:

| Backend | Example | How it runs |
|---|---|---|
| `codex` | `codex:gpt-6.1-sol@xhigh` | `codex exec --sandbox read-only`. The prompt goes on stdin and the answer is read from `-o` (last message). |
| `agy` | `agy:gemini-4-argon-high`, `agy:claude-opus-5-5-high` | `agy --print --output-format json`. Effort is part of the model name. |
| `opencode` | `opencode:opencode/deepseek-v4.1-flash-free@max` | `opencode run --format json`. The prompt is attached with `-f`, and `@effort` becomes `--variant`. |
| `claude` | `claude:claude-opus-5-5` | `claude -p` with tools disallowed |
| `nvidia` | `nvidia:z-ai/glm-5.3` | NVIDIA chat completions API |

Example configs: `examples/smoke.toml` (cheap, low effort), `examples/fleet.toml` (five members and three reviewers), `examples/personas.toml` (stakeholder personas). A personal `default.toml` next to `council.py` is used when present, and it is gitignored.

## Gotchas this tool already handles

- **agy:**
  - It hangs if stdin stays open, so stdin is set to `DEVNULL`.
  - Long prompts passed as argv fail with `Eligibility check failed: UNAVAILABLE (503)`. The prompt is written to a file and agy gets a short pointer to it.
- **opencode:**
  - `-f` is an array flag and swallows the message that follows it, so the message is placed before `-f`.
  - OpenCode resolves `{env:VAR}` provider keys at startup, so `NVIDIA_API_KEY` is passed through even though secret-looking env vars are otherwise removed.
- **Windows:**
  - `os.killpg` doesn't exist, so the process tree is killed with `taskkill /T /F`.
  - npm CLIs are `.cmd` shims, so commands are resolved with `shutil.which()` first.

## Caveats

- **Self-preference.** A reviewer tends to rank the answer its own model wrote higher. Read rankings with that in mind; `mapping-private.json` shows who wrote what.
- **Data exposure.** The question and context go to every member's provider. Never put secrets in a council prompt.
- **Effort settings matter.** The free GLM and DeepSeek members are slower than the others (often 2 minutes or more per call).
- **When to use it.** Councils pay off on judgment-heavy questions such as strategy, design trade-offs and risk reviews, not on simple lookups or plain code generation.

## Claude Code skill

`skill/konsey/SKILL.md` is a [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills) that teaches Claude to run this tool. To install it:

```bash
cp -r skill/konsey ~/.claude/skills/
```

### Basic usage

> **User:** "Run a council on whether we should build our MVP backend on Supabase or a custom Go API."

Claude does four things:
1. Writes the question to a file.
2. Runs `council.py` with `examples/fleet.toml` in the background.
3. Reads `final.md` and the reviews.
4. Reports the chair's decision, the ranking, the main disagreements and the claims to verify.

### Advanced usage

> **User:** "Set up a persona council for our pen-pal app's differentiation: a growth strategist on Codex, a partnerships lead on Opus, a designer on Gemini, and two target users on the free OpenCode models. Write it in Turkish and use our product brief as context."

Claude does three things:
1. Copies `examples/personas.toml` and fills in the roles, with `language = "Türkçe"`.
2. Passes the brief with `--context-file`.
3. Reports the ranking with a self-preference caveat, plus a merged "now / later / never" plan.

## Credits

- The three-stage idea comes from [karpathy/llm-council](https://github.com/karpathy/llm-council).
- The harness design (subprocess hygiene, tolerant extraction, anonymized chair, fallback merge) is adapted from [paldom/llm-council-skills](https://github.com/Paldom/llm-council-skills) (MIT).

See `NOTICE`.

## License

MIT
