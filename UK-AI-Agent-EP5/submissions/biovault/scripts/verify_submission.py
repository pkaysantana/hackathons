from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

FORBIDDEN_LEGACY_TERMS = (
    "SM" + "E",
    "pay" + "roll",
    "sal" + "ary",
    "market" + "ing",
    "camp" + "aign",
    "vend" + "or",
    "q" + "3_growth",
    "growth" + "_margin",
    "Q" + "3",
)

EXECUTABLE_MODEL_PATTERNS = (
    "open" + "ai",
    "anth" + "ropic",
    "lang" + "chain",
    "llama" + "_index",
    "chat" + ".completions",
    "responses" + ".create",
    "model" + ".generate",
    "LLM" + "Chain",
    "Open" + "AI(",
)

DANGEROUS_FORBIDDEN_PATTERNS = (
    ".env",
    "uv.lock",
    "*.db",
    "*.sqlite",
    "*.docx",
    "*.pem",
    "*.key",
    "id_rsa",
    "*private*key*",
)

LOCAL_CACHE_WARNING_NAMES = (
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".uv-cache",
    ".uv-python",
)

TRACKED_FORBIDDEN_PATTERNS = (
    ".venv/*",
    "*/.venv/*",
    "node_modules/*",
    "*/node_modules/*",
    "dist/*",
    "*/dist/*",
    "__pycache__/*",
    "*/__pycache__/*",
    ".pytest_cache/*",
    "*/.pytest_cache/*",
    ".uv-cache/*",
    "*/.uv-cache/*",
    ".uv-python/*",
    "*/.uv-python/*",
    ".env",
    "*/.env",
    "uv.lock",
    "*/uv.lock",
    "*.db",
    "*.docx",
)

TEXT_SCAN_ROOTS = (
    ROOT / "README.md",
    ROOT / "docs",
    FRONTEND_DIR / "src",
    BACKEND_DIR / "app",
    BACKEND_DIR / "tests",
    ROOT / "scripts",
)

EXECUTABLE_SCAN_ROOTS = (
    BACKEND_DIR / "app",
    BACKEND_DIR / "tests",
    ROOT / "scripts",
)

DEPENDENCY_MANIFESTS = (
    FRONTEND_DIR / "package.json",
    FRONTEND_DIR / "package-lock.json",
    BACKEND_DIR / "requirements.txt",
    BACKEND_DIR / "requirements-dev.txt",
    BACKEND_DIR / "pyproject.toml",
)

CLOSED_MODEL_DEPENDENCIES = (
    "open" + "ai",
    "anth" + "ropic",
    "lang" + "chain",
    "llama" + "_index",
    "google-generative",
    "gemini",
    "cohere",
    "bedrock",
    "vertex",
    "azure-ai",
    "xai",
    "grok",
)


class Reporter:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def pass_(self, message: str) -> None:
        print(f"PASS {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"FAIL {message}")


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yml",
        ".yaml",
    }


def iter_files(paths: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    ignored_dirs = {
        ".git",
        "node_modules",
        ".venv",
        ".uv-cache",
        ".uv-python",
        "dist",
        "__pycache__",
        ".pytest_cache",
    }
    for start in paths:
        if not start.exists():
            continue
        if start.is_file():
            if is_text_candidate(start):
                files.append(start)
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = [d for d in dirnames if d not in ignored_dirs]
            for filename in filenames:
                path = Path(dirpath) / filename
                if is_text_candidate(path):
                    files.append(path)
    return sorted(files)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def matches_any(path_text: str, patterns: tuple[str, ...]) -> bool:
    normalized = path_text.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def run_command(command: list[str], cwd: Path, reporter: Reporter, label: str, env: dict[str, str] | None = None) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        reporter.fail(f"{label} unavailable: {exc}")
        return

    if completed.returncode == 0:
        reporter.pass_(label)
        return

    output = completed.stdout.strip()
    if output:
        print(output)
    reporter.fail(f"{label} failed with exit code {completed.returncode}")


def git_tracked_files(reporter: Reporter) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        reporter.warn("git not available; tracked artifact check skipped")
        return []

    if completed.returncode != 0:
        reporter.warn(f"git ls-files failed; tracked artifact check skipped: {completed.stderr.strip()}")
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def check_dangerous_files(reporter: Reporter) -> None:
    dangerous: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != ".git" and d not in LOCAL_CACHE_WARNING_NAMES]
        for dirname in dirnames:
            path = Path(dirpath) / dirname
            if matches_any(rel(path), DANGEROUS_FORBIDDEN_PATTERNS):
                dangerous.append(rel(path))
        for filename in filenames:
            path = Path(dirpath) / filename
            if matches_any(rel(path), DANGEROUS_FORBIDDEN_PATTERNS):
                dangerous.append(rel(path))

    if dangerous:
        reporter.fail("dangerous local files present: " + ", ".join(sorted(dangerous)))
    else:
        reporter.pass_("dangerous local file hygiene")

    tracked = git_tracked_files(reporter)
    tracked_bad = [p for p in tracked if matches_any(p, TRACKED_FORBIDDEN_PATTERNS)]
    if tracked_bad:
        reporter.fail("forbidden tracked artifacts present: " + ", ".join(sorted(tracked_bad)))
    else:
        reporter.pass_("forbidden tracked artifact hygiene")


def check_local_generated_warnings(reporter: Reporter) -> None:
    tracked = set(git_tracked_files(reporter))
    warnings: list[str] = []
    for dirpath, dirnames, _filenames in os.walk(ROOT):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for dirname in list(dirnames):
            if dirname in LOCAL_CACHE_WARNING_NAMES:
                path = Path(dirpath) / dirname
                relative = rel(path)
                if not any(p == relative or p.startswith(relative.rstrip("/") + "/") for p in tracked):
                    warnings.append(relative)
                dirnames.remove(dirname)

    if warnings:
        reporter.warn("local generated folders present but untracked: " + ", ".join(sorted(set(warnings))))
    else:
        reporter.pass_("no untracked local generated folders found")


def check_forbidden_legacy_terms(reporter: Reporter) -> None:
    hits: list[str] = []
    for path in iter_files(TEXT_SCAN_ROOTS):
        text = read_text(path)
        for term in FORBIDDEN_LEGACY_TERMS:
            if term in text:
                hits.append(f"{rel(path)}:{term}")
    if hits:
        reporter.fail("forbidden legacy vocabulary found: " + ", ".join(hits))
    else:
        reporter.pass_("forbidden legacy vocabulary scan")


def check_executable_model_patterns(reporter: Reporter) -> None:
    hits: list[str] = []
    for path in iter_files(EXECUTABLE_SCAN_ROOTS):
        text = read_text(path).lower()
        for pattern in EXECUTABLE_MODEL_PATTERNS:
            if pattern.lower() in text:
                hits.append(f"{rel(path)}:{pattern}")
    if hits:
        reporter.fail("model/LLM pattern found in executable backend/scripts: " + ", ".join(hits))
    else:
        reporter.pass_("executable model/LLM permission-path scan")


def check_closed_model_dependencies(reporter: Reporter) -> None:
    hits: list[str] = []
    for path in DEPENDENCY_MANIFESTS:
        if not path.exists():
            continue
        text = read_text(path).lower()
        for dep in CLOSED_MODEL_DEPENDENCIES:
            if re.search(rf"(^|[\"'@/\s,=:_-]){re.escape(dep)}($|[\"'\s,=:_-])", text):
                hits.append(f"{rel(path)}:{dep}")
    if hits:
        reporter.fail("closed-model dependency markers found: " + ", ".join(hits))
    else:
        reporter.pass_("closed-model dependency scan")


def check_required_terms(reporter: Reporter) -> None:
    readme = ROOT / "README.md"
    spec = ROOT / "docs" / "JUDGE_SPEC.md"
    if not readme.exists():
        reporter.fail("README.md missing")
        return
    if not spec.exists():
        reporter.fail("docs/JUDGE_SPEC.md missing")
        return

    readme_text = read_text(readme)
    combined = readme_text + "\n" + read_text(spec)

    identity_terms = ("BioVault", "Phase II", "CRO", "adverse-event", "source-lineage", "audit", "0 model tokens")
    missing_identity = [term for term in identity_terms if term not in readme_text]
    if missing_identity:
        reporter.fail("README missing BioVault identity terms: " + ", ".join(missing_identity))
    else:
        reporter.pass_("README BioVault identity terms")

    honest_terms = (
        "prototype",
        "not production security",
        "not clinical decision support",
        "simulated ACL/revocation",
        "not full Hirebase integration",
    )
    combined_lower = combined.lower()
    missing_honest = [term for term in honest_terms if term.lower() not in combined_lower]
    if missing_honest:
        reporter.fail("missing honest-scope wording: " + ", ".join(missing_honest))
    else:
        reporter.pass_("honest-scope wording")


def check_spec_semantics(reporter: Reporter) -> None:
    spec = ROOT / "docs" / "JUDGE_SPEC.md"
    if not spec.exists():
        reporter.fail("docs/JUDGE_SPEC.md missing")
        return

    text = read_text(spec)
    required = (
        "target read grant plus read grants for every included transitive source",
        "Redacted/declassified derivatives are explicit governed exceptions",
        "attestation/source hashes",
        "Denied reads and `/query` calls return no plaintext/context",
        "not production security",
        "not clinical decision support",
        "not real external IAM sync",
        "not production load test",
    )
    missing = [phrase for phrase in required if phrase not in text]
    if missing:
        reporter.fail("Judge Spec missing required semantics: " + ", ".join(missing))
    else:
        reporter.pass_("Judge Spec source-lineage, exception, and scope semantics")

    bad_claims = (
        r"(?<!not )production security",
        r"(?<!not )clinical decision support",
        r"production-ready",
        r"production grade",
        r"(?<!not )real external IAM sync",
        r"(?<!not )production load test",
    )
    bad_hits: list[str] = []
    for pattern in bad_claims:
        if re.search(pattern, text, flags=re.IGNORECASE):
            bad_hits.append(pattern)
    if bad_hits:
        reporter.fail("possible overclaiming in Judge Spec: " + ", ".join(bad_hits))
    else:
        reporter.pass_("Judge Spec overclaiming scan")


def check_backend_tests(reporter: Reporter) -> None:
    if not BACKEND_DIR.exists():
        reporter.fail("backend directory missing")
        return
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    before = len(reporter.failures)
    run_command(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        BACKEND_DIR,
        reporter,
        "backend pytest",
        env=env,
    )
    if len(reporter.failures) > before:
        print("Install backend requirements, then run py -3 -m pytest -q from backend.")


def check_frontend_build(reporter: Reporter) -> None:
    if not FRONTEND_DIR.exists():
        reporter.fail("frontend directory missing")
        return
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm") or shutil.which("npm")
    if not npm:
        reporter.fail("frontend build unavailable: npm not found. Install frontend dependencies, then run npm run build from frontend.")
        return
    with tempfile.TemporaryDirectory(prefix="biovault_frontend_build_") as tmp:
        out_dir = str(Path(tmp) / "dist")
        run_command([npm, "run", "build", "--", "--outDir", out_dir], FRONTEND_DIR, reporter, "frontend build")


def main() -> int:
    reporter = Reporter()
    print(f"BioVault submission verification: {ROOT}")
    print()

    check_dangerous_files(reporter)
    check_local_generated_warnings(reporter)
    check_forbidden_legacy_terms(reporter)
    check_executable_model_patterns(reporter)
    check_closed_model_dependencies(reporter)
    check_required_terms(reporter)
    check_spec_semantics(reporter)
    check_backend_tests(reporter)
    check_frontend_build(reporter)

    print()
    if reporter.warnings:
        print("WARNINGS:")
        for warning in reporter.warnings:
            print(f"- {warning}")

    if reporter.failures:
        print("FAILURES:")
        for failure in reporter.failures:
            print(f"- {failure}")
        print("SAFE TO SUBMIT: no")
        return 1

    print("SAFE TO SUBMIT: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
