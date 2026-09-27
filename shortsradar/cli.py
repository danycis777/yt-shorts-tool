"""Command line interface. Every command supports --json for scripting/automation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import (
    APP_NAME, __version__, ai, channels, competitors, earnings, ideas, keywords, outliers, scorecard, tags, titles,
    trending,
)
from .config import Settings
from .context import App
from .seo import score_metadata


# ---- output helpers ------------------------------------------------------------------------------

def compact(n: Any) -> str:
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= div:
            return f"{n / div:.1f}{suffix}".replace(".0" + suffix, suffix)
    return f"{n:.0f}" if n == int(n) else f"{n:.1f}"


def table(rows: Iterable[Sequence[Any]], headers: Sequence[str]) -> str:
    rows = [["" if c is None else str(c) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = min(max(widths[i], len(c)), 60)
    def line(cells: Sequence[str]) -> str:
        return "  ".join((c[:57] + "…" if len(c) > 60 else c).ljust(widths[i]) for i, c in enumerate(cells))
    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)


def emit(args: argparse.Namespace, data: Any, render) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        render(data)


# ---- commands -----------------------------------------------------------------------------------------

def cmd_serve(app: App, args: argparse.Namespace) -> None:
    from .server import Server
    demo_srv = None
    if args.demo:
        from .demo import DemoServer
        demo_srv = DemoServer(grow=True).start()
        demo_srv.configure()
        app.demo = True  # type: ignore[attr-defined]
        if not app.settings.get("youtube_api_key"):
            app.settings.update({"youtube_api_key": "demo-key", "niche_keywords": ["minecraft redstone", "cooking"]})
    srv = Server(app, host=args.host, port=args.port, verbose=args.verbose)
    print(f"{APP_NAME} {__version__} running at {srv.url}" + ("   [DEMO MODE — synthetic data]" if args.demo else ""))
    print(f"Data folder: {Path(app.db.path).parent}")
    if args.host not in ("127.0.0.1", "localhost"):
        print("WARNING: listening beyond this computer. Anyone who can reach it can use your API keys.")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        try:
            webbrowser.open(srv.url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    finally:
        if demo_srv:
            demo_srv.stop()


def cmd_keyword(app: App, args: argparse.Namespace) -> None:
    res = keywords.research(app, args.keyword, fmt=args.format, region=args.region, language=args.language,
                            deep=not args.quick, use_api=not args.no_api)

    def render(r: Dict[str, Any]) -> None:
        s = r["scores"]
        sv = r["search_volume"]
        print(f"\nKeyword: {r['keyword']}  ({r['region']}/{r['language']})")
        print(f"  Volume      {s['volume'] if s['volume'] is not None else '—':>5}   ~{compact(sv['monthly_estimate'])} searches/month ({sv['band']})")
        print(f"  Competition {s['competition'] if s['competition'] is not None else '—':>5}" + ("" if r["api_used"] else "   (add a YouTube API key)"))
        print(f"  Overall     {s['overall'] if s['overall'] is not None else '—':>5}")
        if r.get("insights"):
            for n in r["insights"]["notes"]:
                print(f"  • {n['text']}")
        for key, label in (("matching", "Long-tail variations"), ("questions", "Questions"), ("related", "Related")):
            rows = r[key][:12]
            if rows:
                print(f"\n{label}:")
                print(table([(x["keyword"], x["volume"], x["competition"], x["overall"], compact(x["monthly"]))
                             for x in rows], ["keyword", "vol", "comp", "overall", "~monthly"]))
        if r["top_videos"]:
            print("\nTop ranking videos:")
            print(table([(v["rank"], v["title"], compact(v["views"]), compact(v["channel_subs"]),
                          "Short" if v["is_short"] else "Long") for v in r["top_videos"][:10]],
                        ["#", "title", "views", "subs", "format"]))
        print(f"\nQuota used: {r['quota_units']} units · autocomplete requests: {r['autocomplete_requests']}")
    emit(args, res, render)


def cmd_outliers(app: App, args: argparse.Namespace) -> None:
    chan_ids = [channels.resolve_channel_id(app, c) for c in (args.channel or [])]
    res = outliers.find_outliers(app, keyword=args.keyword, channel_ids=chan_ids or None, fmt=args.format,
                                 within=args.within, min_score=args.min_score, max_subs=args.max_subs,
                                 sort=args.sort, deep=args.deep, limit=args.limit)

    def render(r: Dict[str, Any]) -> None:
        print(table([(f"{v['outlier_score']:.1f}x" if v["outlier_score"] is not None else "—", v["title"],
                      v["channel_title"], compact(v["views"]), compact(v["channel_subs"]), compact(v["vph"]),
                      v["url"]) for v in r["results"]],
                    ["score", "title", "channel", "views", "subs", "vph", "url"]))
        print(f"\nScanned {r['scanned']} videos · quota used: {r['quota_units']} units")
    emit(args, res, render)


def cmd_video(app: App, args: argparse.Namespace) -> None:
    res = scorecard.scorecard(app, args.video, keyword=args.keyword)

    def render(r: Dict[str, Any]) -> None:
        v, st = r["video"], r["stats"]
        print(f"\n{v['title']}\n{v.get('channel_title', '')} · {'Short' if v.get('is_short') else 'Long-form'} · {v['url']}")
        if r.get("note"):
            print(f"Note: {r['note']}")
        print(f"  Views {compact(st.get('views'))} · VPH {compact(st.get('vph_lifetime'))} · "
              f"engagement {st.get('engagement_rate') or '—'}% · likes {compact(st.get('likes'))} · comments {compact(st.get('comments'))}")
        if r.get("outlier"):
            print(f"  Outlier score {r['outlier']['score']}x ({r['outlier']['basis']})")
        print(f"  SEO score {r['seo']['score']}/100 ({r['seo']['grade']}) · keyword: {r['seo']['keyword']}")
        print(f"  Title score {r['title_score']['score']}/100")
        for c in r["seo"]["checks"]:
            mark = {"pass": "✔", "warn": "!", "fail": "✘"}.get(c["status"], "·")
            print(f"    {mark} {c['label']}: {c['detail']}")
        if v.get("tags"):
            print(f"  Tags: {', '.join(v['tags'])}")
    emit(args, res, render)


def cmd_channel(app: App, args: argparse.Namespace) -> None:
    res = channels.audit(app, args.channel, max_videos=args.max)

    def render(r: Dict[str, Any]) -> None:
        ch = r["channel"]
        print(f"\n{ch['title']} {ch.get('handle') or ''} · {compact(ch['subs'])} subs · {compact(ch['views'])} views · {ch['video_count']} videos")
        for fmt, f in r["formats"].items():
            if f["count"]:
                print(f"  {fmt:5}: {f['count']} uploads · median {compact(f['median_views'])} views · {f['view_share']}% of views")
        c = r["cadence"]
        print(f"  Cadence: {c['per_week_90d']} uploads/week · last upload {c['days_since_last_upload']} days ago")
        print("\nRecommendations:")
        for rec in r["recommendations"]:
            print(f"  • {rec['text']}")
        print("\nTop outliers:")
        print(table([(f"{v['outlier_score']}x", v["title"], compact(v["views"])) for v in r["top_videos"]],
                    ["score", "title", "views"]))
    emit(args, res, render)


def cmd_trending(app: App, args: argparse.Namespace) -> None:
    if args.keyword:
        res = trending.niche(app, args.keyword, hours=args.hours, fmt=args.format)
    else:
        res = trending.chart(app, region=args.region, category=args.category, fmt=args.format)

    def render(r: Dict[str, Any]) -> None:
        print(table([(v["title"], v["channel_title"], compact(v["views"]), compact(v["vph"]),
                      "Short" if v["is_short"] else "Long") for v in r["videos"][:40]],
                    ["title", "channel", "views", "vph", "format"]))
    emit(args, res, render)


def cmd_competitors(app: App, args: argparse.Namespace) -> None:
    if args.action == "add":
        for ref in args.refs:
            c = competitors.add(app, ref)
            print(f"Tracking {c['title']} ({c['channel_id']})")
        return
    if args.action == "remove":
        for ref in args.refs:
            competitors.remove(app, channels.resolve_channel_id(app, ref))
        return
    if args.action == "refresh":
        res = competitors.refresh(app)
        emit(args, res, lambda r: print(f"Refreshed {r['refreshed']} channels." + (f" Errors: {r['errors']}" if r["errors"] else "")))
        return
    if args.action == "feed":
        res = competitors.feed(app, fmt=args.format, days=args.days)
        emit(args, res, lambda r: print(table([(f"{v['outlier_score']}x" if v["outlier_score"] else "—", v["channel_title"],
                                                 v["title"], compact(v["views"]), compact(v["vph"])) for v in r],
                                               ["score", "channel", "title", "views", "vph"])))
        return
    res = competitors.list_competitors(app)
    emit(args, res, lambda r: print(table([(c["title"], compact(c["subs"]), c["uploads_7d"],
                                             compact(c["median_short_views"]), compact(c["median_long_views"]))
                                            for c in r], ["channel", "subs", "uploads 7d", "median short", "median long"])))


def cmd_tags(app: App, args: argparse.Namespace) -> None:
    res = tags.suggest_tags(app, args.keyword, fmt=args.format, title=args.title, use_api=not args.no_api)
    emit(args, res, lambda r: print(f"{r['copy']}\n\n({r['char_count']}/500 characters)\nHashtags: {r['hashtag_copy']}"))


def cmd_title(app: App, args: argparse.Namespace) -> None:
    if args.generate:
        res = titles.generate_titles(args.generate, fmt=args.format, limit=15)
        emit(args, res, lambda r: print(table([(x["score"], x["title"]) for x in r], ["score", "title"])))
        return
    res = titles.compare_titles(args.titles, fmt=args.format, keyword=args.keyword)

    def render(r: List[Dict[str, Any]]) -> None:
        for x in r:
            print(f"\n{x['score']:>3} ({x['grade']})  {x['title']}")
            for s in x["signals"]:
                print(f"       {s['points']:+5.0f}  {s['label']}{' — ' + s['detail'] if s['detail'] else ''}")
            for tip in x["suggestions"]:
                print(f"        tip: {tip}")
    emit(args, res, render)


def cmd_seo(app: App, args: argparse.Namespace) -> None:
    desc = Path(args.description_file).read_text("utf-8") if args.description_file else (args.description or "")
    res = score_metadata(args.title, desc, [t.strip() for t in (args.tags or "").split(",") if t.strip()],
                         keyword=args.keyword, fmt=args.format)

    def render(r: Dict[str, Any]) -> None:
        print(f"SEO score: {r['score']}/100 ({r['grade']}) — keyword: {r['keyword']}")
        for c in r["checks"]:
            mark = {"pass": "✔", "warn": "!", "fail": "✘"}.get(c["status"], "·")
            print(f"  {mark} {c['label']}: {c['detail']}" + (f"\n      → {c['tip']}" if c["tip"] else ""))
    emit(args, res, render)


def cmd_earnings(app: App, args: argparse.Namespace) -> None:
    res = earnings.calculator(args.views, category=args.category, country=args.country, fmt=args.format,
                              shorts_share=args.shorts_share)
    emit(args, res, lambda r: print(
        f"Monthly: ${r['earnings']['low']:,.0f} – ${r['earnings']['high']:,.0f} (mid ${r['earnings']['mid']:,.0f})\n"
        f"Yearly:  ${r['yearly']['low']:,.0f} – ${r['yearly']['high']:,.0f}\nRPM: ${r['rpm']['low']} – ${r['rpm']['high']}\n{r['note']}"))


def cmd_ideas(app: App, args: argparse.Namespace) -> None:
    res = ideas.daily_ideas(app, args.niche or None, fmt=args.format, refresh=args.refresh)
    emit(args, res, lambda r: print(table([(i["score"], i["idea"], i["why"]) for i in r["ideas"]], ["score", "idea", "why"])))


def cmd_ai(app: App, args: argparse.Namespace) -> None:
    params = {"topic": args.topic, "keyword": args.keyword, "title": args.title, "format": args.format,
              "niche": args.niche, "seconds": args.seconds}
    res = ai.run(app, args.task, {k: v for k, v in params.items() if v}, mode=args.mode)

    def render(r: Dict[str, Any]) -> None:
        if r["mode"] == "prompt":
            print(r["prompt"])
            return
        print(f"[{r['mode']}{' · ' + r['model'] if r.get('model') else ''}]")
        print(json.dumps(r["result"], indent=2, ensure_ascii=False))
    emit(args, res, render)


def cmd_config(app: App, args: argparse.Namespace) -> None:
    if args.action == "set":
        app.settings.update({args.key: args.value})
        print(f"Saved {args.key}.")
    print(json.dumps(app.settings.public(), indent=2))


def cmd_quota(app: App, args: argparse.Namespace) -> None:
    emit(args, app.quota.status(), lambda r: print(
        f"YouTube API quota today: {r['used']:,} / {r['limit']:,} units used · resets in {r['resets_in_seconds'] // 3600}h"))


# ---- parser ----------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shortsradar", description=f"{APP_NAME}: YouTube & Shorts research toolkit.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command")

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(func=fn)
        sp.add_argument("--json", action="store_true", help="output JSON")
        return sp

    def fmt(sp: argparse.ArgumentParser, default: str = "short") -> None:
        sp.add_argument("--format", choices=["short", "long", "any"], default=default)

    s = add("serve", cmd_serve, "start the web dashboard")
    s.add_argument("--port", type=int, default=int(os.environ.get("SHORTSRADAR_PORT", 8765)))
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--no-browser", action="store_true", help="don't open the browser")
    s.add_argument("--demo", action="store_true", help="explore with synthetic demo data (no API key needed)")
    s.add_argument("--verbose", action="store_true")

    s = add("keyword", cmd_keyword, "keyword research: volume, competition, related keywords")
    s.add_argument("keyword")
    fmt(s, "any")
    s.add_argument("--region")
    s.add_argument("--language")
    s.add_argument("--quick", action="store_true", help="fewer autocomplete expansions")
    s.add_argument("--no-api", action="store_true", help="don't spend YouTube API quota")

    s = add("outliers", cmd_outliers, "find videos that massively outperformed their channel")
    s.add_argument("keyword", nargs="?")
    s.add_argument("--channel", action="append", help="channel URL/@handle/ID (repeatable)")
    fmt(s)
    s.add_argument("--within", default="month", choices=list(outliers.WITHIN_DAYS))
    s.add_argument("--min-score", type=float)
    s.add_argument("--max-subs", type=int)
    s.add_argument("--sort", default="score", choices=["score", "views", "vph", "recent", "engagement"])
    s.add_argument("--deep", action="store_true", help="3 searches instead of 1 (300 units)")
    s.add_argument("--limit", type=int, default=30)

    s = add("video", cmd_video, "video scorecard: stats, VPH, outlier score, SEO audit")
    s.add_argument("video", help="video/Shorts URL or ID")
    s.add_argument("--keyword", help="target keyword to audit against")

    s = add("channel", cmd_channel, "channel audit")
    s.add_argument("channel", help="channel URL, @handle or ID")
    s.add_argument("--max", type=int, default=100, help="recent uploads to analyse")

    s = add("trending", cmd_trending, "trending chart, or what's hot in a niche (--keyword)")
    s.add_argument("--keyword")
    s.add_argument("--hours", type=int, default=72)
    s.add_argument("--region")
    s.add_argument("--category")
    fmt(s, "any")

    s = add("competitors", cmd_competitors, "track competitor channels (free, via RSS)")
    s.add_argument("action", choices=["list", "add", "remove", "refresh", "feed"], nargs="?", default="list")
    s.add_argument("refs", nargs="*")
    fmt(s, "any")
    s.add_argument("--days", type=int, default=14)

    s = add("tags", cmd_tags, "generate tags & hashtags for a keyword")
    s.add_argument("keyword")
    s.add_argument("--title")
    fmt(s)
    s.add_argument("--no-api", action="store_true")

    s = add("title", cmd_title, "score titles (CTR heuristic) or --generate ideas")
    s.add_argument("titles", nargs="*")
    s.add_argument("--keyword")
    s.add_argument("--generate", metavar="KEYWORD")
    fmt(s)

    s = add("seo", cmd_seo, "score title/description/tags before uploading")
    s.add_argument("--title", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--description-file")
    s.add_argument("--tags", help="comma separated")
    s.add_argument("--keyword")
    fmt(s)

    s = add("earnings", cmd_earnings, "estimate ad revenue for monthly views")
    s.add_argument("views", type=float)
    s.add_argument("--category", default="Entertainment", choices=earnings.CATEGORIES)
    s.add_argument("--country", default="US")
    fmt(s)
    s.add_argument("--shorts-share", type=float, help="0-1 share of Shorts views for a channel mix")

    s = add("ideas", cmd_ideas, "daily video ideas from outliers & searches in your niches")
    s.add_argument("niche", nargs="*")
    fmt(s)
    s.add_argument("--refresh", action="store_true")

    s = add("ai", cmd_ai, "AI studio: titles, hooks, script, description, tags, ideas")
    s.add_argument("task", choices=list(ai.TASKS))
    s.add_argument("topic", nargs="?")
    s.add_argument("--keyword")
    s.add_argument("--title")
    s.add_argument("--niche")
    s.add_argument("--seconds", type=int)
    fmt(s)
    s.add_argument("--mode", default="auto", choices=["auto", "claude", "template", "prompt"])

    s = add("config", cmd_config, "show or set settings (e.g. config set youtube_api_key KEY)")
    s.add_argument("action", choices=["show", "set"], nargs="?", default="show")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")

    add("quota", cmd_quota, "show today's YouTube API quota usage")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version")):
        argv = ["serve"] + argv  # no command: start the dashboard
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # ✔/→ on Windows consoles & pipes
        except (AttributeError, ValueError):
            pass
    if args.command == "serve" and args.demo:
        # Demo data lives in its own folder so it never mixes with your real data/settings.
        base = os.environ.get("SHORTSRADAR_HOME")
        os.environ["SHORTSRADAR_HOME"] = str(Path(base) / "demo") if base else str(Path(tempfile.gettempdir()) / "shortsradar-demo")
    if args.command == "config" and args.action == "set" and not (args.key and args.value is not None):
        parser.error("usage: config set KEY VALUE")
    app = App(Settings())
    try:
        args.func(app, args)
    except KeyboardInterrupt:
        return 130
    except Exception as err:  # noqa: BLE001 - friendly CLI errors
        if os.environ.get("SHORTSRADAR_DEBUG"):
            raise
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0
