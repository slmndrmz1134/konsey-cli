"""Cross-platform tests for council.py (stdlib unittest; no agent CLIs needed).

Run: python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import council  # noqa: E402

PY = sys.executable


class ParseSpecTest(unittest.TestCase):
    def test_backend_model_effort(self):
        self.assertEqual(council.parse_spec("codex:gpt-6.1-sol@xhigh"),
                         ("codex", "gpt-6.1-sol", "xhigh"))
        self.assertEqual(council.parse_spec("opencode:opencode/glm-5.3-flash-free@max"),
                         ("opencode", "opencode/glm-5.3-flash-free", "max"))
        self.assertEqual(council.parse_spec("agy:gemini-4-argon-high"),
                         ("agy", "gemini-4-argon-high", None))


class AggregateTest(unittest.TestCase):
    def test_mean_rank_and_last_ranking_line_wins(self):
        r1 = council.Result(spec="x", role="reviewer",
                            text="I first thought FINAL RANKING: C, B, A\n...\nFINAL RANKING: A, B, C")
        r2 = council.Result(spec="y", role="reviewer", text="FINAL RANKING: B > A > C")
        r3 = council.Result(spec="z", role="reviewer", error="boom")
        ranking = council.aggregate([r1, r2, r3], ["A", "B", "C"])
        self.assertEqual(ranking, {"A": 1.5, "B": 1.5, "C": 3.0})

    def test_self_votes_are_dropped(self):
        # reviewer "x" wrote answer A and ranks it first; that vote must not count
        r1 = council.Result(spec="x", role="reviewer", text="FINAL RANKING: A, B, C")
        r2 = council.Result(spec="y", role="reviewer", text="FINAL RANKING: B, C, A")
        ranking = council.aggregate([r1, r2], ["A", "B", "C"], {"A": "x", "B": "y", "C": "z"})
        # x ranks B, C (A removed) -> B=1, C=2; y ranks C, A (B removed) -> C=1, A=2
        self.assertEqual(ranking, {"A": 2.0, "B": 1.0, "C": 1.5})


class RetryFallbackTest(unittest.TestCase):
    def test_empty_answer_is_retried_then_fallback_used(self):
        calls = []

        def flaky(model, effort, prompt, scratch, timeout):
            calls.append(model)
            if model == "bad":
                return ""  # empty answer, as agy sometimes returns
            return "a fallback answer that is long enough to count as real"

        with mock.patch.dict(council.BACKENDS, {"fake": flaky}):
            r = council._call("fake:bad", "member", "q", 60, fallback="fake:good", retries=1)
        self.assertEqual(calls, ["bad", "bad", "good"])
        self.assertEqual(r.spec, "fake:good")
        self.assertIsNone(r.error)
        self.assertEqual(len(r.attempts), 2)

    def test_timeout_is_not_retried_on_same_seat(self):
        calls = []

        def slow(model, effort, prompt, scratch, timeout):
            calls.append(model)
            raise TimeoutError("exceeded")

        with mock.patch.dict(council.BACKENDS, {"fake": slow}):
            r = council._call("fake:slow", "member", "q", 60, retries=2)
        self.assertEqual(calls, ["slow"])
        self.assertIn("TimeoutError", r.error)


class CheckTest(unittest.TestCase):
    def test_check_reports_failing_seat(self):
        cfg = {"council": {"reviewers": ["fake:r1"], "boss": "broken:chair"},
               "member": [{"spec": "fake:m1"}, {"spec": "fake:m1"}]}
        with mock.patch.dict(council.BACKENDS, {"fake": fake_backend, "broken": failing_backend}):
            self.assertEqual(council.check(cfg, 60), 1)
            cfg["council"]["boss"] = "none"
            self.assertEqual(council.check(cfg, 60), 0)


class RunHygieneTest(unittest.TestCase):
    def test_utf8_output(self):
        out = council._run([PY, "-c", "print('ğüşçö — 漢字')"], tempfile.mkdtemp(), timeout=60)
        self.assertIn("ğüşçö — 漢字", out)

    def test_secret_env_scrubbed_unless_kept(self):
        code = "import os; print(os.environ.get('FAKE_API_KEY', 'absent'))"
        with mock.patch.dict(os.environ, {"FAKE_API_KEY": "s3cret"}):
            scrubbed = council._run([PY, "-c", code], tempfile.mkdtemp(), timeout=60)
            kept = council._run([PY, "-c", code], tempfile.mkdtemp(), timeout=60,
                                keep_env=("FAKE_API_KEY",))
        self.assertEqual(scrubbed.strip(), "absent")
        self.assertEqual(kept.strip(), "s3cret")

    def test_stdin_prompt_is_delivered(self):
        out = council._run([PY, "-c", "import sys; print(sys.stdin.read().upper())"],
                           tempfile.mkdtemp(), timeout=60, stdin_text="hello council")
        self.assertIn("HELLO COUNCIL", out)

    def test_timeout_kills_whole_process_tree(self):
        # The child spawns a grandchild that would write a marker file after 4 s.
        # A timeout must kill the grandchild too, so the marker never appears.
        work = Path(tempfile.mkdtemp())
        marker = work / "grandchild-survived.txt"
        grandchild = (f"import time, pathlib; time.sleep(4); "
                      f"pathlib.Path({str(marker)!r}).write_text('alive')")
        child = (f"import subprocess, sys, time; "
                 f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); time.sleep(30)")
        t0 = time.time()
        with self.assertRaises(TimeoutError):
            council._run([PY, "-c", child], str(work), timeout=2)
        self.assertLess(time.time() - t0, 15)
        time.sleep(5)
        self.assertFalse(marker.exists(), "grandchild outlived the timeout kill")

    def test_nonzero_exit_raises(self):
        with self.assertRaises(RuntimeError):
            council._run([PY, "-c", "import sys; sys.exit(3)"], tempfile.mkdtemp(), timeout=60)


def fake_backend(model, effort, prompt, scratch, timeout):
    if "You are the chair" in prompt:
        return "# Decision\nThe council recommends option B, with option A as the fallback."
    if "You are a reviewer" in prompt:
        return "Answer review text that is long enough to count.\nFINAL RANKING: A, B"
    return f"Member answer from {model}: a concrete, practical recommendation."


def failing_backend(model, effort, prompt, scratch, timeout):
    raise RuntimeError("simulated quota error")


class OpencodeRetryTest(unittest.TestCase):
    def test_database_locked_is_retried(self):
        calls = []
        event = json.dumps({"type": "text", "part": {"text": "an answer that is long enough to count"}})

        def fake_run(cmd, cwd, timeout, stdin_text=None, keep_env=()):
            calls.append(cmd)
            if len(calls) == 1:
                raise RuntimeError("opencode exited 1: Error: Unexpected error\n\ndatabase is locked")
            return event

        with mock.patch.object(council, "_run", fake_run), mock.patch.object(council.time, "sleep"):
            text = council.run_opencode("opencode/x", "high", "prompt", tempfile.mkdtemp(), 60)
        self.assertEqual(len(calls), 2)
        self.assertIn("long enough", text)

    def test_other_errors_are_not_retried(self):
        with mock.patch.object(council, "_run", side_effect=RuntimeError("boom")) as run:
            with self.assertRaises(RuntimeError):
                council.run_opencode("opencode/x", None, "prompt", tempfile.mkdtemp(), 60)
        self.assertEqual(run.call_count, 1)


class PipelineTest(unittest.TestCase):
    def test_end_to_end_with_fake_backends_and_one_failing_member(self):
        work = Path(tempfile.mkdtemp())
        (work / "q.md").write_text("Which option should we pick?", encoding="utf-8")
        (work / "c.toml").write_text(
            '[council]\nlanguage = "English"\ntimeout_s = 60\n'
            'reviewers = ["fake:r1", "fake:r2"]\nboss = "fake:chair"\n'
            '[[member]]\nspec = "fake:m1"\n[[member]]\nspec = "fake:m2"\n'
            '[[member]]\nspec = "broken:m3"\n', encoding="utf-8")
        out = work / "run"
        argv = ["council.py", "--config", str(work / "c.toml"),
                "--question-file", str(work / "q.md"), "--out", str(out)]
        with mock.patch.dict(council.BACKENDS, {"fake": fake_backend, "broken": failing_backend}), \
                mock.patch.object(sys, "argv", argv):
            council.main()

        self.assertIn("option B", (out / "final.md").read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in (out / "stage1").glob("*.md")), ["A.md", "B.md"])
        run = json.loads((out / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["ranking"], {"A": 1.0, "B": 2.0})
        errors = [m["error"] for m in run["members"] if m["error"]]
        self.assertEqual(len(errors), 1)
        self.assertIn("simulated quota error", errors[0])
        mapping = json.loads((out / "mapping-private.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(mapping[k] for k in ("A", "B")), ["fake:m1", "fake:m2"])


class DiscoveryTest(unittest.TestCase):
    def test_codex_cache_and_agy_listing(self):
        home = Path(tempfile.mkdtemp())
        (home / "models_cache.json").write_text(json.dumps({"models": [
            {"slug": "gpt-x", "display_name": "GPT-X", "visibility": "list",
             "supported_reasoning_levels": [{"effort": "low"}, {"effort": "xhigh"}]},
            {"slug": "hidden", "visibility": "hide"}]}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(home)}):
            self.assertEqual(council._codex_models(),
                             [{"spec": "codex:gpt-x", "name": "GPT-X", "efforts": ["low", "xhigh"]}])
        listing = "Fetching available models...\ngemini-z-high\tGemini Z (High)\n"
        with mock.patch.object(council, "_run", return_value=listing):
            self.assertEqual(council._agy_models()[0]["spec"], "agy:gemini-z-high")

    def test_setup_wizard_writes_a_valid_config(self):
        found = {"codex": [{"spec": "codex:gpt-x", "name": "X", "efforts": ["low", "xhigh"]}],
                 "agy": [{"spec": "agy:gem-high", "name": "G", "efforts": []}],
                 "opencode": "not installed", "claude": "not installed"}
        # language=Türkçe, suggested members, effort default (xhigh), reviewers default,
        # chair = first member, no --check
        answers = iter(["2", "", "", "", "", "2"])
        target = Path(tempfile.mkdtemp()) / "default.toml"
        with mock.patch.object(council, "discover_models", return_value=found),                 mock.patch("builtins.input", lambda _: next(answers)):
            council.setup_wizard(target)
        cfg = council.tomllib.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(cfg["council"]["language"], "Türkçe")
        self.assertEqual([m["spec"] for m in cfg["member"]], ["codex:gpt-x@xhigh", "agy:gem-high"])
        self.assertEqual(cfg["council"]["boss"], "codex:gpt-x@xhigh")
        self.assertEqual(cfg["council"]["boss_fallback"], "agy:gem-high")


if __name__ == "__main__":
    unittest.main()
