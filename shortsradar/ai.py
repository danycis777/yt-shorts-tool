"""AI Studio: titles, descriptions, tags, hooks, Shorts scripts and video ideas.

Three ways to run every task:
  * "claude"   - calls Claude through the official `anthropic` SDK (optional, needs Python 3.10+)
                 when an Anthropic API key is configured.
  * "template" - an offline, zero-cost generator built on proven YouTube formats.
  * "prompt"   - a ready-to-paste prompt for the free Claude.ai chat.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shlex
import sys
import sysconfig
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .seo import score_metadata
from .textutil import normalize_keyword, smart_title, tokens
from .titles import generate_titles, score_title

DEFAULT_MODEL = "claude-opus-5"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
SDK_REQUIREMENT = "anthropic>=1.8"
SDK_MIN_PYTHON = (3, 10)
PROJECT_DIR = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = """You are a YouTube growth strategist who specialises in YouTube Shorts and short-form retention.
You write packaging (titles, hooks, descriptions, tags) and scripts that earn clicks honestly: every
promise in a title or hook must be delivered by the video. Principles you follow:
- Shorts are judged in the first 1-2 seconds: open on the most intriguing moment or claim, no intros.
- Titles are specific and concrete (numbers, stakes, outcomes), easy to scan, ideally under 60 characters
  for Shorts and under 70 for long-form, with the main search phrase near the start when one is given.
- Curiosity gaps beat vague hype; never use misleading clickbait or ALL CAPS shouting.
- Write for the creator's niche and audience; keep the language natural, not keyword-stuffed.
Keep every field focused and concise."""


class AIError(Exception):
    pass


def sdk_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


def api_key(app) -> str:
    return app.settings.get("anthropic_api_key") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")


def _shell_quote(text: str) -> str:
    if os.name == "nt":
        return f'"{text}"' if " " in text else text
    return shlex.quote(text)


def _externally_managed() -> bool:
    """True when this Python refuses pip installs outside a virtual environment (PEP 668)."""
    if sys.prefix != sys.base_prefix:
        return False
    stdlib = sysconfig.get_path("stdlib")
    return bool(stdlib) and os.path.isfile(os.path.join(stdlib, "EXTERNALLY-MANAGED"))


def install_info() -> Dict[str, Any]:
    """The exact command that installs the Claude SDK for the Python running ShortsRadar.

    A bare `pip install` often targets a different Python than the one running the app."""
    python = sys.executable or ""
    exe = _shell_quote(python) if python else ("py -3" if os.name == "nt" else "python3")
    command = f'{exe} -m pip install "{SDK_REQUIREMENT}"'
    after = "Then restart ShortsRadar."
    venv = _externally_managed() and (PROJECT_DIR / "run.py").is_file()
    if venv:  # e.g. Homebrew or Debian/Ubuntu Python: install into the project's .venv instead
        command = (f"cd {_shell_quote(str(PROJECT_DIR))} && {exe} -m venv .venv && "
                   f'.venv/bin/python -m pip install "{SDK_REQUIREMENT}"')
        after = "Then restart ShortsRadar with ./start.sh (it uses .venv automatically) or .venv/bin/python run.py."
    return {
        "python_version": ".".join(str(n) for n in sys.version_info[:3]),
        "python_path": python,
        "python_ok": sys.version_info >= SDK_MIN_PYTHON,
        "shell": "Command Prompt" if os.name == "nt" else "Terminal",
        "command": command,
        "venv": venv,
        "after": after,
    }


def _hint(key: bool, install: Optional[Dict[str, Any]]) -> Optional[str]:
    if not key:
        return "Add an Anthropic API key in Settings to generate with Claude — or use the free Template/Prompt modes."
    if install is None:
        return None
    if not install["python_ok"]:
        return (f"Claude needs Python 3.10 or newer, but ShortsRadar is running on Python {install['python_version']}. "
                "Install the latest Python from python.org, then start ShortsRadar again.")
    return f"Install the Claude SDK by running this in {install['shell']}:\n  {install['command']}\n{install['after']}"


def status(app) -> Dict[str, Any]:
    key = bool(api_key(app))
    sdk = sdk_available()
    install = None if sdk else install_info()
    return {
        "sdk_installed": sdk,
        "key_configured": key,
        "ready": key and sdk,
        "model": app.settings.get("ai_model") or DEFAULT_MODEL,
        "effort": app.settings.get("ai_effort") or "medium",
        "install": install,
        "hint": _hint(key, install),
    }


# ---- task definitions -------------------------------------------------------------------------

def _str(v: Any, limit: int = 4000) -> str:
    return str(v or "").strip()[:limit]


def _fmt_label(fmt: str) -> str:
    return "YouTube Short (vertical, under 60 seconds)" if fmt == "short" else "long-form YouTube video"


def _context_block(p: Dict[str, Any]) -> str:
    lines = []
    if p.get("niche"):
        lines.append(f"Channel niche: {_str(p['niche'], 200)}")
    if p.get("audience"):
        lines.append(f"Target audience: {_str(p['audience'], 200)}")
    if p.get("keyword"):
        lines.append(f"Main search phrase to target: {_str(p['keyword'], 150)}")
    comp = [t for t in (p.get("competitor_titles") or []) if str(t).strip()][:15]
    if comp:
        lines.append("Titles that are over-performing in this niche right now (for inspiration, do not copy):\n"
                     + "\n".join(f"- {_str(t, 150)}" for t in comp))
    searches = [t for t in (p.get("searches") or []) if str(t).strip()][:15]
    if searches:
        lines.append("Phrases people search for on YouTube in this niche:\n" + "\n".join(f"- {_str(s, 120)}" for s in searches))
    return "\n".join(lines)


def _obj(props: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(items: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "array", "items": items}


S = {"type": "string"}

TASKS: Dict[str, Dict[str, Any]] = {
    "titles": {
        "label": "Title ideas",
        "schema": _obj({"titles": _arr(_obj({"title": S, "angle": S, "why": S}))}),
        "chat_format": "a numbered list: title — angle — one line on why it works",
        "build": lambda p: (
            f"Write 10 title options for a {_fmt_label(p.get('format', 'short'))}.\n"
            f"Video topic / what happens in it: {_str(p.get('topic'))}\n"
            + (f"Current working title: {_str(p.get('current_title'), 200)}\n" if p.get("current_title") else "")
            + _context_block(p)
            + "\nVary the angles (curiosity, challenge/experiment, how-to, list, stakes, contrarian). "
              "For each title give the angle and one short sentence on why it earns the click."
        ),
    },
    "description": {
        "label": "Description",
        "schema": _obj({"description": S, "hashtags": _arr(S), "pinned_comment": S}),
        "chat_format": "the description text, then 3 hashtags, then a suggested pinned comment",
        "build": lambda p: (
            f"Write the YouTube description for a {_fmt_label(p.get('format', 'short'))}.\n"
            f"Title: {_str(p.get('title'), 200)}\nWhat the video covers: {_str(p.get('topic'))}\n"
            + _context_block(p)
            + "\nPut the main search phrase naturally in the first sentence. "
            + ("Keep it to 2-4 short sentences. " if p.get("format", "short") == "short" else
               "Include a 2-3 sentence summary, key points, a chapters placeholder line and a subscribe call to action. ")
            + "Give exactly 3 relevant hashtags (with #). Also write a pinned comment that invites replies."
        ),
    },
    "tags": {
        "label": "Tags",
        "schema": _obj({"tags": _arr(S), "hashtags": _arr(S)}),
        "chat_format": "a comma-separated tag list (under 500 characters total), then 3 hashtags",
        "build": lambda p: (
            f"Suggest YouTube tags for a {_fmt_label(p.get('format', 'short'))}.\n"
            f"Title: {_str(p.get('title'), 200)}\nTopic: {_str(p.get('topic'))}\n" + _context_block(p)
            + "\nOrder: the exact main search phrase first, then close variations people search, then broader "
              "topic tags. 12-20 tags, lowercase, no '#' in tags, total under 450 characters. Also 3 hashtags."
        ),
    },
    "hooks": {
        "label": "Hooks (first 2 seconds)",
        "schema": _obj({"hooks": _arr(_obj({"text": S, "type": S, "why": S}))}),
        "chat_format": "a numbered list: hook line — hook type — why it stops the scroll",
        "build": lambda p: (
            "Write 10 opening hooks (the first 1-2 seconds, spoken or on-screen) for a YouTube Short.\n"
            f"Topic: {_str(p.get('topic'))}\n" + _context_block(p)
            + "\nMix hook types: bold claim, question, pattern interrupt, 'POV', result-first, mistake/warning, "
              "number/list. Each hook under 12 words."
        ),
    },
    "script": {
        "label": "Shorts script",
        "schema": _obj({
            "title": S, "hook": S,
            "beats": _arr(_obj({"time": S, "voiceover": S, "on_screen_text": S, "visual": S})),
            "cta": S, "loop": S, "caption": S, "hashtags": _arr(S),
        }),
        "chat_format": "a timestamped script table (time | voiceover | on-screen text | visual), then CTA, loop tip, caption and hashtags",
        "build": lambda p: (
            f"Write a {int(p.get('seconds') or 35)}-second YouTube Short script.\n"
            f"Topic: {_str(p.get('topic'))}\n"
            + (f"Style/voice: {_str(p.get('style'), 200)}\n" if p.get("style") else "")
            + _context_block(p)
            + "\nStructure: a hook in the first 2 seconds, fast beats (a new visual every 2-3 seconds), a payoff, "
              "and an ending that loops back into the start so viewers rewatch. Voiceover lines must fit the time "
              "stamps (about 2.5 words per second). Include on-screen text and what to show for every beat. "
              "Suggest a title, a caption line and 3 hashtags."
        ),
    },
    "ideas": {
        "label": "Video ideas",
        "schema": _obj({"ideas": _arr(_obj({"title": S, "hook": S, "concept": S, "why_it_works": S}))}),
        "chat_format": "a numbered list: title — hook — one-line concept — why it works",
        "build": lambda p: (
            f"Give me 12 fresh {_fmt_label(p.get('format', 'short'))} ideas.\n"
            + _context_block(p)
            + (f"\nExtra notes from the creator: {_str(p.get('topic'), 800)}" if p.get("topic") else "")
            + "\nBase them on what is working now but make each idea original, filmable by a small creator, and "
              "specific. For each: a title, the opening hook line, the concept in one sentence, and why it works."
        ),
    },
}


def build_prompt(task: str, params: Dict[str, Any]) -> str:
    spec = TASKS[task]
    return spec["build"](params)


def chat_prompt(task: str, params: Dict[str, Any]) -> str:
    """A self-contained prompt to paste into the Claude.ai chat (free)."""
    spec = TASKS[task]
    return f"{SYSTEM_PROMPT}\n\n{build_prompt(task, params)}\n\nFormat your answer as {spec['chat_format']}."


# ---- Claude call ------------------------------------------------------------------------------------

def _client(app):
    import anthropic

    kwargs: Dict[str, Any] = {"timeout": 240.0, "max_retries": 2}
    key = app.settings.get("anthropic_api_key")
    if key:
        kwargs["api_key"] = key
    elif os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        kwargs["auth_token"] = os.environ["ANTHROPIC_AUTH_TOKEN"]
    if os.environ.get("SHORTSRADAR_ANTHROPIC_BASE"):
        kwargs["base_url"] = config.ANTHROPIC_BASE
    return anthropic.Anthropic(**kwargs)


def call_claude(app, task: str, params: Dict[str, Any]) -> Dict[str, Any]:
    import anthropic

    spec = TASKS[task]
    model = app.settings.get("ai_model") or DEFAULT_MODEL
    effort = app.settings.get("ai_effort") or "medium"
    if effort not in EFFORTS:
        effort = "medium"
    client = _client(app)
    try:
        # Server-side fallbacks ("default") re-run a request that Claude's safety classifiers decline on
        # Anthropic's recommended fallback model instead of failing.
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": spec["schema"]}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(task, params)}],
        )
    except anthropic.AuthenticationError:
        raise AIError("Your Anthropic API key was rejected. Check it in Settings.") from None
    except anthropic.PermissionDeniedError as err:
        raise AIError(f"Your Anthropic API key can't use this model ({err.message}).") from None
    except anthropic.NotFoundError:
        raise AIError(f"Model '{model}' was not found. Pick another model in Settings.") from None
    except anthropic.RateLimitError:
        raise AIError("Claude is rate-limiting your key. Wait a minute and try again.") from None
    except anthropic.BadRequestError as err:
        raise AIError(f"Claude rejected the request: {err.message}") from None
    except anthropic.APIStatusError as err:
        raise AIError(f"Claude API error ({err.status_code}). Try again shortly.") from None
    except anthropic.APIConnectionError:
        raise AIError("Couldn't reach the Claude API. Check your internet connection.") from None

    if response.stop_reason == "refusal":
        raise AIError("Claude declined this request. Try rephrasing the topic.")
    if response.stop_reason == "max_tokens":
        raise AIError("Claude's answer was cut off. Try a shorter request.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError:
        raise AIError("Claude returned an unexpected format. Try again.") from None
    iterations = getattr(response.usage, "iterations", None) or []
    fallback_ran = any(getattr(it, "type", "") == "fallback_message" for it in iterations)
    return {
        "data": data,
        "model": response.model,
        "fallback_used": fallback_ran,
        "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
    }


# ---- offline templates -------------------------------------------------------------------------------

HOOK_TEMPLATES = (
    ("Stop scrolling if you {v}", "Pattern interrupt"),
    ("Nobody tells you this about {t}", "Curiosity"),
    ("I tried {t} so you don't have to", "Experiment"),
    ("This {t} mistake costs you everything", "Warning"),
    ("POV: you finally figured out {t}", "POV"),
    ("Here's {t} in 30 seconds", "Speed / payoff"),
    ("Watch what happens when I {v}", "Result-first"),
    ("3 things about {t} I wish I knew sooner", "List"),
    ("You're doing {t} wrong — here's why", "Contrarian"),
    ("Is this the best {t} ever?", "Question"),
)


def _subject(params: Dict[str, Any], prefer_topic: bool = False) -> str:
    topic = _str(params.get("topic"), 200)
    if prefer_topic and topic and len(topic) <= 60:
        return topic
    return _str(params.get("keyword") or topic or params.get("title"), 80) or "this"


def template(app, task: str, params: Dict[str, Any]) -> Dict[str, Any]:
    fmt = params.get("format") or "short"
    subject = normalize_keyword(_subject(params, prefer_topic=task in ("script", "hooks", "titles")))
    pretty = smart_title(subject)
    if task == "titles":
        rows = generate_titles(subject, fmt=fmt, limit=12)
        return {"titles": [{"title": r["title"], "angle": "template", "why": f"CTR score {r['score']}"} for r in rows]}
    if task == "hooks":
        verb = subject[7:] if subject.startswith("how to ") else f"try {subject}"
        return {"hooks": [{"text": t.format(t=subject, v=verb), "type": kind, "why": "Proven short-form hook pattern"}
                          for t, kind in HOOK_TEMPLATES]}
    if task == "description":
        title = _str(params.get("title"), 200) or pretty
        kw = subject
        tag_words = [w for w in tokens(kw) if len(w) > 2][:2]
        hashtags = ["#" + "".join(tokens(kw))] + ["#" + w for w in tag_words]
        if fmt == "short":
            hashtags.append("#shorts")
            desc = (f"{pretty}: {(_str(params.get('topic'), 300) or title).rstrip('.')}. "
                    f"Follow for more {kw} tips!\n\n" + " ".join(dict.fromkeys(hashtags)))
        else:
            desc = (f"{pretty} — {(_str(params.get('topic'), 400) or title).rstrip('.')}.\n\n"
                    f"In this video you'll learn:\n• \n• \n• \n\n"
                    f"Chapters:\n0:00 Intro\n\nIf this helped, subscribe for more {kw} videos!\n\n"
                    + " ".join(dict.fromkeys(hashtags)))
        return {"description": desc, "hashtags": list(dict.fromkeys(hashtags))[:3],
                "pinned_comment": f"What should I try next with {kw}? 👇"}
    if task == "tags":
        from .tags import suggest_tags
        res = suggest_tags(app, subject, fmt=fmt, use_api=False, with_volume=False)
        return {"tags": res["selected"], "hashtags": res["hashtags"]}
    if task == "script":
        secs = int(params.get("seconds") or 35)
        beats = []
        marks = [0, 2, max(5, secs // 3), max(8, 2 * secs // 3), max(10, secs - 4)]
        texts = [
            ("[Hook] Open on the most surprising moment of the result.", f"{pretty}?!", "Result first, tight close-up"),
            (f"[Setup] Say what you're doing and why it matters for {subject}.", "Here's how", "Quick setup shot"),
            ("[Step / reveal 1] Show the first key step fast.", "Step 1", "New angle every 2-3 seconds"),
            ("[Step / reveal 2] The twist or the detail most people miss.", "The secret", "Zoom / reaction"),
            ("[Payoff] Show the final result and set up the loop.", "Worth it?", "Final result, cut back to the start"),
        ]
        for t, (vo, ost, vis) in zip(marks, texts):
            beats.append({"time": f"0:{t:02d}", "voiceover": vo, "on_screen_text": ost, "visual": vis})
        return {"title": generate_titles(subject, fmt="short", limit=1)[0]["title"] if subject else pretty,
                "hook": HOOK_TEMPLATES[1][0].format(t=subject, v=subject), "beats": beats,
                "cta": "Follow for part 2", "loop": "End mid-sentence on a line that matches your first frame.",
                "caption": f"{pretty} 🤯", "hashtags": ["#" + "".join(tokens(subject)), "#shorts"]}
    if task == "ideas":
        from .ideas import search_gap_ideas
        rows = search_gap_ideas(app, subject, fmt=fmt, limit=12)
        return {"ideas": [{"title": r["title"], "hook": r["hook"], "concept": r["concept"], "why_it_works": r["why"]}
                          for r in rows]}
    raise AIError(f"Unknown task: {task}")


# ---- entry point ---------------------------------------------------------------------------------------

def run(app, task: str, params: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
    if task not in TASKS:
        raise AIError(f"Unknown task '{task}'. Choose one of: {', '.join(TASKS)}.")
    params = dict(params or {})
    params.setdefault("format", app.settings.get("default_format") or "short")
    if not (params.get("topic") or params.get("keyword") or params.get("title") or params.get("niche")):
        raise AIError("Describe the topic (or give a keyword/title) first.")
    st = status(app)
    if mode == "auto":
        mode = "claude" if st["ready"] else "template"
    out: Dict[str, Any] = {"task": task, "mode": mode, "prompt": chat_prompt(task, params), "status": st,
                           "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
    if mode == "claude":
        if not st["ready"]:
            raise AIError(st["hint"] or "Claude is not configured.")
        res = call_claude(app, task, params)
        out.update(result=res["data"], model=res["model"], fallback_used=res["fallback_used"], usage=res["usage"])
    elif mode == "template":
        out["result"] = template(app, task, params)
    elif mode == "prompt":
        out["result"] = None
    else:
        raise AIError("mode must be auto, claude, template or prompt")
    _post_process(task, params, out)
    return out


def _post_process(task: str, params: Dict[str, Any], out: Dict[str, Any]) -> None:
    res = out.get("result")
    if not res:
        return
    fmt = params.get("format") or "short"
    kw = params.get("keyword")
    if task == "titles" and isinstance(res.get("titles"), list):
        for row in res["titles"]:
            s = score_title(row.get("title", ""), fmt=fmt, keyword=kw)
            row["score"], row["grade"] = s["score"], s["grade"]
        res["titles"].sort(key=lambda r: -r.get("score", 0))
    if task == "description" and isinstance(res.get("description"), str):
        seo = score_metadata(params.get("title") or "", res["description"], params.get("tags") or [],
                             keyword=kw, fmt=fmt)
        res["seo_score"] = seo["score"]


TASK_LIST: List[Dict[str, str]] = [{"id": k, "label": v["label"]} for k, v in TASKS.items()]
