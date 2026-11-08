"""The page shell every face page shares: one stylesheet, the areas across the top, the sections down the side, who
you are acting as. A page is a body; the chrome is here."""
from __future__ import annotations

from flask import render_template_string, url_for

NAV = [
    ("plan", "Plan", [("demand", "Demand plan", "plan"), ("entries", "Entries", "entries"), ("new", "New entry", "entry_new"),
                      ("money", "Revenue bridge", "money")]),
    ("registers", "Registers", [("events", "Promotions", "events"), ("terms", "Terms", "terms"), ("versions", "Versions", "versions")]),
    ("run", "Run", [("run", "Run and health", "run")]),
]

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} — Caldera</title><link rel="stylesheet" href="{{ url_for('static', filename='face.css') }}"></head>
<body><header class="top"><a class="brand" href="{{ url_for('plan') }}">Caldera<small>integrated planning</small></a>
<nav class="areas">{% for a in nav.areas %}<a href="{{ a.href }}" class="{{ 'active' if a.active }}">{{ a.label }}</a>{% endfor %}</nav>
<form class="who" method="post" action="{{ url_for('whoami') }}"><label>acting as</label>
<select name="who" onchange="this.form.submit()">{% for p in principals %}<option value="{{ p }}" {{ 'selected' if p == who }}>{{ p }}</option>{% endfor %}</select>
<input type="hidden" name="next" value="{{ request.path }}"></form></header>
<div class="shell"><aside class="side"><nav>{% for g in nav.groups %}<div class="area {{ 'active' if g.active }}"><div class="group">{{ g.label }}</div>
<div class="sections">{% for s in g.sections %}<a href="{{ s.href }}" class="{{ 'active' if s.active }}">{{ s.label }}</a>{% endfor %}</div></div>{% endfor %}</nav></aside>
<main>{% if flash %}<div class="flash {{ 'bad' if not flash.ok }}">{{ flash.says }}</div>{% endif %}
"""
FOOT = """</main></div></body></html>"""


def _nav(active: str | None) -> dict:
    area_of = {sk: ak for ak, _, secs in NAV for sk, *_ in secs}
    area = area_of.get(active or "", NAV[0][0])
    return dict(areas=[dict(key=ak, label=al, href=url_for(secs[0][2]), active=ak == area) for ak, al, secs in NAV],
                groups=[dict(key=ak, label=al, active=ak == area,
                             sections=[dict(key=sk, label=sl, href=url_for(ep), active=sk == active) for sk, sl, ep in secs])
                        for ak, al, secs in NAV])


def page(body: str, **ctx) -> str:
    ctx.setdefault("flash", None)
    ctx["nav"] = _nav(ctx.get("active"))
    return render_template_string(HEAD + body + FOOT, **ctx)


def n(x, d=0) -> str:
    """A number for a table: thousands separated, blank for nothing, a leading sign kept."""
    if x is None:
        return ""
    return f"{x:,.{d}f}"
