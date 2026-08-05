#!/usr/bin/env python3
"""
Benchmark de LLM sur des tâches de codage, en Rust et en Python.

Trois backends :
  - Ollama          : modèle local, API native (nom nu, ou préfixe `ollama:`).
  - LiteLLM         : proxy ou endpoint OpenAI-compatible (préfixe `litellm:`),
                      donc n'importe quel fournisseur routé par LiteLLM.
  - Claude Code CLI : préfixe `claude:`, auth par abonnement.

Deux modes d'évaluation :
  - direct    : un seul appel, le modèle rend le fichier d'un coup (pass@1).
  - agentique : boucle outillée (write_file / read_file / run_command), le
                modèle compile, teste et itère jusqu'à se déclarer satisfait.

Dans les deux cas la note finale vient d'une suite de tests *cachée* que le
modèle ne voit jamais, exécutée dans une copie propre du projet.

Usage :
    python3 bench.py --self-test
    python3 bench.py --models qwen3.6:35b-mlx
    python3 bench.py --models litellm:gpt-4o-mini --litellm-base-url http://localhost:4000
    python3 bench.py --models claude:opus --lang python
    python3 bench.py --models a,b --tasks rust/rle,python/asn1_ber --modes direct
    python3 bench.py --models claude:haiku --tasks python/rle -v   # trace les échanges
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shlex
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
# sous-dossier d'une tâche contenant les jeux de données à analyser ; recopié tel
# quel à la racine du projet, en mode direct comme en mode agentique
DATA_DIR = "data"

CARGO_TOML = """[package]
name = "task"
version = "0.1.0"
edition = "2021"

[lib]
path = "src/lib.rs"

# Empêche cargo de remonter vers un workspace parent.
[workspace]
"""

CMAKELISTS = """cmake_minimum_required(VERSION 3.16)
project(task C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Debug)
endif()

add_compile_options(-Wall -Wextra -g)

# Les erreurs mémoire et les UB doivent faire échouer le test, pas passer.
if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
  set(SAN -fsanitize=address,undefined -fno-sanitize-recover=undefined
          -fno-omit-frame-pointer)
  add_compile_options(${SAN})
  add_link_options(${SAN})
endif()

file(GLOB TASK_SOURCES CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/src/*.c")
add_library(task STATIC ${TASK_SOURCES})
target_include_directories(task PUBLIC "${CMAKE_SOURCE_DIR}/src")

enable_testing()
file(GLOB TEST_SOURCES CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/tests/*.c")
foreach(test_src ${TEST_SOURCES})
  get_filename_component(test_name ${test_src} NAME_WE)
  add_executable(${test_name} ${test_src})
  target_link_libraries(${test_name} PRIVATE task)
  target_include_directories(${test_name} PRIVATE "${CMAKE_SOURCE_DIR}/tests")
  add_test(NAME ${test_name} COMMAND ${test_name})
endforeach()
"""

# Micro-runner d'assertions déposé dans tests/, pour la suite cachée comme pour
# les tests que le modèle écrit lui-même. Format de sortie calqué sur `cargo
# test`, ce qui permet de réutiliser les mêmes expressions rationnelles.
C_HARNESS_H = r"""/* Micro-harnais de test — fourni par le benchmark, ne pas modifier. */
#ifndef TASK_TEST_HARNESS_H
#define TASK_TEST_HARNESS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void (*th_fn)(void);

static struct { const char *name; th_fn fn; } th_reg[512];
static int th_count;
static int th_current_failed;

static void th_register(const char *name, th_fn fn) {
    if (th_count < (int)(sizeof th_reg / sizeof th_reg[0])) {
        th_reg[th_count].name = name;
        th_reg[th_count].fn = fn;
        th_count++;
    }
}

/* TEST(nom) { ... } : la fonction s'enregistre toute seule au démarrage. */
#define TEST(name)                                                            \
    static void th_test_##name(void);                                         \
    __attribute__((constructor)) static void th_reg_##name(void) {            \
        th_register(#name, th_test_##name);                                   \
    }                                                                         \
    static void th_test_##name(void)

__attribute__((unused))
static void th_fail(const char *file, int line, const char *what) {
    th_current_failed = 1;
    printf("FAILED\n    %s:%d: %s\n", file, line, what);
}

#define TH_FAILF(...)                                                         \
    do {                                                                      \
        th_current_failed = 1;                                                \
        printf("FAILED\n    %s:%d: ", __FILE__, __LINE__);                    \
        printf(__VA_ARGS__);                                                  \
        printf("\n");                                                         \
        return;                                                               \
    } while (0)

#define CHECK(cond)                                                           \
    do {                                                                      \
        if (!(cond)) { th_fail(__FILE__, __LINE__, #cond); return; }           \
    } while (0)

#define CHECK_INT_EQ(got, want)                                               \
    do {                                                                      \
        long long th_g = (long long)(got), th_w = (long long)(want);          \
        if (th_g != th_w)                                                     \
            TH_FAILF("%s == %s : obtenu %lld, attendu %lld",                  \
                     #got, #want, th_g, th_w);                                \
    } while (0)

#define CHECK_UINT_EQ(got, want)                                              \
    do {                                                                      \
        unsigned long long th_g = (unsigned long long)(got);                  \
        unsigned long long th_w = (unsigned long long)(want);                 \
        if (th_g != th_w)                                                     \
            TH_FAILF("%s == %s : obtenu %llu, attendu %llu",                  \
                     #got, #want, th_g, th_w);                                \
    } while (0)

#define CHECK_DBL_EQ(got, want, eps)                                          \
    do {                                                                      \
        double th_g = (double)(got), th_w = (double)(want);                   \
        double th_d = th_g - th_w;                                            \
        if (th_d < 0) th_d = -th_d;                                           \
        if (!(th_d <= (double)(eps)))                                         \
            TH_FAILF("%s == %s : obtenu %.17g, attendu %.17g",                \
                     #got, #want, th_g, th_w);                                \
    } while (0)

#define CHECK_STR_EQ(got, want)                                               \
    do {                                                                      \
        const char *th_g = (got), *th_w = (want);                             \
        if (th_g == NULL || th_w == NULL || strcmp(th_g, th_w) != 0)          \
            TH_FAILF("%s : obtenu \"%s\", attendu \"%s\"", #got,              \
                     th_g ? th_g : "(null)", th_w ? th_w : "(null)");         \
    } while (0)

#define CHECK_MEM_EQ(got, want, n)                                            \
    do {                                                                      \
        const void *th_g = (got), *th_w = (want);                             \
        size_t th_n = (size_t)(n);                                            \
        if (th_g == NULL || th_w == NULL || memcmp(th_g, th_w, th_n) != 0)    \
            TH_FAILF("%s : %zu octets différents de %s", #got, th_n, #want);  \
    } while (0)

#define CHECK_NULL(p)                                                         \
    do {                                                                      \
        if ((p) != NULL) TH_FAILF("%s devait être NULL", #p);                 \
    } while (0)

#define CHECK_NOT_NULL(p)                                                     \
    do {                                                                      \
        if ((p) == NULL) TH_FAILF("%s ne devait pas être NULL", #p);          \
    } while (0)

int main(void) {
    int passed = 0, failed = 0;
    /* sortie non tamponnée : un crash ne doit pas avaler les lignes déjà écrites */
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("\nrunning %d tests\n", th_count);
    for (int i = 0; i < th_count; i++) {
        printf("test %s ... ", th_reg[i].name);
        th_current_failed = 0;
        th_reg[i].fn();
        if (th_current_failed) {
            failed++;
        } else {
            passed++;
            printf("ok\n");
        }
    }
    printf("\ntest result: %s. %d passed; %d failed\n",
           failed ? "FAILED" : "ok", passed, failed);
    return failed ? 1 : 0;
}

#endif /* TASK_TEST_HARNESS_H */
"""

PY = sys.executable or "python3"

# --------------------------------------------------------------------------- #
# Trace verbeuse (-v / -vv)
# --------------------------------------------------------------------------- #

# 0 : silencieux (défaut) — 1 : prompts, réponses, outils demandés et leurs
# résultats — 2 : en plus, le contexte complet renvoyé à chaque tour, les
# raisonnements et aucune troncature.
VERBOSE = 0
VERBOSE_CLIP = 1500  # caractères par bloc à -v ; -vv n'en coupe aucun


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if sys.stdout.isatty() else text


def vclip(text: str) -> str:
    """Coupe au milieu : le début et la fin d'un bloc sont les plus parlants."""
    if VERBOSE >= 2 or len(text) <= VERBOSE_CLIP:
        return text
    half = VERBOSE_CLIP // 2
    return (f"{text[:half]}\n[…{len(text) - VERBOSE_CLIP} caractères coupés, "
            f"-vv pour tout voir…]\n{text[-half:]}")


def vsection(label: str, body: str = "", level: int = 1) -> None:
    """Affiche un bloc encadré, si la verbosité demandée est atteinte."""
    if VERBOSE < level or not (body or "").strip():
        return
    print(_dim(f"  ┌─ {label} " + "─" * max(3, 67 - len(label))))
    for line in vclip(body.rstrip()).splitlines():
        print(_dim("  │ ") + line)
    print(_dim("  └" + "─" * 70), flush=True)


def vline(text: str, level: int = 1) -> None:
    if VERBOSE >= level:
        print(_dim(f"  · {text}"), flush=True)


def vmessages(messages: list, label: str = "prompt", level: int = 1) -> None:
    """Affiche les messages tels qu'ils partent vers le modèle."""
    if VERBOSE < level:
        return
    for msg in messages:
        body = msg.get("content") or ""
        if not isinstance(body, str):  # contenu structuré éventuel
            body = json.dumps(body, ensure_ascii=False, indent=2)
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            body += f"\n[appel d'outil] {fn.get('name')}({fn.get('arguments')})"
        vsection(f"{label} · {msg.get('role', '?')}", body, level)


def vtools(tools: list | None, level: int = 1) -> None:
    """Affiche les outils déclarés au modèle (schéma résumé)."""
    if VERBOSE < level or not tools:
        return
    lines = []
    for t in tools:
        fn = t.get("function") or {}
        props = (fn.get("parameters") or {}).get("properties") or {}
        lines.append(f"{fn.get('name')}({', '.join(props)}) — {fn.get('description', '')}")
    vsection("outils déclarés", "\n".join(lines), level)


def vcall(name: str, args: dict, level: int = 1) -> None:
    """Affiche l'outil demandé par le modèle et ses arguments."""
    if VERBOSE < level:
        return
    vsection(f"outil demandé · {name or '?'}",
             json.dumps(args or {}, ensure_ascii=False, indent=2), level)


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
    except Exception as exc:
        return 127, "", f"[harness] {type(exc).__name__}: {exc}", time.monotonic() - t0, False


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
    except Exception as exc:
        return 127, f"[harness] {type(exc).__name__}: {exc}", time.monotonic() - t0, False


# --------------------------------------------------------------------------- #
# Clients LLM (streaming, pour pouvoir couper net sur deadline)
# --------------------------------------------------------------------------- #


class LlmError(RuntimeError):
    pass


class OllamaError(LlmError):
    pass


class LiteLLMError(LlmError):
    pass


class ToolsUnsupported(LlmError):
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
    cost_usd: float = 0.0
    aborted: bool = False
    abort_reason: str = ""


def read_timeout(budget: float) -> float:
    """Timeout *de lecture* d'un flux : il s'applique à chaque bloc reçu.

    Pas de plafond en dur : avec des outils, un backend peut ne rien émettre
    tant que l'appel n'est pas complet (le parseur gemma4 d'Ollama accumule
    tout le bloc et ne le rend qu'au dernier chunk), si bien que le premier
    octet arrive après toute la génération. Un plafond plus court que le budget
    transformerait ce silence légitime en erreur de transport ; le garde-fou,
    c'est le budget de la tâche.
    """
    return max(5.0, budget)


def note_abort(reply: LlmReply, exc: BaseException, timeout: float) -> None:
    """Flux coupé : on garde ce qui est déjà arrivé et on dit pourquoi.

    Le timeout d'`urlopen` étant un timeout de lecture, un serveur qui met trop
    longtemps à sortir le token suivant lève TimeoutError ici, au milieu de
    l'itération sur la réponse — pas au moment de la requête.
    """
    reply.aborted = True
    if isinstance(exc, TimeoutError):
        reply.abort_reason = (f"aucune donnée du serveur pendant {timeout:.0f}s "
                              f"(timeout de lecture)")
    else:
        reply.abort_reason = f"flux interrompu : {type(exc).__name__}: {exc}"


class Ollama:
    def __init__(self, host: str, num_ctx: int, temperature: float, seed: int, keep_alive: str,
                 num_predict: int):
        self.host = host.rstrip("/")
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.seed = seed
        self.keep_alive = keep_alive
        self.num_predict = num_predict

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
                # filet contre les générations qui partent en boucle : sans
                # plafond, un modèle peut remplir tout le contexte sans jamais
                # rendre la main (vu en agentique, dans un appel d'outil).
                "num_predict": self.num_predict,
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
        timeout = read_timeout(budget)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if "does not support tools" in body or "tools" in body and exc.code == 400:
                raise ToolsUnsupported(body) from exc
            raise OllamaError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama injoignable sur {self.host} : {exc}") from exc
        except TimeoutError as exc:
            raise OllamaError(f"Ollama n'a pas répondu en {timeout:.0f}s : {exc}") from exc
        except (http.client.HTTPException, OSError) as exc:
            raise OllamaError(f"Ollama {self.host} : {type(exc).__name__}: {exc}") from exc

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
        except (TimeoutError, http.client.IncompleteRead, OSError) as exc:
            note_abort(reply, exc, timeout)
        finally:
            resp.close()  # couper la connexion arrête la génération côté serveur

        reply.wall_s = time.monotonic() - t0
        return reply

    def warmup(self, model: str) -> float:
        """Charge le modèle en mémoire pour ne pas facturer le load au 1er test."""
        t0 = time.monotonic()
        self.chat(model, [{"role": "user", "content": "ok"}], None, budget=180.0)
        return time.monotonic() - t0

    # --- mise en forme des messages de la boucle agentique ------------------ #

    def assistant_msg(self, reply: LlmReply) -> dict:
        msg = {"role": "assistant", "content": reply.content}
        if reply.tool_calls:
            msg["tool_calls"] = reply.tool_calls[:1]
        return msg

    def tool_msg(self, call: dict, name: str, output: str) -> dict:
        return {"role": "tool", "content": output,
                "tool_name": (call.get("function") or {}).get("name") or name}


class LiteLLM:
    """Client OpenAI-compatible : proxy LiteLLM, ou tout endpoint `/chat/completions`.

    Même interface que `Ollama` (chat / warmup rendant un `LlmReply`), ce qui
    permet de réutiliser tels quels les modes direct et agentique.

    Deux différences de mesure à garder en tête :
      - pas de temps de décodage pur exposé par l'API : `eval_s` est la fenêtre
        premier token → dernier token, réseau compris. Ce n'est PAS la même
        définition que le `eval_duration` d'Ollama ;
      - `load_s` n'a pas de sens ici (rien à charger côté client).
    """

    def __init__(self, base_url: str, api_key: str, temperature: float, seed: int,
                 num_predict: int, extra_body: dict | None = None):
        url = base_url.rstrip("/")
        if not url.startswith("http"):
            url = "http://" + url
        # Le proxy LiteLLM sert les deux, mais /v1 est ce qu'attendent aussi les
        # endpoints OpenAI-compatibles tiers.
        self.base_url = url if url.endswith("/v1") else url + "/v1"
        self.api_key = api_key
        self.temperature = temperature
        self.seed = seed
        self.num_predict = num_predict
        self.extra_body = extra_body or {}

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _post(self, path: str, payload: dict, timeout: float):
        """POST streamé. `timeout` est un timeout de lecture, pas un budget total."""
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode(),
            headers=self._headers(),
        )
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            low = body.lower()
            if exc.code in (400, 404, 422) and (
                    "tool" in low or "function call" in low) and "tool_call_id" not in low:
                raise ToolsUnsupported(body) from exc
            raise LiteLLMError(f"HTTP {exc.code}: {body[:800]}") from exc
        except urllib.error.URLError as exc:
            raise LiteLLMError(f"endpoint LiteLLM injoignable sur {self.base_url} : {exc}") from exc
        except TimeoutError as exc:
            raise LiteLLMError(
                f"{self.base_url} n'a pas répondu en {timeout:.0f}s : {exc}") from exc
        except (http.client.HTTPException, OSError) as exc:
            # connexion coupée par le proxy, réponse tronquée… : ne doit pas
            # faire tomber le run entier, juste marquer ce couple (tâche, mode).
            raise LiteLLMError(f"{self.base_url} : {type(exc).__name__}: {exc}") from exc

    def chat(self, model: str, messages: list, tools: list | None, budget: float) -> LlmReply:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            # sans ça, la plupart des backends omettent l'usage en streaming
            "stream_options": {"include_usage": True},
            "temperature": self.temperature,
            # même filet anti-boucle que `num_predict` côté Ollama
            "max_tokens": self.num_predict,
        }
        if self.seed:
            payload["seed"] = self.seed
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        payload.update(self.extra_body)

        reply = LlmReply()
        t0 = time.monotonic()
        timeout = read_timeout(budget)
        try:
            resp = self._post("/chat/completions", payload, timeout)
        except LiteLLMError as exc:
            if "stream_options" not in str(exc):
                raise
            # backend qui ne connaît pas l'option : on repart sans, quitte à
            # perdre le compte de tokens.
            payload.pop("stream_options")
            resp = self._post("/chat/completions", payload, timeout)
        # Coût annoncé par le proxy quand il le connaît d'avance ; sinon il peut
        # encore arriver dans l'`usage` de fin de flux (voir plus bas).
        reply.cost_usd = _float_header(resp, "x-litellm-response-cost")

        calls: dict[int, dict] = {}
        t_last = 0.0
        try:
            for raw in resp:
                if time.monotonic() - t0 > budget:
                    reply.aborted = True
                    break
                line = raw.decode(errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(chunk, dict) and chunk.get("error"):
                    err = chunk["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    if "tool" in str(msg).lower():
                        raise ToolsUnsupported(str(msg))
                    raise LiteLLMError(str(msg))

                usage = chunk.get("usage") or {}
                if usage:
                    reply.prompt_tokens = usage.get("prompt_tokens", 0) or reply.prompt_tokens
                    reply.gen_tokens = usage.get("completion_tokens", 0) or reply.gen_tokens
                    reply.cost_usd = reply.cost_usd or float(usage.get("cost") or 0.0)

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content") or ""
                thought = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if piece or thought:
                    now = time.monotonic() - t0
                    if not reply.ttft_s:
                        reply.ttft_s = now
                    t_last = now
                reply.content += piece
                reply.thinking += thought

                for frag in delta.get("tool_calls") or []:
                    idx = frag.get("index")
                    if idx is None:
                        idx = len(calls)
                    slot = calls.setdefault(idx, {"id": "", "type": "function",
                                                  "function": {"name": "", "arguments": ""}})
                    if frag.get("id"):
                        slot["id"] = frag["id"]
                    fn = frag.get("function") or {}
                    if fn.get("name") and not slot["function"]["name"]:
                        slot["function"]["name"] = fn["name"]
                    # les arguments arrivent en morceaux de JSON à recoller
                    slot["function"]["arguments"] += fn.get("arguments") or ""
                    if not reply.ttft_s:
                        reply.ttft_s = time.monotonic() - t0
                    t_last = time.monotonic() - t0
        except (TimeoutError, http.client.IncompleteRead, OSError) as exc:
            note_abort(reply, exc, timeout)
        finally:
            resp.close()  # couper la connexion arrête la génération côté serveur

        reply.tool_calls = [calls[k] for k in sorted(calls)]
        reply.wall_s = time.monotonic() - t0
        # fenêtre de décodage observée ; à défaut, le temps hors TTFT
        reply.eval_s = max(t_last - reply.ttft_s, 0.0) or max(reply.wall_s - reply.ttft_s, 0.0)
        # gen_tokens reste à 0 si le backend n'a pas renvoyé d'usage : mieux vaut
        # une colonne vide qu'une estimation inventée dans un benchmark.
        return reply

    def warmup(self, model: str) -> float:
        """Vérifie tôt que l'endpoint répond et que le modèle existe."""
        t0 = time.monotonic()
        self.chat(model, [{"role": "user", "content": "ok"}], None, budget=60.0)
        return time.monotonic() - t0

    # --- mise en forme des messages de la boucle agentique ------------------ #

    def assistant_msg(self, reply: LlmReply) -> dict:
        msg = {"role": "assistant"}
        if reply.content or not reply.tool_calls:
            msg["content"] = reply.content
        if reply.tool_calls:
            msg["tool_calls"] = reply.tool_calls[:1]
        return msg

    def tool_msg(self, call: dict, name: str, output: str) -> dict:
        return {"role": "tool", "content": output,
                "tool_call_id": call.get("id") or name}


def _float_header(resp, name: str) -> float:
    try:
        return float(resp.headers.get(name) or 0.0)
    except (AttributeError, TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# Langages : tout ce qui diffère entre un projet cargo et un projet Python
# --------------------------------------------------------------------------- #

RUST_TEST_LINE = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+(ok|FAILED|ignored)", re.M)
RUST_RESULT = re.compile(r"test result:\s+(ok|FAILED)\.\s+(\d+) passed;\s+(\d+) failed", re.M)
PY_OK_LINE = re.compile(r"\.\.\. ok\s*$", re.M)
PY_RAN = re.compile(r"^Ran (\d+) tests?", re.M)
C_RUNNING = re.compile(r"^running \d+ tests?", re.M)


class Lang:
    name: str
    entry: str          # le fichier que le modèle doit produire
    test_path: str      # où le harnais dépose les tests cachés
    fences: tuple       # langages de bloc markdown acceptés
    label: str          # nom affiché dans les prompts
    layout: str         # description de l'arborescence, pour les prompts
    test_cmd: str       # commande que l'agent est censé lancer
    allowed_cmds: str   # description de l'allowlist, pour les prompts
    write_paths: str    # chemins que l'agent a le droit d'écrire, pour les prompts

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
    write_paths = "src/*.rs, tests/*.rs"

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
    write_paths = "*.py à la racine"

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


class CLang(Lang):
    name = "c"
    entry = "src/solution.c"
    test_path = "tests/hidden.c"
    fences = ("c", "cpp")  # certains modèles étiquettent leur C en ```cpp
    label = "C"
    layout = ("    CMakeLists.txt    (fourni, ne pas modifier : compile src/*.c en "
              "bibliothèque `task`\n"
              "                       et un exécutable par fichier tests/*.c)\n"
              "    src/solution.c    (à toi de le remplir)\n"
              "    src/*.h           (tu peux ajouter tes propres en-têtes)\n"
              "    tests/harness.h   (fourni : macros TEST(nom) et CHECK_*)\n"
              "    tests/*.c         (tu peux y écrire tes propres tests)\n"
              "\n"
              "  Configure une fois avec `cmake -S . -B build`, puis compile avec\n"
              "  `cmake --build build` et lance `ctest --test-dir build "
              "--output-on-failure`.\n"
              "  Compilation en C11 avec -Wall -Wextra et "
              "-fsanitize=address,undefined : une\n"
              "  erreur mémoire ou un comportement indéfini fait échouer le test.")
    test_cmd = "ctest --test-dir build --output-on-failure"
    allowed_cmds = ("cmake -S . -B build, cmake --build build, "
                    "ctest --test-dir build --output-on-failure, ./build/<exécutable>")
    write_paths = "src/*.c, src/*.h, tests/*.c, tests/*.h"

    def scaffold(self, project, source):
        (project / "src").mkdir(parents=True, exist_ok=True)
        (project / "tests").mkdir(parents=True, exist_ok=True)
        (project / "CMakeLists.txt").write_text(CMAKELISTS)
        (project / "tests" / "harness.h").write_text(C_HARNESS_H)
        (project / "src" / "solution.c").write_text(source or "/* Écris ton implémentation ici. */\n")

    def extras(self, project):
        src = project / "src"
        if not src.exists():
            return []
        return [p for p in sorted(src.iterdir())
                if p.suffix in (".c", ".h") and p.name != "solution.c"]

    def collect(self, project):
        f = project / "src" / "solution.c"
        return f.read_text() if f.exists() else ""

    def pre_argv(self):
        return [["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Debug"],
                ["cmake", "--build", "build", "--target", "hidden"]]

    def tests_argv(self):
        return ["./build/hidden"]

    def count_tests(self, tests_src):
        return len(re.findall(r"^\s*TEST\(", tests_src, re.M))

    def write_ok(self, rel):
        return (len(rel.parts) == 2 and rel.parts[0] in ("src", "tests")
                and rel.suffix in (".c", ".h") and rel.name != "harness.h")

    def normalise_cmd(self, parts):
        if not parts:
            return None
        if parts[0] == "cmake":
            if "--build" in parts:
                return ["cmake", "--build", "build"] + parts[parts.index("--build") + 2:]
            return ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Debug"]
        if parts[0] == "ctest":
            return ["ctest", "--test-dir", "build", "--output-on-failure"]
        # lancement direct d'un exécutable produit par le build
        exe = parts[0].removeprefix("./")
        if exe.startswith("build/") and "/" not in exe[len("build/"):]:
            return ["./" + exe] + parts[1:]
        return None

    def parse(self, out, rc, n_tests):
        seen = len(RUST_TEST_LINE.findall(out))
        m = RUST_RESULT.search(out)
        if m:
            return True, int(m.group(2)), max(n_tests, seen, int(m.group(2)) + int(m.group(3)))
        if C_RUNNING.search(out):
            # binaire lancé puis interrompu (segfault, abort d'un sanitizer) :
            # ce n'est pas une erreur de compilation, c'est un échec de test
            return True, len(re.findall(r"\.\.\.\s+ok$", out, re.M)), n_tests
        return False, 0, n_tests


LANGS = {l.name: l for l in (RustLang(), PythonLang(), CLang())}


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


def install_data(task: "Task", project: Path) -> None:
    """Recopie les jeux de données de la tâche dans `<projet>/data/`."""
    if not task.data_files:
        return
    dest_dir = project / DATA_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in task.data_files:
        shutil.copyfile(src, dest_dir / src.name)


def project_layout(task: "Task") -> str:
    """Arborescence annoncée à l'agent, augmentée des données de la tâche."""
    if not task.data_files:
        return task.lang.layout
    names = ", ".join(f"{DATA_DIR}/{p.name}" for p in task.data_files)
    return (f"{task.lang.layout}\n"
            f"    {DATA_DIR + '/':<18}(fourni, à analyser, à ne pas modifier : {names})")


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
    install_data(task, project)
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
    data_files: list = field(default_factory=list)

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
            data_dir = d / DATA_DIR
            tasks.append(Task(
                name=d.name,
                lang=lang,
                spec=(d / "spec.md").read_text(),
                tests_src=tests_src,
                reference=reference,
                n_tests=lang.count_tests(tests_src),
                data_files=(sorted(p for p in data_dir.iterdir() if p.is_file())
                            if data_dir.is_dir() else []),
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
          "python": re.compile(r"^(def|class)\s+\w+", re.M),
          # une définition de fonction ou un #include en début de ligne
          "c": re.compile(r"^(#include|[A-Za-z_][\w \t*]*\**\w+\s*\([^;]*\)\s*\{)", re.M)}


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
{data}
---

Rends TON code dans UN SEUL bloc ```{fence} contenant l'intégralité du fichier
`{entry}`. Pas de point d'entrée exécutable, pas de dépendance externe, pas de
commentaire d'introduction en dehors du bloc de code. Le code doit marcher tel quel."""

# en mode direct le modèle n'a pas de système de fichiers : les données sont
# inlinées dans le prompt, sinon la tâche d'analyse est ingagnable
MAX_DATA_INLINE = 20000
DATA_FENCE = {".json": "json", ".csv": "csv", ".jsonl": "json"}


def inline_data(task: Task) -> str:
    """Bloc de données joint au prompt direct (vide si la tâche n'en a pas)."""
    if not task.data_files:
        return ""
    parts = ["\n---\n\nContenu des fichiers présents dans le projet :\n"]
    for p in task.data_files:
        text = p.read_text(errors="replace")
        if len(text) > MAX_DATA_INLINE:
            text = text[:MAX_DATA_INLINE] + "\n[...tronqué...]"
        parts.append(f"`{DATA_DIR}/{p.name}` :\n\n```{DATA_FENCE.get(p.suffix, '')}\n{text}\n```\n")
    return "\n".join(parts)


def direct_messages(task: Task) -> tuple[str, str]:
    return (
        DIRECT_SYSTEM.format(label=task.lang.label),
        DIRECT_USER.format(spec=task.spec, data=inline_data(task),
                           fence=task.lang.fences[0], entry=task.lang.entry),
    )


def run_direct(client: Ollama | LiteLLM, model: str, task: Task, workdir: Path,
               target_dir: Path, deadline: Deadline, cargo_timeout: float,
               label: str = "") -> "Result":
    res = Result(model=label or model, task=task.key, mode="direct", protocol="single-shot")
    system, user = direct_messages(task)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    vmessages(messages)
    try:
        reply = client.chat(model, messages, None, budget=deadline.remaining)
    except LlmError as exc:
        res.status = "error"
        res.detail = str(exc)[:500]
        res.wall_s = deadline.elapsed
        return res

    res.turns = 1
    res.absorb(reply)
    vsection("réflexion", reply.thinking, level=2)
    vsection("réponse", reply.content)
    (workdir / "raw_reply.md").write_text(reply.thinking + "\n\n" + reply.content)

    if reply.aborted or deadline.expired:
        res.status = "timeout"
        res.detail = (reply.abort_reason
                      or f"budget de {deadline.limit:.0f}s dépassé pendant la génération")
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
 3. si un test échoue, analyse d'abord si l'erreur vient du code ou d'une erreur de logique dans ton test (simule l'exécution à la main) ;
 4. corrige le code ou le test, et recommence ;
 5. quand tout marche et que tes tests passent, appelle `finish`.

Conseils pour les tests :
 - Adopte une approche incrémentale : commence par des tests atomiques simples avant de créer des scénarios complexes.
 - Si tu échoues à corriger le même test plusieurs fois, remets en question la validité du test lui-même.

Règles : bibliothèque standard uniquement, pas de point d'entrée exécutable, pas
de dépendance externe.
Ton code sera ensuite noté par une suite de tests cachée conforme à la
spécification : respecte scrupuleusement les signatures demandées.
Tu as {max_turns} tours maximum. N'appelle qu'un outil à la fois."""

AGENT_USER = "Voici la tâche à réaliser.\n\n{spec}\n\nCommence maintenant."

def build_tools(lang: Lang) -> list:
    tools = json.loads(json.dumps(TOOLS))  # copie profonde
    fn = {t["function"]["name"]: t["function"] for t in tools}
    fn["write_file"]["description"] = (
        f"Écrit (ou écrase) un fichier du projet. Chemins autorisés : {lang.write_paths}")
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


def run_agentic(client: Ollama | LiteLLM, model: str, task: Task, workdir: Path,
                target_dir: Path, deadline: Deadline, cargo_timeout: float, max_turns: int,
                protocol: str, label: str = "") -> "Result":
    res = Result(model=label or model, task=task.key, mode="agentic", protocol=protocol)
    lang = task.lang
    project = workdir / "agent"
    lang.scaffold(project, "")
    install_data(task, project)
    box = Sandbox(project, lang, target_dir, cargo_timeout)
    tools = build_tools(lang)
    text_proto = TEXT_PROTOCOL.format(entry=lang.entry, fence=lang.fences[0],
                                      test_cmd=lang.test_cmd)

    use_tools = protocol in ("tools", "auto")
    system = AGENT_SYSTEM.format(max_turns=max_turns, label=lang.label,
                                 layout=project_layout(task),
                                 entry=lang.entry, test_cmd=lang.test_cmd)
    if not use_tools:
        system += "\n\n" + text_proto
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": AGENT_USER.format(spec=task.spec)},
    ]
    transcript = []
    vtools(tools if use_tools else None)
    vmessages(messages)

    for turn in range(1, max_turns + 1):
        if deadline.expired:
            res.status = "timeout"
            res.detail = f"budget de {deadline.limit:.0f}s dépassé au tour {turn}"
            break
        vline(f"tour {turn}/{max_turns} — protocole {res.protocol}")
        # à -vv, le contexte complet tel qu'il repart à chaque tour
        vmessages(messages, label=f"contexte tour {turn}", level=2)
        try:
            reply = client.chat(model, messages, tools if use_tools else None,
                                budget=deadline.remaining)
        except ToolsUnsupported:
            if protocol == "auto":
                # bascule automatique vers le protocole texte
                res.protocol = protocol = "text"
                use_tools = False
                messages[0]["content"] = system + "\n\n" + text_proto
                vline("outils non supportés : bascule sur le protocole texte")
                vsection("nouveau prompt système", messages[0]["content"])
                continue
            res.status = "error"
            res.detail = "le modèle ne supporte pas les outils"
            break
        except LlmError as exc:
            res.status = "error"
            res.detail = str(exc)[:500]
            break

        res.turns = turn
        res.absorb(reply)
        vsection(f"tour {turn} · réflexion", reply.thinking, level=2)
        vsection(f"tour {turn} · réponse", reply.content)
        if use_tools and protocol == "auto" and reply.tool_calls:
            res.protocol = "tools"

        if reply.aborted or deadline.expired:
            res.status = "timeout"
            res.detail = (f"{reply.abort_reason} (tour {turn})" if reply.abort_reason
                          else f"budget de {deadline.limit:.0f}s dépassé pendant la "
                               f"génération (tour {turn})")
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

        messages.append(client.assistant_msg(reply))
        vcall(name, args)

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

        vsection(f"tour {turn} · résultat de {name or '?'}", out)
        res.tool_calls += 1
        transcript.append({
            "turn": turn,
            "action": name or "?",
            "args": {k: (v[:200] if isinstance(v, str) else v) for k, v in args.items()},
            "result": out[:1500],
        })

        if reply.tool_calls:
            messages.append(client.tool_msg(reply.tool_calls[0], name, out))
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
LITELLM_PREFIX = "litellm:"
OLLAMA_PREFIX = "ollama:"

AGENT_SYSTEM_CLI = """Tu es un agent de développement {label} autonome. Tu travailles dans ce projet :

{root}
{layout}

Ton répertoire de travail courant est déjà `{root}` : n'utilise que des chemins
relatifs (`{entry}`), jamais de chemin absolu — toute écriture hors de ce
répertoire est refusée.

Ta méthode :
 1. écris `{entry}` avec l'outil Write ;
 2. lance `{test_cmd}` avec l'outil Bash ;
 3. si un test échoue, analyse d'abord si l'erreur vient du code ou d'une erreur de logique dans ton test (simule l'exécution à la main) ;
 4. corrige le code ou le test, et recommence ;
 5. quand tout marche et que tes tests passent, termine ton tour.

Conseils pour les tests :
 - Adopte une approche incrémentale : commence par des tests atomiques simples avant de créer des scénarios complexes.
 - Si tu échoues à corriger le même test plusieurs fois, remets en question la validité du test lui-même.

Seules les commandes commençant par {bash_prefix} sont autorisées dans Bash.
Règles : bibliothèque standard uniquement, pas de point d'entrée exécutable, pas
de dépendance externe.
Ton code sera ensuite noté par une suite de tests cachée conforme à la
spécification : respecte scrupuleusement les signatures demandées."""

# outil Bash du CLI : préfixes de commande autorisés, par langage
CLI_BASH_ALLOW = {"rust": ("cargo",), "python": (Path(PY).name,), "c": ("cmake", "ctest")}


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
    # En verbeux on demande le flux JSONL : il laisse voir les outils demandés
    # tour par tour, et sa dernière ligne reste l'objet `type: result` attendu
    # par parse_cli_json — les métriques sont donc identiques.
    fmt = (["--output-format", "stream-json", "--verbose"] if VERBOSE
           else ["--output-format", "json"])
    return [
        "claude", "-p",
        "--model", model,
        "--system-prompt", system,
        *fmt,
        "--safe-mode",              # neutralise CLAUDE.md, skills, plugins, hooks
        "--no-session-persistence",
    ]
    # NB : le prompt passe par stdin, jamais en argument positionnel — les options
    # variadiques (`--tools`, `--allowed-tools`) l'avaleraient sinon.


def vcli(argv: list[str], system: str, user: str) -> None:
    """Ce qui part vers le CLI : prompts, outils autorisés, ligne de commande."""
    vsection("prompt système", system)
    vsection("prompt utilisateur", user)
    vsection("commande CLI", " ".join(shlex.quote(a) for a in argv), level=2)


def vcli_stream(stdout: str, level: int = 1) -> None:
    """Rejoue le flux JSONL du CLI : texte de l'assistant et outils demandés."""
    if VERBOSE < level:
        return
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") not in ("assistant", "user"):
            continue
        content = (ev.get("message") or {}).get("content")
        if isinstance(content, str):
            vsection("réponse du CLI", content, level)
            continue
        for block in content or []:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                vsection("réponse du CLI", block.get("text", ""), level)
            elif kind == "thinking":
                vsection("réflexion du CLI", block.get("thinking", ""), level + 1)
            elif kind == "tool_use":
                vcall(block.get("name", "?"), block.get("input") or {}, level)
            elif kind == "tool_result":
                out = block.get("content")
                if isinstance(out, list):
                    out = "\n".join(b.get("text", "") for b in out if isinstance(b, dict))
                vsection("résultat outil", str(out or ""), level)


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
    vcli(argv, system, user)
    rc, out, err, secs, killed = run_cmd_split(argv, cwd, deadline.remaining, stdin_text=user)
    vcli_stream(out)
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
    prefixes = CLI_BASH_ALLOW[lang.name]
    shown = ", ".join(f"`{p}`" for p in prefixes)
    res = Result(model=CLI_PREFIX + model, task=task.key, mode="agentic",
                 protocol=f"claude-code Read/Write/Bash({'+'.join(prefixes)})")
    project = workdir / "agent"
    lang.scaffold(project, "")
    install_data(task, project)

    system = AGENT_SYSTEM_CLI.format(label=lang.label, layout=project_layout(task),
                                     root=project.resolve(), entry=lang.entry,
                                     test_cmd=lang.test_cmd, bash_prefix=shown)
    argv = cli_base_argv(model, system) + [
        "--tools", "Read,Write,Edit,Bash",
        "--allowed-tools", ",".join(f"Bash({p}:*)" for p in prefixes),
        "--disallowed-tools", "WebSearch,WebFetch",
        "--permission-mode", "acceptEdits",
    ]
    user = AGENT_USER.format(spec=task.spec)
    vcli(argv, system, user)
    rc, out, err, secs, killed = run_cmd_split(
        argv, project, deadline.remaining, env=lang.env(target_dir),
        stdin_text=user,
    )
    vcli_stream(out)
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
        self.cost_usd += reply.cost_usd
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
    lines.append("# Benchmark de codage — C, Rust & Python\n")
    lines.append(f"- date : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- machine : {config['machine']}")
    lines.append(f"- budget par (tâche, mode) : {config['task_timeout']:.0f}s "
                 f"(processus tué au-delà)")
    lines.append(f"- num_ctx={config['num_ctx']}, num_predict={config.get('num_predict', '?')}, "
                 f"temperature={config['temperature']}, seed={config['seed']}, "
                 f"tours agentiques max={config['max_turns']}")

    has_cli = any(r.model.startswith(CLI_PREFIX) for r in results)
    has_litellm = any(r.model.startswith(LITELLM_PREFIX) for r in results)
    if has_litellm:
        lines.append(f"- endpoint LiteLLM : {config.get('litellm_base_url', '?')}")
        if config.get("litellm_extra_body"):
            lines.append(f"- corps supplémentaire LiteLLM : "
                         f"`{json.dumps(config['litellm_extra_body'], ensure_ascii=False)}`")
    lines.append("")

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

    if has_litellm:
        cost = sum(r.cost_usd for r in results if r.model.startswith(LITELLM_PREFIX))
        lines.append("> ℹ️ **Lignes `litellm:*`.** Même harnais que les modèles Ollama "
                     "(mêmes prompts, mêmes 4 outils, même boucle) : les deux modes sont "
                     "donc comparables entre `litellm:*` et Ollama. À garder en tête :\n"
                     ">\n"
                     "> - **`tok/s`** est mesuré ici du premier au dernier token, réseau "
                     "compris — pas le décodage pur d'Ollama (`eval_count / eval_duration`). "
                     "Sur un endpoint distant, la latence réseau est dans le dénominateur.\n"
                     "> - Les paramètres d'inférence (quantisation, contexte, batching) "
                     "appartiennent au serveur derrière le proxy : `--num-ctx` ne s'y "
                     "applique pas, utiliser `--litellm-extra-body` si le backend le "
                     "supporte.\n"
                     + (f"> - Coût rapporté par le proxy : **{cost:.4f} $**.\n" if cost else ""))
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


def split_backend(spec: str, default: str) -> tuple[str, str]:
    """`litellm:gpt-4o-mini` → ('litellm', 'gpt-4o-mini'). Sans préfixe : backend par défaut."""
    for prefix, backend in ((CLI_PREFIX, "claude"), (LITELLM_PREFIX, "litellm"),
                            (OLLAMA_PREFIX, "ollama")):
        if spec.startswith(prefix):
            return backend, spec[len(prefix):]
    return default, spec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="",
                    help="liste séparée par des virgules. Préfixes : `ollama:` (défaut), "
                         "`litellm:` (endpoint OpenAI-compatible), `claude:` (CLI Claude Code). "
                         "Ex: qwen3.6:35b-mlx,litellm:gpt-4o-mini,claude:opus")
    ap.add_argument("--tasks", default="",
                    help="ex: rle,lru ou rust/rle,python/asn1_ber (défaut : toutes)")
    ap.add_argument("--lang", default="", help="rust, python, ou les deux (défaut)")
    ap.add_argument("--modes", default="direct,agentic")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--backend", default="ollama", choices=["ollama", "litellm"],
                    help="backend des modèles sans préfixe (défaut : ollama)")
    ap.add_argument("--litellm-base-url",
                    default=os.environ.get("LITELLM_BASE_URL")
                            or os.environ.get("OPENAI_BASE_URL", "http://localhost:4000"),
                    help="URL du proxy LiteLLM ou de tout endpoint OpenAI-compatible "
                         "(défaut : $LITELLM_BASE_URL puis http://localhost:4000)")
    ap.add_argument("--litellm-api-key",
                    default=os.environ.get("LITELLM_API_KEY")
                            or os.environ.get("OPENAI_API_KEY", ""),
                    help="clé envoyée en Bearer (défaut : $LITELLM_API_KEY, sinon $OPENAI_API_KEY)")
    ap.add_argument("--litellm-extra-body", default="",
                    help="JSON fusionné dans le corps de chaque requête, ex: "
                         "'{\"num_ctx\": 16384}' pour un modèle Ollama servi par le proxy")
    ap.add_argument("--task-timeout", type=float, default=600.0,
                    help="budget par (tâche, mode) en secondes ; au-delà on tue (défaut 600)")
    ap.add_argument("--cargo-timeout", type=float, default=120.0)
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--num-predict", type=int, default=8192,
                    help="plafond de tokens générés par réponse ; évite qu'une génération "
                         "en boucle consomme tout le budget (défaut 8192)")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--keep-alive", default="15m")
    ap.add_argument("--agent-protocol", default="auto", choices=["auto", "tools", "text"])
    ap.add_argument("--no-warmup", action="store_true",
                    help="saute l'appel de préchauffage (inutile et facturé sur une API distante)")
    ap.add_argument("--self-test", action="store_true",
                    help="vérifie les tests cachés avec les solutions de référence puis sort")
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="affiche les prompts envoyés au modèle, ses réponses, les outils "
                         "déclarés, ceux qu'il demande et leur résultat ; -vv ajoute le "
                         "contexte complet de chaque tour, les raisonnements, et ne tronque rien")
    args = ap.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    if not args.host.startswith("http"):
        args.host = "http://" + args.host

    try:
        extra_body = json.loads(args.litellm_extra_body) if args.litellm_extra_body else {}
    except json.JSONDecodeError as exc:
        sys.exit(f"--litellm-extra-body : JSON invalide ({exc})")
    if not isinstance(extra_body, dict):
        sys.exit("--litellm-extra-body doit être un objet JSON")

    langs = [l.strip() for l in args.lang.split(",") if l.strip()] or None
    if langs and set(langs) - set(LANGS):
        sys.exit(f"langages inconnus : {', '.join(sorted(set(langs) - set(LANGS)))}")
    tasks = load_tasks([t for t in args.tasks.split(",") if t] or None, langs)
    RUNS_DIR.mkdir(exist_ok=True)
    target_dir = RUNS_DIR / "_target"

    if any(t.lang.name == "rust" for t in tasks) and not shutil.which("cargo"):
        sys.exit("cargo introuvable dans le PATH.")
    if any(t.lang.name == "c" for t in tasks):
        for tool in ("cmake", "ctest"):
            if not shutil.which(tool):
                sys.exit(f"{tool} introuvable dans le PATH.")

    if args.self_test:
        return 1 if self_test(tasks, target_dir, args.cargo_timeout) else 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        sys.exit("indique au moins un modèle : --models qwen3.6:35b-mlx")
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    ollama = Ollama(args.host, args.num_ctx, args.temperature, args.seed, args.keep_alive,
                    args.num_predict)
    litellm = LiteLLM(args.litellm_base_url, args.litellm_api_key, args.temperature,
                      args.seed, args.num_predict, extra_body)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / stamp
    out_dir.mkdir(parents=True)

    config = {
        "machine": machine_info(),
        "host": args.host,
        "backend": args.backend,
        "litellm_base_url": litellm.base_url,
        "litellm_extra_body": extra_body,
        "models": models,
        "tasks": [t.key for t in tasks],
        "modes": modes,
        "task_timeout": args.task_timeout,
        "cargo_timeout": args.cargo_timeout,
        "max_turns": args.max_turns,
        "num_ctx": args.num_ctx,
        "num_predict": args.num_predict,
        "temperature": args.temperature,
        "seed": args.seed,
        "agent_protocol": args.agent_protocol,
    }
    print(f"Sortie : {out_dir}\nMachine : {config['machine']}\n")

    results: list[Result] = []
    for spec in models:
        backend, model = split_backend(spec, args.backend)
        # étiquette portée par les résultats : un nom nu reste un modèle Ollama,
        # pour ne pas casser la comparaison avec les runs précédents.
        label = model if backend == "ollama" else f"{backend}:{model}"
        client = {"ollama": ollama, "litellm": litellm}.get(backend)

        if backend == "claude":
            if not shutil.which("claude"):
                print(f"   💥 CLI `claude` introuvable pour {spec}\n")
                continue
            print(f"── {label} via le CLI Claude Code (auth abonnement)\n")
        else:
            # Ollama : le warm-up charge les poids, pour ne pas facturer le
            # chargement au premier test. LiteLLM : il ne sert qu'à valider tôt
            # l'endpoint, la clé et le nom du modèle.
            where = "LiteLLM " + litellm.base_url if backend == "litellm" else "Ollama"
            if args.no_warmup:
                print(f"── {model} via {where}\n")
            else:
                print(f"── {model} via {where} : préchauffage …", flush=True)
                try:
                    warm_s = client.warmup(model)
                except LlmError as exc:
                    print(f"   💥 {exc}\n")
                    continue
                print(f"   prêt en {warm_s:.1f}s\n")

        for task in tasks:
            for mode in modes:
                slug = f"{label}__{task.key}__{mode}".replace(":", "_").replace("/", "-")
                workdir = out_dir / slug
                workdir.mkdir(parents=True, exist_ok=True)
                # en verbeux les blocs de trace s'intercalent : la ligne d'état
                # ne peut plus rester ouverte en attendant son verdict.
                print(f"▶ {label} · {task.key} · {mode} …",
                      end="\n" if VERBOSE else "", flush=True)
                deadline = Deadline(args.task_timeout)
                if backend == "claude" and mode == "direct":
                    r = run_direct_cli(model, task, workdir, target_dir,
                                       deadline, args.cargo_timeout)
                elif backend == "claude":
                    r = run_agentic_cli(model, task, workdir, target_dir, deadline,
                                        args.cargo_timeout, args.max_turns)
                elif mode == "direct":
                    r = run_direct(client, model, task, workdir, target_dir,
                                   deadline, args.cargo_timeout, label)
                else:
                    r = run_agentic(client, model, task, workdir, target_dir, deadline,
                                    args.cargo_timeout, args.max_turns, args.agent_protocol,
                                    label)
                results.append(r)
                print(f"{'▶ ' if VERBOSE else ' '}{STATUS_ICON.get(r.status, r.status)} "
                      f"{r.passed}/{r.total} en {r.wall_s:.0f}s "
                      f"({r.gen_tokens} tok, {r.tok_s:.1f} tok/s, {r.turns} tour(s))",
                      flush=True)
                # rapport incrémental : on ne perd rien si on interrompt
                report(results, out_dir, config)

        if backend == "ollama" and shutil.which("ollama"):
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
