#!/usr/bin/env python3
"""deep_audit.py — reproducible prompt-vs-code audit for the Afrakala/AfraPayam project.

Answers one question: for every master prompt ever written, what actually got built,
what got half-built, what exists for no reason, and what was asked for and never done.

Fully static: stdlib only, no network, no API key. Everything it reports is derived from
the working tree plus `git log`, so two runs on the same tree give the same audit.md.

    python deep_audit.py --output audit.md

Design notes:
  * Prompt files are discovered in --prompt-dir (default: repo root, because no prompts/
    directory exists in this project). Only *.md / *.txt / *.prompt are considered.
  * A prompt is linked to code two independent ways: (a) commits whose subject carries its
    version tag, (b) source comments carrying the same tag. Either alone is weak evidence;
    both together is strong.
  * audit.md NEVER contains prompt bodies. Prompts are treated as confidential: only the
    title line, a one-line goal, PART headings, and counts are emitted.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ── configuration ──────────────────────────────────────────────────────────────

PROMPT_EXTS = {".md", ".txt", ".prompt"}
SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx"}

# Directories never worth walking: vendored, generated, or VCS internals.
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache", "venv", ".venv",
    "env", "dist", "build", ".idea", ".vscode", ".mypy_cache", ".ruff_cache",
    ".media", "logs",
}

# Root-level docs that are project documentation, not master prompts.
NON_PROMPT_DOCS = {
    "README.md", "CLAUDE.md", "SYSTEM_DOCUMENTATION.md", "analysis_report.md",
    "project_structure.txt", "NGROK_SERVICE_SETUP.md", "OPEN_TO_LAN.md",
    "MENU_SIDEBAR_RESEARCH.md", "audit.md",
}

STUB_MARKERS = re.compile(r"\b(TODO|FIXME|XXX|HACK|WIP|NotImplementedError)\b")
VERSION_IN_NAME = re.compile(r"^V(\d+)(?:[_.]|$)", re.IGNORECASE)
PART_HEADING = re.compile(r"^#{1,4}\s*(PART\s+[0-9][0-9A-Za-z.]*)\b[ \t]*[—:-]?[ \t]*(.*)$",
                          re.IGNORECASE | re.MULTILINE)
# Imperative lines in a prompt = explicit asks. Used only for counting.
REQUIREMENT_LINE = re.compile(r"^\s*(?:[-*]\s+)?(?:MUST|NEVER|ALWAYS|Do NOT|Implement|Add|Fix|Remove|Ensure)\b",
                              re.IGNORECASE | re.MULTILINE)

BINARY_SNIFF = 4096


# ── small helpers ──────────────────────────────────────────────────────────────

def run_git(repo: Path, *args: str) -> str:
    """Run git and return stdout, or '' if git is unavailable / the command fails."""
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def is_binary(path: Path) -> bool:
    """A NUL byte in the first 4 KiB, or an undecodable head, means 'do not read this'.

    The sniff window almost always lands mid-character in Persian text (2-byte UTF-8), so a
    naive decode of the raw window raises UnicodeDecodeError on perfectly good files. Trim up
    to 3 trailing bytes before deciding — otherwise every Farsi prompt is called 'binary'."""
    try:
        head = path.open("rb").read(BINARY_SNIFF)
    except OSError:
        return True
    if b"\x00" in head:
        return True
    for trim in range(4):                       # 0..3 possible continuation bytes
        candidate = head[:len(head) - trim] if trim else head
        try:
            candidate.decode("utf-8")
            return False
        except UnicodeDecodeError:
            continue
    return True


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def walk_sources(root: Path):
    """Yield every source file under root, skipping vendored/generated trees."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in SOURCE_EXTS:
                yield p


# ── data model ─────────────────────────────────────────────────────────────────

@dataclass
class Prompt:
    path: Path
    name: str
    tag: str | None                       # "V44" etc., or None for untagged prompts
    binary: bool = False
    title: str = ""
    goal: str = ""
    parts: list[tuple[str, str]] = field(default_factory=list)   # (label, short title)
    requirement_count: int = 0
    size: int = 0
    tracked: bool = False

    # filled in by the mapping stage
    commits: list[tuple[str, str]] = field(default_factory=list)  # (sha, subject)
    commit_files: set[str] = field(default_factory=set)
    marker_files: set[str] = field(default_factory=set)
    parts_done: dict[str, bool] = field(default_factory=dict)
    # True when this prompt predates the "V<n> PART <k>:" commit-subject convention, so
    # commit matching is structurally impossible and absence of commits proves nothing.
    pre_convention: bool = False
    sha256: str = ""

    @property
    def status(self) -> str:
        if self.pre_convention:
            # Cannot be verified by commit subject. Code markers are the only evidence.
            return "UNVERIFIABLE" if self.marker_files else "NO TRACE"
        if not self.commits and not self.marker_files:
            return "NOT DONE"
        if self.parts and not all(self.parts_done.values()):
            return "PARTIAL"
        if self.commits and self.marker_files:
            return "COMPLETE"
        return "PARTIAL"


@dataclass
class Finding:
    path: Path
    kind: str
    detail: str
    line: int = 0


# ── stage 1: discover + parse prompts ──────────────────────────────────────────

def discover_prompts(prompt_dir: Path, tracked: set[str], repo: Path) -> list[Prompt]:
    prompts: list[Prompt] = []
    if not prompt_dir.is_dir():
        return prompts

    for path in sorted(prompt_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in PROMPT_EXTS:
            continue
        if path.name in NON_PROMPT_DOCS:
            continue

        m = VERSION_IN_NAME.match(path.name)
        tag = f"V{int(m.group(1))}" if m else None
        rel = path.relative_to(repo).as_posix()
        p = Prompt(path=path, name=path.name, tag=tag,
                   size=path.stat().st_size, tracked=rel in tracked)

        try:
            p.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            p.sha256 = ""

        if is_binary(path):
            p.binary = True                      # name only, per the constraints
            prompts.append(p)
            continue

        text = read_text(path)
        lines = text.splitlines()

        for ln in lines:
            if ln.startswith("# "):
                p.title = ln[2:].strip()
                break
        for ln in lines:
            s = ln.strip()
            if s.startswith("## ") and "PART" not in s.upper():
                p.goal = s[3:].strip()
                break
        if not p.goal:
            for ln in lines:
                s = ln.strip()
                if s and not s.startswith(("#", ">", "-", "*", "|")):
                    p.goal = s
                    break

        for label, rest in PART_HEADING.findall(text):
            label = re.sub(r"\s+", " ", label).strip().upper()
            short = re.sub(r"\s+", " ", rest).strip()
            if len(short) > 80:
                short = short[:77] + "..."
            if label not in [l for l, _ in p.parts]:
                p.parts.append((label, short))

        p.requirement_count = len(REQUIREMENT_LINE.findall(text))
        prompts.append(p)

    return prompts


# ── stage 2: map prompts to commits and to code markers ────────────────────────

def map_commits(repo: Path, prompts: list[Prompt]) -> tuple[int, dict[str, list[tuple[str, str]]]]:
    """Attach commits to prompts by version tag appearing in the commit subject.

    Returns (lowest_tagged_version, all_tagged_commits). The project only adopted the
    "V<n> PART <k>: ..." subject convention partway through its life; every prompt older
    than that cannot be matched this way, and must not be reported as undelivered."""
    raw = run_git(repo, "log", "--all", "--pretty=format:%H%x1f%s")
    entries = []
    for line in raw.splitlines():
        if "\x1f" not in line:
            continue
        sha, subject = line.split("\x1f", 1)
        entries.append((sha, subject))

    by_tag: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for sha, subject in entries:
        m = re.match(r"\s*V(\d+)\b", subject)
        if m:
            by_tag[f"V{int(m.group(1))}"].append((sha, subject))

    lowest = min((int(t[1:]) for t in by_tag), default=0)

    for p in prompts:
        if not p.tag:
            continue
        if int(p.tag[1:]) < lowest:
            p.pre_convention = True
        p.commits = by_tag.get(p.tag, [])
        for sha, _ in p.commits:
            files = run_git(repo, "show", "--pretty=format:", "--name-only", sha)
            p.commit_files.update(f.strip() for f in files.splitlines() if f.strip())
        # A PART counts as done when some commit subject names it.
        subjects = " || ".join(s for _, s in p.commits).upper()
        for label, _ in p.parts:
            p.parts_done[label] = label in subjects

    return lowest, by_tag


def map_markers(repo: Path, prompts: list[Prompt], sources: list[Path]) -> None:
    """Attach source files that carry a prompt's version tag in a comment/docstring."""
    tags = {p.tag for p in prompts if p.tag}
    if not tags:
        return
    pattern = re.compile(r"\b(V(?:%s))\b" % "|".join(
        sorted((t[1:] for t in tags), key=int, reverse=True)))
    hits: dict[str, set[str]] = defaultdict(set)
    for path in sources:
        text = read_text(path)
        if not text:
            continue
        rel = path.relative_to(repo).as_posix()
        for tag in set(pattern.findall(text)):
            hits[tag].add(rel)
    for p in prompts:
        if p.tag:
            p.marker_files = hits.get(p.tag, set())


# ── stage 3: half-done detection ───────────────────────────────────────────────

def find_incomplete(repo: Path, sources: list[Path], tracked: set[str]) -> list[Finding]:
    findings: list[Finding] = []

    for path in sources:
        text = read_text(path)
        if not text:
            continue
        rel_path = path.relative_to(repo)

        for i, line in enumerate(text.splitlines(), 1):
            if STUB_MARKERS.search(line):
                snippet = line.strip()
                if len(snippet) > 120:
                    snippet = snippet[:117] + "..."
                findings.append(Finding(rel_path, "marker", snippet, i))

        if path.suffix.lower() != ".py":
            continue

        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            findings.append(Finding(rel_path, "syntax-error", str(exc), exc.lineno or 0))
            continue

        # Empty bodies: a def whose entire body is pass / ... / a bare docstring.
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [n for n in node.body if not (isinstance(n, ast.Expr)
                                                 and isinstance(n.value, ast.Constant)
                                                 and isinstance(n.value.value, str))]
            def _is_noop(n: ast.stmt) -> bool:
                # `pass`, or a bare `...` expression (ast.Ellipsis is deprecated in 3.12+).
                return isinstance(n, ast.Pass) or (
                    isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                    and n.value.value is Ellipsis)

            if not body or all(_is_noop(n) for n in body):
                findings.append(Finding(rel_path, "empty-body",
                                        f"def {node.name}() has no implementation", node.lineno))

        # Local imports that resolve to nothing, or resolve to an UNTRACKED file.
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            for mod in mods:
                if not mod.startswith("app."):
                    continue
                target = repo / "backend" / Path(*mod.split("."))
                pyfile, pkgfile = target.with_suffix(".py"), target / "__init__.py"
                if pyfile.exists():
                    hit = pyfile
                elif pkgfile.exists():
                    hit = pkgfile
                else:
                    findings.append(Finding(rel_path, "missing-dep",
                                            f"imports {mod} — no such module", node.lineno))
                    continue
                if hit.relative_to(repo).as_posix() not in tracked:
                    findings.append(Finding(rel_path, "untracked-dep",
                                            f"imports {mod} — target file is NOT tracked by git",
                                            node.lineno))

    return findings


# ── stage 4: dead / redundant files ────────────────────────────────────────────

def find_useless(repo: Path, sources: list[Path], prompts: list[Prompt],
                 tracked: set[str]) -> tuple[list[Finding], list[Finding]]:
    """Return (orphan findings, duplicate findings)."""
    referenced: set[str] = set()
    for path in sources:
        text = read_text(path)
        for mod in re.findall(r"from\s+(app\.[\w.]+)\s+import", text):
            referenced.add(mod.split(".")[-1])
        for mod in re.findall(r"import\s+(app\.[\w.]+)", text):
            referenced.add(mod.split(".")[-1])
        for spec in re.findall(r"""from\s+['"]([^'"]+)['"]""", text):
            referenced.add(Path(spec).name.split(".")[0])

    marker_files: set[str] = set()
    for p in prompts:
        marker_files |= p.marker_files
        marker_files |= p.commit_files

    orphans: list[Finding] = []
    for path in sources:
        rel = path.relative_to(repo).as_posix()
        stem = path.stem
        if stem in ("__init__", "conftest", "main", "setup"):
            continue
        if stem.startswith("test_"):
            continue                                   # collected by pytest, not imported
        if stem in referenced or rel in marker_files:
            continue
        reason = "not imported anywhere and not tied to any prompt"
        if rel not in tracked:
            reason += "; also UNTRACKED"
        orphans.append(Finding(path.relative_to(repo), "orphan", reason))

    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in sources:
        data = read_text(path).strip()
        if len(data) < 200:
            continue
        by_hash[hashlib.sha256(data.encode("utf-8", "replace")).hexdigest()].append(path)

    dupes: list[Finding] = []
    for _h, group in by_hash.items():
        if len(group) > 1:
            names = ", ".join(g.relative_to(repo).as_posix() for g in group)
            dupes.append(Finding(group[0].relative_to(repo), "duplicate",
                                 f"byte-identical content shared by: {names}"))

    return orphans, dupes


def find_prompt_dupes(prompts: list[Prompt]) -> list[list[Prompt]]:
    """Byte-identical prompt files. A renamed scratch copy of a real master prompt is pure
    noise in the corpus and inflates every count in this report."""
    by_hash: dict[str, list[Prompt]] = defaultdict(list)
    for p in prompts:
        if p.sha256:
            by_hash[p.sha256].append(p)
    return [g for g in by_hash.values() if len(g) > 1]


def find_orphan_versions(by_tag: dict[str, list[tuple[str, str]]], prompts: list[Prompt],
                         sources: list[Path], repo: Path) -> list[tuple[str, int, int]]:
    """Versions that exist in git and/or code but have NO prompt file on disk.

    This is the inverse of 'forgotten': work that shipped with no surviving specification,
    so nobody can now say what it was supposed to do. Returns (tag, commits, marker_files)."""
    have_prompt = {p.tag for p in prompts if p.tag}
    marker_counts: dict[str, int] = defaultdict(int)
    all_tags = set(by_tag) - have_prompt
    if all_tags:
        pat = re.compile(r"\b(V(?:%s))\b" % "|".join(
            sorted((t[1:] for t in all_tags), key=int, reverse=True)))
        for path in sources:
            for tag in set(pat.findall(read_text(path))):
                marker_counts[tag] += 1
    return sorted(((t, len(by_tag[t]), marker_counts.get(t, 0)) for t in all_tags),
                  key=lambda x: int(x[0][1:]))


# ── stage 5: render ────────────────────────────────────────────────────────────

def render(repo: Path, prompts: list[Prompt], incomplete: list[Finding],
           orphans: list[Finding], dupes: list[Finding], head: str,
           prompt_dupes: list[list[Prompt]], orphan_versions: list[tuple[str, int, int]],
           lowest_tag: int) -> str:
    A = lambda rel: (repo / rel).resolve().as_posix().replace("/", "\\")   # absolute paths
    out: list[str] = []
    w = out.append

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    w("# Deep Audit — Prompts vs. Delivered Code\n")
    w(f"- Repository: `{repo.resolve()}`")
    w(f"- HEAD: `{head}`")
    w(f"- Generated: {ts} by `deep_audit.py`")
    w(f"- Prompts analyzed: **{len(prompts)}**\n")
    w("> Prompt bodies are treated as confidential. This report contains only titles, "
      "one-line goals, PART headings and counts — never prompt content.\n")
    w("## Reading this report — a required caveat\n")
    w(f"Prompt→commit linking relies on the `V<n> PART <k>: ...` commit-subject convention, "
      f"which this project only adopted at **V{lowest_tag}**. Every prompt numbered below "
      f"V{lowest_tag} is therefore marked **UNVERIFIABLE**, not 'not done' — the early work "
      f"was committed under free-form subjects (`v2.0`, `feat: ...`) and cannot be matched "
      f"by tag. For those, code markers are the only available evidence.\n")
    w("---\n")

    # ── BUILT ──
    w("# ساخته‌شده‌ها / Built\n")
    built = [p for p in prompts if p.status == "COMPLETE"]
    if not built:
        w("_None._\n")
    for p in sorted(built, key=lambda x: (x.tag is None, x.tag or x.name)):
        w(f"## {p.name} — {p.tag or 'untagged'}")
        w(f"- Prompt: `{A(p.path.relative_to(repo))}`")
        w(f"- Goal: {p.goal or '(no summary line found)'}")
        w(f"- Commits: {len(p.commits)}")
        for sha, subj in p.commits[:6]:
            w(f"  - `{sha[:7]}` {subj}")
        prod = sorted(f for f in p.commit_files if not Path(f).name.startswith("test_"))
        tests = sorted(f for f in p.commit_files if Path(f).name.startswith("test_"))
        if prod:
            w("- Output files:")
            for f in prod[:12]:
                w(f"  - `{A(f)}`")
        if tests:
            w(f"- Tests: {len(tests)} file(s), e.g. `{A(tests[0])}`")
        w("")

    # ── HALF-DONE ──
    w("---\n")
    w("# نیمه‌کاره‌ها / Half-done\n")
    partial = [p for p in prompts if p.status == "PARTIAL"]
    if partial:
        w("## Prompts with unfinished PARTs\n")
        for p in sorted(partial, key=lambda x: (x.tag is None, x.tag or x.name)):
            missing = [l for l, done in p.parts_done.items() if not done]
            w(f"- **{p.name}** ({p.tag or 'untagged'}) — {len(p.commits)} commit(s); "
              f"missing: {', '.join(missing) if missing else 'no PART headings to verify'}")
            w(f"  - `{A(p.path.relative_to(repo))}`")
        w("")

    grouped: dict[str, list[Finding]] = defaultdict(list)
    for f in incomplete:
        grouped[f.kind].append(f)

    titles = {"untracked-dep": "Imports of files git does not track (would break a clean clone)",
              "missing-dep": "Imports that resolve to nothing",
              "empty-body": "Functions with no implementation",
              "syntax-error": "Files that do not parse",
              "marker": "TODO / FIXME / XXX / HACK / NotImplementedError"}
    def in_tests(f: Finding) -> bool:
        return f.path.name.startswith("test_") or "tests" in f.path.parts

    for kind in ("syntax-error", "missing-dep", "untracked-dep", "empty-body", "marker"):
        items = grouped.get(kind, [])
        if not items:
            continue
        # An empty def inside a test file is nearly always a mock/stub double, not unfinished
        # work. Reporting the two together makes a real finding impossible to see.
        prod = [f for f in items if not in_tests(f)]
        test = [f for f in items if in_tests(f)]
        w(f"## {titles[kind]} — {len(prod)} in production code, "
          f"{len(test)} in tests\n")
        if prod:
            w("**Production code:**\n")
            for f in prod[:40]:
                w(f"- `{A(f.path)}`:{f.line} — {f.detail}")
            if len(prod) > 40:
                w(f"- _...and {len(prod) - 40} more_")
        else:
            w("_No production-code occurrences._")
        if test:
            w(f"\n<details><summary>{len(test)} occurrence(s) in test files "
              f"(mocks/stubs — usually benign)</summary>\n")
            for f in test[:25]:
                w(f"- `{A(f.path)}`:{f.line} — {f.detail}")
            if len(test) > 25:
                w(f"- _...and {len(test) - 25} more_")
            w("\n</details>")
        w("")

    # ── USELESS ──
    w("---\n")
    w("# بیهوده‌ها / Useless\n")
    w(f"## Orphan source files — {len(orphans)}\n")
    for f in orphans[:60]:
        w(f"- `{A(f.path)}` — {f.detail}")
    if len(orphans) > 60:
        w(f"- _...and {len(orphans) - 60} more_")
    w("")
    w(f"## Byte-identical duplicate source files — {len(dupes)}\n")
    for f in dupes:
        w(f"- {f.detail}")
    if not dupes:
        w("_None._")
    w("")

    w(f"## Byte-identical duplicate PROMPT files — {len(prompt_dupes)} group(s)\n")
    if not prompt_dupes:
        w("_None._")
    for group in prompt_dupes:
        w(f"- SHA256 `{group[0].sha256[:16]}` — {len(group)} identical copies "
          f"({group[0].size:,} bytes each):")
        for p in group:
            w(f"  - `{A(p.path.relative_to(repo))}`")
        w("  - **Only one of these is the real prompt; the rest are scratch copies "
          "inflating the corpus.**")
    w("")

    # ── FORGOTTEN ──
    w("---\n")
    w("# فراموش‌شده‌ها / Forgotten\n")
    never = [p for p in prompts if p.status == "NOT DONE"]
    w(f"Prompts with **zero** commits and **zero** code markers — {len(never)}:\n")
    for p in sorted(never, key=lambda x: (x.tag is None, x.tag or x.name)):
        w(f"- **{p.name}** — {p.goal[:100] or '(no goal line)'}")
        w(f"  - `{A(p.path.relative_to(repo))}`  ({p.requirement_count} imperative "
          f"requirement line(s), {len(p.parts)} PART(s) — none delivered)")
    if not never:
        w("_None._")
    w("")

    untracked_prompts = [p for p in prompts if not p.tracked]
    w(f"## Prompt specs never committed to git — {len(untracked_prompts)}\n")
    for p in sorted(untracked_prompts, key=lambda x: x.name):
        w(f"- `{A(p.path.relative_to(repo))}`")
    w("")

    w(f"## Code shipped with NO surviving prompt spec — {len(orphan_versions)}\n")
    if not orphan_versions:
        w("_None._")
    else:
        w("The inverse of a forgotten prompt: work that was committed and lives in the "
          "codebase, but whose specification file does not exist. Nobody can now say what "
          "these were scoped to deliver.\n")
        w("| Version | Commits | Files carrying the marker |")
        w("|---|---|---|")
        for tag, ncommits, nmarkers in orphan_versions:
            w(f"| **{tag}** | {ncommits} | {nmarkers} |")
    w("")

    binaries = [p for p in prompts if p.binary]
    if binaries:
        w(f"## Binary / non-text files in the prompt corpus (name only) — {len(binaries)}\n")
        for p in binaries:
            w(f"- `{A(p.path.relative_to(repo))}`")
        w("")

    # ── MAP ──
    w("---\n")
    w("# نقشه پرامپت‌ها / Prompt map\n")
    w("| Prompt file | Goal (summary) | Status | Commits | Output file(s) |")
    w("|---|---|---|---|---|")

    def sort_key(p: Prompt):
        return (0, int(p.tag[1:])) if p.tag else (1, 0)

    for p in sorted(prompts, key=sort_key):
        goal = (p.goal or p.title or "-").replace("|", "/")
        if len(goal) > 70:
            goal = goal[:67] + "..."
        files = sorted(f for f in p.commit_files if not Path(f).name.startswith("test_"))
        shown = ", ".join(f"`{Path(f).name}`" for f in files[:3]) or "—"
        if len(files) > 3:
            shown += f" +{len(files) - 3}"
        w(f"| `{p.name}` | {goal} | **{p.status}** | {len(p.commits)} | {shown} |")
    w("")

    counts = defaultdict(int)
    for p in prompts:
        counts[p.status] += 1
    w("---\n")
    w("# Summary\n")
    w(f"- Complete: **{counts['COMPLETE']}**")
    w(f"- Partial: **{counts['PARTIAL']}**")
    w(f"- Not done: **{counts['NOT DONE']}**")
    w(f"- Half-done code findings: **{len(incomplete)}**")
    w(f"- Orphan files: **{len(orphans)}**  |  Duplicate files: **{len(dupes)}**")
    w(f"- Prompt specs untracked by git: **{len(untracked_prompts)}**")
    w("")
    return "\n".join(out)


# ── entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Static prompt-vs-code audit.")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--prompt-dir", default=None,
                    help="Directory holding prompt files. Defaults to <repo>/prompts if it "
                         "exists, else the repo root.")
    ap.add_argument("--output", default="audit.md")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if args.prompt_dir:
        prompt_dir = Path(args.prompt_dir).resolve()
    else:
        candidate = repo / "prompts"
        prompt_dir = candidate if candidate.is_dir() else repo

    print(f"[deep_audit] repo       : {repo}")
    print(f"[deep_audit] prompt dir : {prompt_dir}"
          f"{'' if (repo / 'prompts').is_dir() else '   (no prompts/ dir — using repo root)'}")

    tracked = {l.strip() for l in run_git(repo, "ls-files").splitlines() if l.strip()}
    head = (run_git(repo, "log", "-1", "--pretty=format:%h %s") or "unknown").strip()
    print(f"[deep_audit] tracked    : {len(tracked)} files")

    prompts = discover_prompts(prompt_dir, tracked, repo)
    print(f"[deep_audit] prompts    : {len(prompts)}")

    sources = sorted(set(walk_sources(repo / "backend")) | set(walk_sources(repo / "frontend")))
    print(f"[deep_audit] sources    : {len(sources)}")

    lowest_tag, by_tag = map_commits(repo, prompts)
    map_markers(repo, prompts, sources)
    incomplete = find_incomplete(repo, sources, tracked)
    orphans, dupes = find_useless(repo, sources, prompts, tracked)
    prompt_dupes = find_prompt_dupes(prompts)
    orphan_versions = find_orphan_versions(by_tag, prompts, sources, repo)
    print(f"[deep_audit] convention : commit tags start at V{lowest_tag} "
          f"(older prompts are UNVERIFIABLE by design)")
    print(f"[deep_audit] findings   : {len(incomplete)} incomplete, {len(orphans)} orphan, "
          f"{len(dupes)} dup-source, {len(prompt_dupes)} dup-prompt, "
          f"{len(orphan_versions)} spec-less version(s)")

    report = render(repo, prompts, incomplete, orphans, dupes, head,
                    prompt_dupes, orphan_versions, lowest_tag)
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = repo / out_path
    out_path.write_text(report, encoding="utf-8")
    print(f"[deep_audit] wrote      : {out_path}  ({len(report):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
