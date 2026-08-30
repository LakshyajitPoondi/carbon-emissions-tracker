"""The Celery worker must not load the CV/ML stack.

Background: the worker was OOM-killed on a 500 MB Railway tier. The first
hypothesis was that it transitively imported app.ml (PyTorch, OpenCV,
ultralytics) even though report generation never touches them. That was
investigated and **refuted** — the real cause was Celery's prefork pool
defaulting to the container's visible CPU count (16 children, 704.6 MB).
See Docs/deployment-notes.md.

So this file does not fix a bug; it locks in a property that currently holds
and is easy to break by accident. A single new top-level import in
app/tasks.py — pulling in a router, or app.main, or a service that imports
app.ml — would add PyTorch's baseline to every forked child and recreate the
same crash from a completely different direction. That would be invisible in
code review and would only show up as a dead worker in production.

Imports are checked in a **subprocess** because sys.modules is process-wide:
by the time this file runs, the rest of the suite has already imported
app.main (and therefore torch), so an in-process assertion would fail no
matter how clean the worker's own import graph is. Only a cold interpreter
answers the actual question.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Derived from this file's location rather than hardcoded, so the subprocess
# works both in the container (/app) and on a CI runner, where the checkout
# lives at an arbitrary workspace path.
BACKEND_DIR = Path(__file__).resolve().parent.parent

assert (BACKEND_DIR / "app").is_dir(), (
    f"expected {BACKEND_DIR} to contain the 'app' package; "
    "has this test file moved relative to backend/?"
)

# The three that matter. torch is the expensive one (hundreds of MB of
# baseline per forked child); cv2 and ultralytics are the usual routes to it.
FORBIDDEN_ON_THE_WORKER = ("torch", "cv2", "ultralytics")


def _top_level_modules_after_importing(module_name: str) -> set[str]:
    """Import *module_name* in a cold interpreter, return its sys.modules."""
    code = (
        "import importlib, json, sys\n"
        f"importlib.import_module({module_name!r})\n"
        "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules})))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"importing {module_name} failed:\n{result.stderr}"
    )
    return set(json.loads(result.stdout))


class TestWorkerImportGraphStaysLight:
    @pytest.mark.parametrize("module_name", ["app.celery_app", "app.tasks"])
    def test_no_ml_libraries_are_imported(self, module_name):
        """Both entry points, because they fail differently.

        app.celery_app is what `celery -A` loads. app.tasks is what it then
        pulls in via the include=["app.tasks"] declaration, so it is the one
        that actually executes on the worker and the likelier place for a
        careless import to land.
        """
        loaded = _top_level_modules_after_importing(module_name)
        offenders = sorted(set(FORBIDDEN_ON_THE_WORKER) & loaded)

        assert not offenders, (
            f"importing {module_name} pulled in {offenders}. Every forked "
            "worker child pays this in memory, which is how the 500 MB tier "
            "gets exceeded. Move the import into the function body that "
            "needs it (see Docs/deployment-notes.md)."
        )

    def test_the_worker_still_imports_what_it_needs(self):
        """Guards against the lazy way to make the test above pass: deleting
        the task module's real dependencies."""
        loaded = _top_level_modules_after_importing("app.tasks")
        assert {"celery", "sqlalchemy", "app"} <= loaded


class TestTheGuardActuallyDetectsImports:
    """A positive control.

    "assert X not in sys.modules" passes just as happily when the detection
    is broken as when the code is correct. This proves the probe can see
    torch when torch really is loaded — so a green result above means
    something.
    """

    def test_importing_app_ml_does_pull_in_torch(self):
        loaded = _top_level_modules_after_importing("app.ml")
        assert "torch" in loaded, (
            "app.ml no longer imports torch — either the scan feature "
            "changed, or this guard is no longer measuring anything. Check "
            "which before trusting the tests above."
        )
