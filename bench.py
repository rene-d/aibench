#!/usr/bin/env python3
"""
Benchmark d'un LLM local (Ollama) ou de Claude sur des tâches de codage,
en Rust et en Python.

Deux modes d'évaluation :
  - direct    : un seul appel, le modèle rend le fichier d'un coup (pass@1).
  - agentique : boucle outillée (write_file / read_file / run_command), le
                modèle compile, teste et itère jusqu'à se déclarer satisfait.

Dans les deux cas la note finale vient d'une suite de tests *cachée* que le
modèle ne voit jamais, exécutée dans une copie propre du projet.

Usage :
    python3 bench.py --self-test
    python3 bench.py --models qwen3.6:35b-mlx
    python3 bench.py --models claude:opus --lang python
    python3 bench.py --models a,b --tasks rust/rle,python/asn1_ber --modes direct
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT / "tasks"
RUNS_DIR = ROOT / "runs"

CARGO_TOML = """[package]
name = "task"
version = "0.1.0"
edition = "2021"

[lib]
path = "src/lib.rs"

# Empêche cargo de remonter vers un workspace parent.
[workspace]
"""

PY = sys.executable or "python3"

# --------------------------------------------------------------------------- #
# Utilitaires processus / temps
# --------------------------------------------------------------------------- #


class Deadline:
    """Budget de temps global pour un couple (tâche, mode)."""

    def __init__(self, seconds: float):
        self.limit = seconds
        self.start = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start

    @property
    def remaining(self) -> float:
        return self.limit - self.elapsed

    @property
    def expired(self) -> bool:
        return self.remaining <= 0


def run_cmd_split(argv: list[str], cwd: Path, timeout: float, env: dict | None = None,
                  stdin_text: str | None = None):
    """Comme run_cmd mais garde stdout et stderr séparés (sortie JSON à parser)."""
    t0 = time.monotonic()
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                              timeout=max(1.0, timeout), env=full_env, input=stdin_text)
        return proc.returncode, proc.stdout or "", proc.stderr or "", time.monotonic() - t0, False
    except subprocess.TimeoutExpired as exc:
        dec = lambda b: (b.decode(errors="replace") if isinstance(b, bytes) else (b or ""))
        return 124, dec(exc.stdout), dec(exc.stderr), time.monotonic() - t0, True


def run_cmd(argv: list[str], cwd: Path, timeout: float, env: dict | None = None):
    """Lance une commande, la tue au bout de `timeout` secondes."""
    t0 = time.monotonic()
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout),
            env=full_env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out, time.monotonic() - t0, False
    except subprocess.TimeoutExpired as exc:
        out = ""
        for chunk in (exc.stdout, exc.stderr):
            if chunk:
                out += chunk.decode() if isinstance(chunk, bytes) else chunk
        out += f"\n[harness] commande tuée après {timeout:.0f}s"
        return 124, out, time.monotonic() - t0, True
    except FileNotFoundError as exc:
        return 127, f"[harness] {exc}", time.monotonic() - t0, False


# --------------------------------------------------------------------------- #
# Client Ollama (streaming, pour pouvoir couper net sur deadline)
# --------------------------------------------------------------------------- #


class OllamaError(RuntimeError):
    pass


class ToolsUnsupported(OllamaError):
    pass


@dataclass
class LlmReply:
    content: str = ""
    thinking: str = ""
    tool_calls: list = field(default_factory=list)
    prompt_tokens: int = 0
    gen_tokens: int = 0
    eval_s: float = 0.0
    load_s: float = 0.0
    wall_s: float = 0.0
    ttft_s: float = 0.0
    aborted: bool = False


class Ollama:
    def __init__(self, host: str, num_ctx: int, temperature: float, seed: int, keep_alive: str):
        self.host = host.rstrip("/")
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.seed = seed
        self.keep_alive = keep_alive

    def chat(self, model: str, messages: list, tools: list | None, budget: float) -> LlmReply:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
                "seed": self.seed,
            },
        }
        if tools:
            payload["tools"] = tools

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

        reply = LlmReply()
        t0 = time.monotonic()
        try:
            resp = urllib.request.urlopen(req, timeout=max(5.0, min(budget, 120.0)))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if "does not support tools" in body or "tools" in body and exc.code == 400:
                raise ToolsUnsupported(body) from exc
            raise OllamaError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama injoignable sur {self.host} : {exc}") from exc

        try:
            for raw in resp:
                if time.monotonic() - t0 > budget:
                    reply.aborted = True
                    break
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in chunk:
                    raise OllamaError(str(chunk["error"]))
                msg = chunk.get("message") or {}
                piece = msg.get("content") or ""
                if piece:
                    if not reply.ttft_s:
                        reply.ttft_s = time.monotonic() - t0
                    reply.content += piece
                thought = msg.get("thinking") or ""
                if thought:
                    if not reply.ttft_s:
                        reply.ttft_s = time.monotonic() - t0
                    reply.thinking += thought
                for call in msg.get("tool_calls") or []:
                    reply.tool_calls.append(call)
                if chunk.get("done"):
                    reply.prompt_tokens = chunk.get("prompt_eval_count", 0) or 0
                    reply.gen_tokens = chunk.get("eval_count", 0) or 0
                    reply.eval_s = (chunk.get("eval_duration", 0) or 0) / 1e9
                    reply.load_s = (chunk.get("load_duration", 0) or 0) / 1e9
        finally:
            resp.close()  # couper la connexion arrête la génération côté serveur

        reply.wall_s = time.monotonic() - t0
        return reply

    def warmup(self, model: str) -> float:
        """Charge le modèle en mémoire pour ne pas facturer le load au 1er test."""
        t0 = time.monotonic()
        self.chat(model, [{"role": "user", "content": "ok"}], None, budget=180.0)
        return time.monotonic() - t0


# --------------------------------------------------------------------------- #
# Langages : tout ce qui diffère entre un projet cargo et un projet Python
# --------------------------------------------------------------------------- #

RUST_TEST_LINE = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+(ok|FAILED|ignored)", re.M)
RUST_RESULT = re.compile(r"test result:\s+(ok|FAILED)\.\s+(\d+) passed;\s+(\d+) failed", re.M)
PY_OK_LINE = re.compile(r"\.\.\. ok\s*$", re.M)
PY_RAN = re.compile(r"^Ran (\d+) tests?", re.M)


class Lang:
    name: str
    entry: str          # le fichier que le modèle doit produire
    test_path: str      # où le harnais dépose les tests cachés
    fences: tuple       # langages de bloc markdown acceptés
    label: str          # nom affiché dans les prompts
    layout: str         # description de l'arborescence, pour les prompts
    test_cmd: str       # commande que l'agent est censé lancer
    allowed_cmds: str   # description de l'allowlist, pour les prompts

    def scaffold(self, project: Path, source: str) -> None: ...
    def extras(self, project: Path) -> list[Path]: ...
    def collect(self, project: Path) -> str: ...
    def env(self, target_dir: Path) -> dict: return {}
    def pre_argv(self) -> list[list[str]]: return []
    def tests_argv(self) -> list[str]: ...
    def count_tests(self, tests_src: str) -> int: ...
    def write_ok(self, rel: Path) -> bool: ...
    def normalise_cmd(self, parts: list[str]) -> list[str] | None: ...
    def parse(self, out: str, rc: int, n_tests: int) -> tuple[bool, int, int]: ...


class RustLang(Lang):
    name = "rust"
    entry = "src/lib.rs"
    test_path = "tests/hidden.rs"
    fences = ("rust", "rs")
    label = "Rust"
    layout = ("    Cargo.toml        (crate bibliothèque nommée `task`, édition 2021, "
              "aucune dépendance)\n"
              "    src/lib.rs        (à toi de le remplir)\n"
              "    tests/            (tu peux y écrire tes propres tests d'intégration)")
    test_cmd = "cargo test"
    allowed_cmds = "cargo build, cargo check, cargo test, cargo clippy, cargo fmt"

    def scaffold(self, project, source):
        (project / "src").mkdir(parents=True, exist_ok=True)
        (project / "Cargo.toml").write_text(CARGO_TOML)
        (project / "src" / "lib.rs").write_text(source or "// Écris ton implémentation ici.\n")

    def extras(self, project):
        src = project / "src"
        return [p for p in sorted(src.glob("*.rs")) if p.name != "lib.rs"] if src.exists() else []

    def collect(self, project):
        f = project / "src" / "lib.rs"
        return f.read_text() if f.exists() else ""

    def env(self, target_dir):
        return {"CARGO_TARGET_DIR": str(target_dir), "CARGO_TERM_COLOR": "never", "RUSTFLAGS": ""}

    def tests_argv(self):
        return ["cargo", "test", "--offline", "--test", "hidden", "--", "--test-threads=1"]

    def count_tests(self, tests_src):
        return tests_src.count("#[test]")

    def write_ok(self, rel):
        return rel.parts and rel.parts[0] in ("src", "tests") and rel.suffix == ".rs"

    def normalise_cmd(self, parts):
        allowed = {"build", "check", "test", "clippy", "fmt"}
        if len(parts) >= 2 and parts[0] == "cargo" and parts[1] in allowed:
            return ["cargo", parts[1], "--offline"] + parts[2:]
        return None

    def parse(self, out, rc, n_tests):
        m = RUST_RESULT.search(out)
        if not m:
            return False, 0, n_tests
        seen = len(RUST_TEST_LINE.findall(out))
        return True, int(m.group(2)), max(n_tests, seen)


class PythonLang(Lang):
    name = "python"
    entry = "solution.py"
    test_path = "test_hidden.py"
    fences = ("python", "py", "python3")
    label = "Python"
    layout = ("    solution.py       (à toi de le remplir — c'est le module importé "
              "par les tests)\n"
              "    test_*.py         (tu peux y écrire tes propres tests unittest)")
    test_cmd = f"{Path(PY).name} -m unittest discover -v"
    allowed_cmds = (f"{Path(PY).name} -m unittest ..., {Path(PY).name} -m py_compile ..., "
                    f"{Path(PY).name} <fichier>.py")

    def scaffold(self, project, source):
        project.mkdir(parents=True, exist_ok=True)
        (project / "solution.py").write_text(source or "# Écris ton implémentation ici.\n")

    def extras(self, project):
        return [p for p in sorted(project.glob("*.py"))
                if p.name != "solution.py" and not p.name.startswith("test_")]

    def collect(self, project):
        f = project / "solution.py"
        return f.read_text() if f.exists() else ""

    def env(self, target_dir):
        # pas de __pycache__ partagé entre projets, et pas de site-packages surprise
        return {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ""}

    def pre_argv(self):
        return [[PY, "-m", "py_compile", "solution.py"]]

    def tests_argv(self):
        return [PY, "-m", "unittest", "-v", "test_hidden"]

    def count_tests(self, tests_src):
        return len(re.findall(r"^\s+def test_\w+", tests_src, re.M))

    def write_ok(self, rel):
        return len(rel.parts) == 1 and rel.suffix == ".py"

    def normalise_cmd(self, parts):
        exe = Path(parts[0]).name if parts else ""
        if exe not in ("python", "python3", Path(PY).name):
            return None
        if len(parts) >= 3 and parts[1] == "-m" and parts[2] in ("unittest", "py_compile", "pytest"):
            return [PY] + parts[1:]
        if len(parts) >= 2 and parts[1].endswith(".py"):
            return [PY] + parts[1:]
        return None

    def parse(self, out, rc, n_tests):
        m = PY_RAN.search(out)
        if not m:
            return False, 0, n_tests
        return True, len(PY_OK_LINE.findall(out)), max(n_tests, int(m.group(1)))


LANGS = {l.name: l for l in (RustLang(), PythonLang())}


@dataclass
class Grade:
    status: str = "fail"  # pass | fail | compile_error | no_code | timeout
    passed: int = 0
    total: int = 0
    compiled: bool = False
    detail: str = ""
    cargo_s: float = 0.0

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0


def grade(task: "Task", source: str, workdir: Path, target_dir: Path, timeout: float) -> Grade:
    """Exécute la solution candidate contre la suite de tests cachée."""
    lang = task.lang
    g = Grade(total=task.n_tests)
    if not source.strip():
        g.status = "no_code"
        g.detail = "aucun code produit"
        return g

    project = workdir / "grading"
    if project.exists():
        shutil.rmtree(project)
    lang.scaffold(project, source)
    for extra in task.extra_sources:
        dest = project / Path(lang.entry).parent / extra.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(extra.read_text())
    test_file = project / lang.test_path
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(task.tests_src)

    env = lang.env(target_dir)
    deadline = time.monotonic() + timeout

    # étape préalable (py_compile) : une erreur ici est une erreur de "compilation"
    for argv in lang.pre_argv():
        rc, out, secs, killed = run_cmd(argv, project, max(5.0, deadline - time.monotonic()), env)
        g.cargo_s += secs
        if killed:
            g.status, g.detail = "timeout", out[-4000:]
            return g
        if rc != 0:
            g.status, g.detail = "compile_error", out[-4000:]
            return g

    rc, out, secs, killed = run_cmd(
        lang.tests_argv(), project, max(5.0, deadline - time.monotonic()), env
    )
    g.cargo_s += secs
    g.detail = out[-4000:]
    if killed:
        g.status = "timeout"
        return g

    compiled, passed, total = lang.parse(out, rc, task.n_tests)
    g.compiled, g.passed, g.total = compiled, passed, total
    if not compiled:
        g.status = "compile_error" if rc != 0 else "fail"
    else:
        g.status = "pass" if (rc == 0 and passed == total) else "fail"
    return g


# --------------------------------------------------------------------------- #
# Tâches
# --------------------------------------------------------------------------- #


@dataclass
class Task:
    name: str
    lang: Lang
    spec: str
    tests_src: str
    reference: str
    n_tests: int
    extra_sources: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.lang.name}/{self.name}"


def load_tasks(names: list[str] | None, langs: list[str] | None) -> list[Task]:
    """Charge tasks/<langage>/<tâche>/. `names` accepte `rle` ou `rust/rle`."""
    tasks, matched = [], set()
    for lang_dir in sorted(TASKS_DIR.iterdir()):
        if not lang_dir.is_dir() or lang_dir.name not in LANGS:
            continue
        if langs and lang_dir.name not in langs:
            continue
        lang = LANGS[lang_dir.name]
        for d in sorted(lang_dir.iterdir()):
            if not d.is_dir():
                continue
            key, short = f"{lang.name}/{d.name}", d.name
            if names and key not in names and short not in names:
                continue
            matched.update({key, short} & set(names or []))
            tests_src = (d / "tests").with_suffix(Path(lang.test_path).suffix).read_text()
            reference = (d / "reference").with_suffix(Path(lang.entry).suffix).read_text()
            tasks.append(Task(
                name=d.name,
                lang=lang,
                spec=(d / "spec.md").read_text(),
                tests_src=tests_src,
                reference=reference,
                n_tests=lang.count_tests(tests_src),
            ))
    if names:
        missing = set(names) - matched
        if missing:
            sys.exit(f"tâches inconnues : {', '.join(sorted(missing))}")
    return tasks


# --------------------------------------------------------------------------- #
# Extraction de code
# --------------------------------------------------------------------------- #

THINK_TAGS = re.compile(r"<think>.*?</think>", re.S | re.I)
# Une fence ne compte que si les backticks ouvrent la ligne. Sans cette
# contrainte, les doc-comments Rust (`/// ```) fermeraient le bloc trop tôt et
# tronqueraient le fichier rendu par le modèle.
FENCE_LINE = re.compile(r"^\s*```+\s*([A-Za-z0-9_+.-]*)\s*$")


def fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Renvoie [(langage, contenu)] en scannant ligne à ligne."""
    blocks, lang, buf, inside = [], "", [], False
    for line in text.splitlines():
        m = FENCE_LINE.match(line)
        if m and not inside:
            inside, lang, buf = True, m.group(1).lower(), []
        elif m and inside:
            blocks.append((lang, "\n".join(buf)))
            inside = False
        elif inside:
            buf.append(line)
    if inside and buf:  # bloc jamais refermé (troncature côté modèle)
        blocks.append((lang, "\n".join(buf)))
    return blocks


def strip_thinking(text: str) -> str:
    text = THINK_TAGS.sub("", text)
    # cas d'un <think> jamais refermé
    if "<think>" in text and "</think>" not in text:
        text = text.split("<think>")[0]
    return text


DEF_RE = {"rust": re.compile(r"\bpub\s+(fn|struct|enum)\b"),
          "python": re.compile(r"^(def|class)\s+\w+", re.M)}


def extract_code(text: str, lang: Lang) -> str:
    text = strip_thinking(text)
    blocks = [b for tag, b in fenced_blocks(text) if tag == "" or tag in lang.fences]
    pat = DEF_RE[lang.name]
    if not blocks:
        # peut-être du code brut, sans balises
        return text.strip() + "\n" if pat.search(text) else ""
    # on garde le bloc le plus substantiel (le modèle bavarde parfois avant)
    return max(blocks, key=lambda b: (len(pat.findall(b)), len(b))).strip() + "\n"


# --------------------------------------------------------------------------- #
# Mode direct
# --------------------------------------------------------------------------- #

DIRECT_SYSTEM = (
    "Tu es un développeur {label} expérimenté. Tu écris du code correct, idiomatique "
    "et qui marche du premier coup avec la bibliothèque standard uniquement."
)

DIRECT_USER = """{spec}

---

Rends TON code dans UN SEUL bloc ```{fence} contenant l'intégralité du fichier
`{entry}`. Pas de point d'entrée exécutable, pas de dépendance externe, pas de
commentaire d'introduction en dehors du bloc de code. Le code doit marcher tel quel."""


def direct_messages(task: Task) -> tuple[str, str]:
    return (
        DIRECT_SYSTEM.format(label=task.lang.label),
        DIRECT_USER.format(spec=task.spec, fence=task.lang.fences[0], entry=task.lang.entry),
    )


def run_direct(client: Ollama, model: str, task: Task, workdir: Path,
               target_dir: Path, deadline: Deadline, cargo_timeout: float) -> "Result":
    res = Result(model=model, task=task.key, mode="direct", protocol="single-shot")
    system, user = direct_messages(task)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        reply = client.chat(model, messages, None, budget=deadline.remaining)
    except OllamaError as exc:
        res.status = "error"
        res.detail = str(exc)[:500]
        res.wall_s = deadline.elapsed
        return res

    res.turns = 1
    res.absorb(reply)
    (workdir / "raw_reply.md").write_text(reply.thinking + "\n\n" + reply.content)

    if reply.aborted or deadline.expired:
        res.status = "timeout"
        res.detail = f"budget de {deadline.limit:.0f}s dépassé pendant la génération"
        res.wall_s = deadline.elapsed
        return res

    code = extract_code(reply.content, task.lang)
    (workdir / candidate_name(task)).write_text(code)
    res.loc = len([l for l in code.splitlines() if l.strip()])

    g = grade(task, code, workdir, target_dir, min(cargo_timeout, max(5.0, deadline.remaining)))
    res.apply_grade(g)
    res.wall_s = deadline.elapsed
    return res


def candidate_name(task: Task) -> str:
    return "candidate" + Path(task.lang.entry).suffix


# --------------------------------------------------------------------------- #
# Mode agentique
# --------------------------------------------------------------------------- #

AGENT_SYSTEM = """Tu es un agent de développement {label} autonome. Tu travailles dans ce projet :

{layout}

Ta méthode :
 1. écris `{entry}` avec write_file ;
 2. lance `{test_cmd}` avec run_command ;
 3. lis les erreurs, corrige, recommence ;
 4. quand tout marche et que tes tests passent, appelle `finish`.

Règles : bibliothèque standard uniquement, pas de point d'entrée exécutable, pas
de dépendance externe.
Ton code sera ensuite noté par une suite de tests cachée conforme à la
spécification : respecte scrupuleusement les signatures demandées.
Tu as {max_turns} tours maximum. N'appelle qu'un outil à la fois."""

AGENT_USER = "Voici la tâche à réaliser.\n\n{spec}\n\nCommence maintenant."

def build_tools(lang: Lang) -> list:
    tools = json.loads(json.dumps(TOOLS))  # copie profonde
    fn = {t["function"]["name"]: t["function"] for t in tools}
    paths = "src/*.rs, tests/*.rs" if lang.name == "rust" else "*.py à la racine"
    fn["write_file"]["description"] = (
        f"Écrit (ou écrase) un fichier du projet. Chemins autorisés : {paths}")
    fn["write_file"]["parameters"]["properties"]["path"]["description"] = (
        f"chemin relatif, ex: {lang.entry}")
    fn["run_command"]["description"] = f"Exécute une commande. Autorisé : {lang.allowed_cmds}."
    fn["run_command"]["parameters"]["properties"]["command"]["description"] = (
        f"ex: {lang.test_cmd}")
    return tools


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Écrit (ou écrase) un fichier du projet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "chemin relatif"},
                    "content": {"type": "string", "description": "contenu complet du fichier"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lit un fichier du projet.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Exécute une commande.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "commande"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Déclare la tâche terminée.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": [],
            },
        },
    },
]

MAX_TOOL_OUTPUT = 3500


class Sandbox:
    """Exécute les outils de l'agent dans son projet, avec allowlist par langage."""

    def __init__(self, project: Path, lang: Lang, target_dir: Path, cargo_timeout: float):
        self.project = project
        self.lang = lang
        self.target_dir = target_dir
        self.cargo_timeout = cargo_timeout
        self.writes = 0
        self.commands = 0
        self.cargo_s = 0.0
        self.last_test_ok = False

    def _rel(self, path: str) -> tuple[Path, Path] | None:
        p = (self.project / path).resolve()
        try:
            return p, p.relative_to(self.project.resolve())
        except ValueError:
            return None

    def write_file(self, args: dict) -> str:
        path, content = args.get("path", ""), args.get("content", "")
        hit = self._rel(path)
        if hit is None or not self.lang.write_ok(hit[1]):
            return f"ERREUR: chemin refusé '{path}'."
        p = hit[0]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.writes += 1
        return f"OK: {path} écrit ({len(content.splitlines())} lignes)."

    def read_file(self, args: dict) -> str:
        hit = self._rel(args.get("path", ""))
        if hit is None:
            return "ERREUR: chemin refusé."
        p = hit[0]
        if not p.is_file():
            return "ERREUR: fichier inexistant."
        return p.read_text()[:MAX_TOOL_OUTPUT]

    def run_command(self, args: dict, budget: float) -> str:
        cmd = (args.get("command") or "").strip()
        argv = self.lang.normalise_cmd(cmd.split())
        if argv is None:
            return f"ERREUR: commande refusée '{cmd}'. Autorisé : {self.lang.allowed_cmds}"
        rc, out, secs, killed = run_cmd(
            argv, self.project, min(self.cargo_timeout, max(5.0, budget)),
            self.lang.env(self.target_dir),
        )
        self.commands += 1
        self.cargo_s += secs
        if "test" in " ".join(argv):
            self.last_test_ok = rc == 0
        head = f"$ {' '.join(argv)}\n(exit {rc}, {secs:.1f}s)\n"
        if len(out) > MAX_TOOL_OUTPUT:
            out = out[:MAX_TOOL_OUTPUT // 2] + "\n[...tronqué...]\n" + out[-MAX_TOOL_OUTPUT // 2:]
        return head + out

    def collect_sources(self) -> str:
        return self.lang.collect(self.project)

    def extra_modules(self) -> list[Path]:
        return self.lang.extras(self.project)


# --- protocole texte, pour les modèles sans tool-calling natif --------------- #

TEXT_PROTOCOL = """Tu ne disposes pas d'appels d'outils structurés : à chaque tour, réponds
avec EXACTEMENT UNE action, dans ce format et rien d'autre :

Pour écrire un fichier :
ACTION: write_file
PATH: {entry}
```{fence}
<contenu complet du fichier>
```

Pour lancer une commande :
ACTION: run_command
CMD: {test_cmd}

Pour terminer :
ACTION: finish
"""

ACTION_RE = re.compile(r"ACTION:\s*(\w+)", re.I)
PATH_RE = re.compile(r"PATH:\s*(\S+)", re.I)
CMD_RE = re.compile(r"CMD:\s*(.+)", re.I)


def parse_text_action(text: str, lang: Lang) -> tuple[str, dict]:
    text = strip_thinking(text)
    m = ACTION_RE.search(text)
    action = (m.group(1).lower() if m else "")
    if action == "finish":
        return "finish", {}
    if action == "run_command":
        c = CMD_RE.search(text)
        return "run_command", {"command": c.group(1).strip() if c else lang.test_cmd}
    code = extract_code(text, lang)
    if action == "write_file" or code:
        p = PATH_RE.search(text)
        return "write_file", {"path": p.group(1).strip() if p else lang.entry, "content": code}
    return "", {}


def run_agentic(client: Ollama, model: str, task: Task, workdir: Path, target_dir: Path,
                deadline: Deadline, cargo_timeout: float, max_turns: int,
                protocol: str) -> "Result":
    res = Result(model=model, task=task.key, mode="agentic", protocol=protocol)
    lang = task.lang
    project = workdir / "agent"
    lang.scaffold(project, "")
    box = Sandbox(project, lang, target_dir, cargo_timeout)
    tools = build_tools(lang)
    text_proto = TEXT_PROTOCOL.format(entry=lang.entry, fence=lang.fences[0],
                                      test_cmd=lang.test_cmd)

    use_tools = protocol in ("tools", "auto")
    system = AGENT_SYSTEM.format(max_turns=max_turns, label=lang.label, layout=lang.layout,
                                 entry=lang.entry, test_cmd=lang.test_cmd)
    if not use_tools:
        system += "\n\n" + text_proto
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": AGENT_USER.format(spec=task.spec)},
    ]
    transcript = []

    for turn in range(1, max_turns + 1):
        if deadline.expired:
            res.status = "timeout"
            res.detail = f"budget de {deadline.limit:.0f}s dépassé au tour {turn}"
            break
        try:
            reply = client.chat(model, messages, tools if use_tools else None,
                                budget=deadline.remaining)
        except ToolsUnsupported:
            if protocol == "auto":
                # bascule automatique vers le protocole texte
                res.protocol = protocol = "text"
                use_tools = False
                messages[0]["content"] = system + "\n\n" + text_proto
                continue
            res.status = "error"
            res.detail = "le modèle ne supporte pas les outils"
            break
        except OllamaError as exc:
            res.status = "error"
            res.detail = str(exc)[:500]
            break

        res.turns = turn
        res.absorb(reply)
        if use_tools and protocol == "auto" and reply.tool_calls:
            res.protocol = "tools"

        if reply.aborted or deadline.expired:
            res.status = "timeout"
            res.detail = f"budget de {deadline.limit:.0f}s dépassé pendant la génération (tour {turn})"
            transcript.append({"turn": turn, "assistant": reply.content[:2000], "aborted": True})
            break

        # --- déterminer l'action demandée ---------------------------------- #
        if reply.tool_calls:
            call = reply.tool_calls[0]["function"]
            name = call.get("name", "")
            args = call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
        else:
            name, args = parse_text_action(reply.content, lang)

        assistant_msg = {"role": "assistant", "content": reply.content}
        if reply.tool_calls:
            assistant_msg["tool_calls"] = reply.tool_calls[:1]
        messages.append(assistant_msg)

        if name == "finish":
            transcript.append({"turn": turn, "action": "finish"})
            break
        if name == "write_file":
            out = box.write_file(args)
        elif name == "read_file":
            out = box.read_file(args)
        elif name == "run_command":
            out = box.run_command(args, deadline.remaining)
        else:
            out = ("ERREUR: aucune action reconnue. Utilise write_file, read_file, "
                   "run_command ou finish.")
            res.malformed += 1

        res.tool_calls += 1
        transcript.append({
            "turn": turn,
            "action": name or "?",
            "args": {k: (v[:200] if isinstance(v, str) else v) for k, v in args.items()},
            "result": out[:1500],
        })

        if reply.tool_calls:
            messages.append({"role": "tool", "content": out,
                             "tool_name": call.get("name", name)})
        else:
            messages.append({"role": "user", "content": out})

    (workdir / "transcript.json").write_text(json.dumps(transcript, indent=2, ensure_ascii=False))

    code = box.collect_sources()
    (workdir / candidate_name(task)).write_text(code)
    res.loc = len([l for l in code.splitlines() if l.strip()])
    res.writes = box.writes
    res.commands = box.commands
    res.self_tests_ok = box.last_test_ok
    task_for_grade = replace(task, extra_sources=box.extra_modules())

    if res.status not in ("timeout", "error"):
        g = grade(task_for_grade, code, workdir, target_dir,
                  min(cargo_timeout, max(5.0, deadline.remaining)))
        res.apply_grade(g)
    res.cargo_s += box.cargo_s
    res.wall_s = deadline.elapsed
    return res


# --------------------------------------------------------------------------- #
# Backend Claude Code CLI (auth par abonnement, pas de clé API)
# --------------------------------------------------------------------------- #

CLI_PREFIX = "claude:"

AGENT_SYSTEM_CLI = """Tu es un agent de développement {label} autonome. Tu travailles dans ce projet :

{layout}

Ta méthode :
 1. écris `{entry}` avec l'outil Write ;
 2. lance `{test_cmd}` avec l'outil Bash ;
 3. lis les erreurs, corrige, recommence ;
 4. quand tout marche et que tes tests passent, termine ton tour.

Seules les commandes `{bash_prefix}` sont autorisées dans Bash.
Règles : bibliothèque standard uniquement, pas de point d'entrée exécutable, pas
de dépendance externe.
Ton code sera ensuite noté par une suite de tests cachée conforme à la
spécification : respecte scrupuleusement les signatures demandées."""

# outil Bash du CLI : préfixe autorisé par langage
CLI_BASH_ALLOW = {"rust": "cargo", "python": Path(PY).name}


def parse_cli_json(stdout: str) -> dict:
    """Récupère l'objet `type: result` de la sortie --output-format json."""
    for line in reversed([l for l in stdout.splitlines() if l.strip()]):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            return obj
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {}


def absorb_cli(res: "Result", data: dict, model_id: str) -> None:
    """Reporte les métriques du JSON du CLI dans le Result.

    On n'attribue au modèle évalué que les tokens de `modelUsage` qui le
    concernent : le CLI émet aussi des appels annexes (haiku) qui ne font pas
    partie de la tâche.
    """
    usage = data.get("modelUsage") or {}
    mine = {k: v for k, v in usage.items()
            if model_id in k or k.endswith(model_id) or model_id in (v.get("canonicalModel") or "")}
    if not mine:  # fallback : usage global
        u = data.get("usage") or {}
        res.prompt_tokens += u.get("input_tokens", 0)
        res.gen_tokens += u.get("output_tokens", 0)
    else:
        for v in mine.values():
            res.prompt_tokens += v.get("inputTokens", 0) + v.get("cacheReadInputTokens", 0)
            res.gen_tokens += v.get("outputTokens", 0)
    res.cost_usd += float(data.get("total_cost_usd") or 0.0)
    res.llm_s += (data.get("duration_ms") or 0) / 1000.0
    # Pas de temps de décodage pur exposé : on prend le temps API comme
    # dénominateur du tok/s. Ce n'est PAS la même définition que pour Ollama.
    res.eval_s += (data.get("duration_api_ms") or 0) / 1000.0
    if not res.ttft_s:
        res.ttft_s = (data.get("ttft_ms") or 0) / 1000.0
    res.denials += len(data.get("permission_denials") or [])


def cli_base_argv(model: str, system: str) -> list[str]:
    return [
        "claude", "-p",
        "--model", model,
        "--system-prompt", system,
        "--output-format", "json",
        "--safe-mode",              # neutralise CLAUDE.md, skills, plugins, hooks
        "--no-session-persistence",
    ]
    # NB : le prompt passe par stdin, jamais en argument positionnel — les options
    # variadiques (`--tools`, `--allowed-tools`) l'avaleraient sinon.


def _cli_fail(res: "Result", data: dict, stderr: str, killed: bool, deadline: Deadline) -> bool:
    if killed:
        res.status = "timeout"
        res.detail = f"budget de {deadline.limit:.0f}s dépassé, processus claude tué"
        return True
    if not data:
        res.status = "error"
        res.detail = (stderr or "sortie JSON illisible")[-800:]
        return True
    if data.get("is_error") or data.get("subtype") != "success":
        res.status = "error"
        res.detail = str(data.get("result") or data.get("api_error_status") or stderr)[-800:]
        return True
    return False


def run_direct_cli(model: str, task: Task, workdir: Path, target_dir: Path,
                   deadline: Deadline, cargo_timeout: float) -> "Result":
    res = Result(model=CLI_PREFIX + model, task=task.key, mode="direct",
                 protocol="claude-code --tools ''")
    cwd = workdir / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)

    system, user = direct_messages(task)
    argv = cli_base_argv(model, system) + ["--tools", ""]  # aucun outil
    rc, out, err, secs, killed = run_cmd_split(argv, cwd, deadline.remaining, stdin_text=user)
    data = parse_cli_json(out)
    (workdir / "cli_result.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

    res.turns = data.get("num_turns", 1) or 1
    absorb_cli(res, data, model)
    if _cli_fail(res, data, err, killed, deadline):
        res.wall_s = deadline.elapsed
        return res

    text = data.get("result") or ""
    (workdir / "raw_reply.md").write_text(text)
    code = extract_code(text, task.lang)
    (workdir / candidate_name(task)).write_text(code)
    res.loc = len([l for l in code.splitlines() if l.strip()])

    g = grade(task, code, workdir, target_dir, min(cargo_timeout, max(5.0, deadline.remaining)))
    res.apply_grade(g)
    res.wall_s = deadline.elapsed
    return res


def run_agentic_cli(model: str, task: Task, workdir: Path, target_dir: Path,
                    deadline: Deadline, cargo_timeout: float, max_turns: int) -> "Result":
    lang = task.lang
    prefix = CLI_BASH_ALLOW[lang.name]
    res = Result(model=CLI_PREFIX + model, task=task.key, mode="agentic",
                 protocol=f"claude-code Read/Write/Bash({prefix})")
    project = workdir / "agent"
    lang.scaffold(project, "")

    system = AGENT_SYSTEM_CLI.format(label=lang.label, layout=lang.layout, entry=lang.entry,
                                     test_cmd=lang.test_cmd, bash_prefix=prefix)
    argv = cli_base_argv(model, system) + [
        "--tools", "Read,Write,Edit,Bash",
        "--allowed-tools", f"Bash({prefix}:*)",
        "--disallowed-tools", "WebSearch,WebFetch",
        "--permission-mode", "acceptEdits",
    ]
    rc, out, err, secs, killed = run_cmd_split(
        argv, project, deadline.remaining, env=lang.env(target_dir),
        stdin_text=AGENT_USER.format(spec=task.spec),
    )
    data = parse_cli_json(out)
    (workdir / "cli_result.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

    res.turns = data.get("num_turns", 0) or 0
    absorb_cli(res, data, model)
    if _cli_fail(res, data, err, killed, deadline):
        res.wall_s = deadline.elapsed
        return res

    (workdir / "raw_reply.md").write_text(data.get("result") or "")
    code = lang.collect(project)
    (workdir / candidate_name(task)).write_text(code)
    res.loc = len([l for l in code.splitlines() if l.strip()])
    task_for_grade = replace(task, extra_sources=lang.extras(project))

    g = grade(task_for_grade, code, workdir, target_dir,
              min(cargo_timeout, max(5.0, deadline.remaining)))
    res.apply_grade(g)
    res.wall_s = deadline.elapsed
    return res


# --------------------------------------------------------------------------- #
# Résultats
# --------------------------------------------------------------------------- #


@dataclass
class Result:
    model: str
    task: str
    mode: str
    protocol: str = ""
    status: str = "fail"
    passed: int = 0
    total: int = 0
    compiled: bool = False
    wall_s: float = 0.0
    llm_s: float = 0.0
    cargo_s: float = 0.0
    ttft_s: float = 0.0
    prompt_tokens: int = 0
    gen_tokens: int = 0
    eval_s: float = 0.0
    turns: int = 0
    tool_calls: int = 0
    writes: int = 0
    commands: int = 0
    malformed: int = 0
    denials: int = 0
    cost_usd: float = 0.0
    self_tests_ok: bool = False
    loc: int = 0
    detail: str = ""

    def absorb(self, reply: LlmReply) -> None:
        self.llm_s += reply.wall_s
        self.prompt_tokens += reply.prompt_tokens
        self.gen_tokens += reply.gen_tokens
        self.eval_s += reply.eval_s
        if not self.ttft_s:
            self.ttft_s = reply.ttft_s

    def apply_grade(self, g: Grade) -> None:
        self.status = g.status
        self.passed = g.passed
        self.total = g.total
        self.compiled = g.compiled
        self.cargo_s += g.cargo_s
        if g.status != "pass":
            self.detail = g.detail[-1500:]

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def tok_s(self) -> float:
        return self.gen_tokens / self.eval_s if self.eval_s else 0.0


STATUS_ICON = {
    "pass": "✅ pass",
    "fail": "❌ tests KO",
    "compile_error": "🧱 compile KO",
    "no_code": "∅ pas de code",
    "timeout": "⏱ timeout",
    "error": "💥 erreur",
}


def report(results: list[Result], out_dir: Path, config: dict) -> str:
    lines = []
    lines.append("# Benchmark Rust — LLM local (Ollama)\n")
    lines.append(f"- date : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- machine : {config['machine']}")
    lines.append(f"- budget par (tâche, mode) : {config['task_timeout']:.0f}s "
                 f"(processus tué au-delà)")
    lines.append(f"- num_ctx={config['num_ctx']}, temperature={config['temperature']}, "
                 f"seed={config['seed']}, tours agentiques max={config['max_turns']}")
    lines.append("")

    has_cli = any(r.model.startswith(CLI_PREFIX) for r in results)

    lines.append("## Résultats détaillés\n")
    lines.append("| modèle | tâche | mode | statut | tests | temps | LLM | cargo | "
                 "tok gén | tok/s | tours | outils | LOC |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| `{r.model}` | {r.task} | {r.mode} | {STATUS_ICON.get(r.status, r.status)} "
            f"| {r.passed}/{r.total} | {r.wall_s:.0f}s | {r.llm_s:.0f}s | {r.cargo_s:.0f}s "
            f"| {r.gen_tokens} | {r.tok_s:.1f} | {r.turns} "
            f"| {r.tool_calls if not r.model.startswith(CLI_PREFIX) else '—'} | {r.loc} |"
        )
    lines.append("")

    if has_cli:
        cost = sum(r.cost_usd for r in results if r.model.startswith(CLI_PREFIX))
        lines.append("> ⚠️ **Comparabilité limitée entre backends.** Les lignes `claude:*` "
                     "passent par le CLI Claude Code, pas par Ollama :\n"
                     ">\n"
                     "> - Le **mode direct est comparable** : mêmes prompts, outils "
                     "désactivés (`--tools \"\"`), un seul appel.\n"
                     "> - Le **mode agentique ne l'est pas** : la boucle, le format des "
                     "outils et la gestion d'erreur sont ceux de Claude Code, pas ceux de "
                     "mon harnais à 4 outils. On compare deux agents, pas deux modèles.\n"
                     "> - **`tok/s` n'a pas la même définition** : décodage pur côté Ollama, "
                     "temps API bout en bout (réseau inclus) côté CLI. Ne pas mettre les "
                     "deux colonnes en face.\n"
                     "> - **`tours`** = allers-retours internes du CLI, pas mes tours de boucle.\n"
                     f"> - Coût notionnel des appels `claude:*` : **{cost:.2f} $** — non "
                     "facturé en plus sur un abonnement, mais décompté du quota de plan.\n")
        lines.append("")

    lines.append("## Synthèse par modèle et par mode\n")
    lines.append("| modèle | mode | réussite | score tests | temps médian | "
                 "tokens générés | tok/s moyen |")
    lines.append("|---|---|---|---|---|---|---|")
    models = sorted({r.model for r in results})
    for model in models:
        for mode in ("direct", "agentic"):
            sub = [r for r in results if r.model == model and r.mode == mode]
            if not sub:
                continue
            npass = sum(1 for r in sub if r.status == "pass")
            avg_score = statistics.mean(r.score for r in sub)
            med_t = statistics.median(r.wall_s for r in sub)
            toks = sum(r.gen_tokens for r in sub)
            speeds = [r.tok_s for r in sub if r.tok_s]
            lines.append(
                f"| `{model}` | {mode} | {npass}/{len(sub)} | {avg_score:.0%} "
                f"| {med_t:.0f}s | {toks} | {statistics.mean(speeds):.1f} |"
                if speeds else
                f"| `{model}` | {mode} | {npass}/{len(sub)} | {avg_score:.0%} "
                f"| {med_t:.0f}s | {toks} | n/a |"
            )
    lines.append("")

    failures = [r for r in results if r.status != "pass"]
    if failures:
        lines.append("## Échecs — extrait de diagnostic\n")
        for r in failures:
            lines.append(f"### `{r.model}` · {r.task} · {r.mode} — {STATUS_ICON.get(r.status)}\n")
            lines.append("```")
            lines.append((r.detail or "(pas de détail)").strip()[-1200:])
            lines.append("```\n")

    text = "\n".join(lines)
    (out_dir / "report.md").write_text(text)
    (out_dir / "results.json").write_text(
        json.dumps({"config": config, "results": [asdict(r) for r in results]},
                   indent=2, ensure_ascii=False)
    )
    return text


# --------------------------------------------------------------------------- #
# Self-test : les solutions de référence doivent passer 100 %
# --------------------------------------------------------------------------- #


def self_test(tasks: list[Task], target_dir: Path, cargo_timeout: float) -> int:
    print("Vérification des suites de tests cachées avec les solutions de référence…\n")
    tmp = RUNS_DIR / "_selftest"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    bad = 0
    for t in tasks:
        g = grade(t, t.reference, tmp / t.lang.name / t.name, target_dir, cargo_timeout)
        ok = g.status == "pass"
        bad += 0 if ok else 1
        print(f"  {'✅' if ok else '❌'} {t.key:<22} {g.passed}/{g.total} "
              f"tests ({g.cargo_s:.1f}s)")
        if not ok:
            print("     " + g.detail.strip()[-800:].replace("\n", "\n     "))
    print()
    return bad


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def machine_info() -> str:
    rc, out, _, _ = run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"], ROOT, 5)
    cpu = out.strip() if rc == 0 else "?"
    rc, out, _, _ = run_cmd(["sysctl", "-n", "hw.memsize"], ROOT, 5)
    ram = f"{int(out.strip()) / 1e9:.0f} Go" if rc == 0 and out.strip().isdigit() else "?"
    return f"{cpu}, {ram} RAM"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="",
                    help="liste séparée par des virgules. Un nom nu = modèle Ollama ; "
                         "préfixe `claude:` = via le CLI Claude Code (ex: claude:opus)")
    ap.add_argument("--tasks", default="",
                    help="ex: rle,lru ou rust/rle,python/asn1_ber (défaut : toutes)")
    ap.add_argument("--lang", default="", help="rust, python, ou les deux (défaut)")
    ap.add_argument("--modes", default="direct,agentic")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--task-timeout", type=float, default=600.0,
                    help="budget par (tâche, mode) en secondes ; au-delà on tue (défaut 600)")
    ap.add_argument("--cargo-timeout", type=float, default=120.0)
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--keep-alive", default="15m")
    ap.add_argument("--agent-protocol", default="auto", choices=["auto", "tools", "text"])
    ap.add_argument("--self-test", action="store_true",
                    help="vérifie les tests cachés avec les solutions de référence puis sort")
    args = ap.parse_args()

    if not args.host.startswith("http"):
        args.host = "http://" + args.host

    langs = [l.strip() for l in args.lang.split(",") if l.strip()] or None
    if langs and set(langs) - set(LANGS):
        sys.exit(f"langages inconnus : {', '.join(sorted(set(langs) - set(LANGS)))}")
    tasks = load_tasks([t for t in args.tasks.split(",") if t] or None, langs)
    RUNS_DIR.mkdir(exist_ok=True)
    target_dir = RUNS_DIR / "_target"

    if any(t.lang.name == "rust" for t in tasks) and not shutil.which("cargo"):
        sys.exit("cargo introuvable dans le PATH.")

    if args.self_test:
        return 1 if self_test(tasks, target_dir, args.cargo_timeout) else 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        sys.exit("indique au moins un modèle : --models qwen3.6:35b-mlx")
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    client = Ollama(args.host, args.num_ctx, args.temperature, args.seed, args.keep_alive)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / stamp
    out_dir.mkdir(parents=True)

    config = {
        "machine": machine_info(),
        "host": args.host,
        "models": models,
        "tasks": [t.key for t in tasks],
        "modes": modes,
        "task_timeout": args.task_timeout,
        "cargo_timeout": args.cargo_timeout,
        "max_turns": args.max_turns,
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "seed": args.seed,
        "agent_protocol": args.agent_protocol,
    }
    print(f"Sortie : {out_dir}\nMachine : {config['machine']}\n")

    results: list[Result] = []
    for model in models:
        is_cli = model.startswith(CLI_PREFIX)
        if is_cli:
            cli_model = model[len(CLI_PREFIX):]
            if not shutil.which("claude"):
                print(f"   💥 CLI `claude` introuvable pour {model}\n")
                continue
            print(f"── {model} via le CLI Claude Code (auth abonnement)\n")
        else:
            print(f"── chargement de {model} …", flush=True)
            try:
                load_s = client.warmup(model)
            except OllamaError as exc:
                print(f"   💥 {exc}\n")
                continue
            print(f"   prêt en {load_s:.1f}s\n")

        for task in tasks:
            for mode in modes:
                slug = f"{model}__{task.key}__{mode}".replace(":", "_").replace("/", "-")
                workdir = out_dir / slug
                workdir.mkdir(parents=True, exist_ok=True)
                print(f"▶ {model} · {task.key} · {mode} …", end="", flush=True)
                deadline = Deadline(args.task_timeout)
                if is_cli and mode == "direct":
                    r = run_direct_cli(cli_model, task, workdir, target_dir,
                                       deadline, args.cargo_timeout)
                elif is_cli:
                    r = run_agentic_cli(cli_model, task, workdir, target_dir, deadline,
                                        args.cargo_timeout, args.max_turns)
                elif mode == "direct":
                    r = run_direct(client, model, task, workdir, target_dir,
                                   deadline, args.cargo_timeout)
                else:
                    r = run_agentic(client, model, task, workdir, target_dir, deadline,
                                    args.cargo_timeout, args.max_turns, args.agent_protocol)
                results.append(r)
                print(f" {STATUS_ICON.get(r.status, r.status)} "
                      f"{r.passed}/{r.total} en {r.wall_s:.0f}s "
                      f"({r.gen_tokens} tok, {r.tok_s:.1f} tok/s, {r.turns} tour(s))",
                      flush=True)
                # rapport incrémental : on ne perd rien si on interrompt
                report(results, out_dir, config)

        if not is_cli and shutil.which("ollama"):
            # décharge les poids : plusieurs gros modèles ne tiennent pas
            # ensemble en RAM, et l'éviction automatique fausserait les temps.
            run_cmd(["ollama", "stop", model], ROOT, 60)
        print()

    text = report(results, out_dir, config)
    if "## Synthèse" in text:
        summary = "## Synthèse" + text.split("## Synthèse", 1)[1].split("## Échecs")[0]
        print("\n" + summary)
    print(f"Rapport complet : {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
