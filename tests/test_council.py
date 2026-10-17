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


if __name__ == "__main__":
    unittest.main()
