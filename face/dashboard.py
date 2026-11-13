"""The head of demand's home page and the forecast accuracy page: templates and the one figure drawn here. Everything on
them is read from the last run — the tiles, the chart, the tree, the units, the ladder; the only act is the plan's
submission, and that is the same act the submissions page offers."""
from __future__ import annotations

# a tree table: rows carry data-parent; a row's toggle shows its children, hiding grandchildren when it closes
TREE_JS = """<script>document.querySelectorAll('table.tree').forEach(t=>{t.querySelectorAll('tr[data-parent]').forEach(r=>r.hidden=true);
t.querySelectorAll('button.tog').forEach(b=>b.addEventListener('click',()=>{const id=b.dataset.id,open=b.classList.toggle('open');
const hide=pid=>t.querySelectorAll(`tr[data-parent="${pid}"]`).forEach(r=>{r.hidden=true;const bb=r.querySelector('button.tog');if(bb){bb.classList.remove('open');hide(bb.dataset.id)}});
if(open)t.querySelectorAll(`tr[data-parent="${id}"]`).forEach(r=>r.hidden=false);else hide(id)}))})</script>"""

TREE_CSS = """table.tree button.tog{background:none;border:0;box-shadow:none;padding:0 .4rem 0 0;font-size:.7rem;color:var(--muted);cursor:pointer;width:1.2rem}
table.tree button.tog::before{content:"▸"}table.tree button.tog.open::before{content:"▾"}
table.tree tr.l1 td:first-child{padding-left:1.8rem}table.tree tr.l2 td:first-child{padding-left:3.2rem;color:var(--muted)}table.tree tr.l1 td,table.tree tr.l2 td{font-size:.86rem}
.delta{font-variant-numeric:tabular-nums;white-space:nowrap}.delta.up::before{content:"▲ ";font-size:.7em}.delta.down::before{content:"▼ ";font-size:.7em}.delta.flat::before{content:"— "}
.bias.high::after{content:" high";color:var(--muted);font-size:.8em}.bias.low::after{content:" low";color:var(--muted);font-size:.8em}"""

# the figure: the chart's frame, legend swatches, drill crumbs, small multiples and the hover read-out — shared by every page that draws chart()
FIG_CSS = """.fig svg{display:block;width:100%;height:auto;max-height:420px;margin-top:.6rem}.fighead{display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap}.fighead .legend{margin-left:auto}
.key{display:inline-flex;align-items:center;gap:.3rem}.sw{display:inline-block;width:1.1rem;height:0;border-top:2px solid var(--series-1)}.sw.actual{border-top-width:4px}.sw.ref{border-top-style:dashed}.sw.py{border-top-color:var(--series-3)}
.crumbs{font-size:.85rem;color:var(--muted)}.crumbs a{text-decoration:none}.crumbs a:hover{text-decoration:underline}.crumbs b{color:var(--ink)}.crumbs .switch{margin-left:.9rem;font-size:.78rem;border:1px solid var(--rule);border-radius:999px;padding:.1rem .6rem}.crumbs .seg{display:inline-flex;margin-left:.6rem;font-size:.78rem;border:1px solid var(--rule);border-radius:999px;overflow:hidden}.crumbs .seg a,.crumbs .seg b{padding:.1rem .6rem}.crumbs .seg b{background:var(--accent);color:var(--on-accent);font-weight:500}.crumbs .seg a+a,.crumbs .seg b+a,.crumbs .seg a+b{border-left:1px solid var(--rule)}
.multiples{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:.8rem;margin-top:1rem;border-top:1px solid var(--rule);padding-top:1rem}
.multiple{display:block;text-decoration:none;color:inherit;border:1px solid var(--rule);border-radius:var(--radius-s);padding:.5rem .7rem .3rem}.multiple:hover{background:var(--hover);border-color:var(--faint)}
.mhead{display:flex;justify-content:space-between;font-size:.82rem;font-weight:500;gap:.5rem}.multiple svg{max-height:120px}
.fig{position:relative}.tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--paper);font-size:.78rem;padding:.4rem .6rem;border-radius:var(--radius-s);line-height:1.4;white-space:nowrap}
"""

FIG_JS = """<script>(()=>{const svg=document.querySelector('.fig svg');if(!svg)return;const tip=document.querySelector('.fig .tip');const pts=JSON.parse(svg.dataset.points);const cross=svg.querySelector('.cross');const dots=svg.querySelectorAll('.dot');
svg.addEventListener('mousemove',e=>{const r=svg.getBoundingClientRect();const x=(e.clientX-r.left)/r.width*svg.viewBox.baseVal.width;let i=0;for(let k=1;k<pts.length;k++)if(Math.abs(pts[k].x-x)<Math.abs(pts[i].x-x))i=k;const p=pts[i];
cross.setAttribute('x1',p.x);cross.setAttribute('x2',p.x);cross.style.display='';dots.forEach(d=>{const v=p[d.dataset.s];if(v==null){d.style.display='none'}else{d.style.display='';d.setAttribute('cx',p.x);d.setAttribute('cy',v.y)}});
tip.innerHTML='<b>'+p.label+'</b>'+Object.entries(p).filter(([k,v])=>v&&v.text).map(([k,v])=>'<br>'+v.name+' '+v.text).join('');tip.hidden=false;const fr=svg.parentNode.getBoundingClientRect();tip.style.left=Math.min(e.clientX-fr.left+14,fr.width-tip.offsetWidth-8)+'px';tip.style.top=(e.clientY-fr.top-10)+'px'});
svg.addEventListener('mouseleave',()=>{tip.hidden=true;cross.style.display='none';dots.forEach(d=>d.style.display='none')})})()</script>
"""

HEAD_PAGE = """<h1>Demand<small>{{ version }} · FY{{ fy }} · {{ who }} · what the run says this morning</small></h1>
<form class="toolbar" method="get"><label>version<select name="version" onchange="this.form.submit()">{% for v in versions %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == version }}>{{ v.version_id }} · {{ v.status }}</option>{% endfor %}</select></label></form>
<div class="cards tiles">
<a class="card stat" href="{{ links.demand }}"><span>FY{{ fy }} net sales · AUD</span><b>{{ t.value|m }}</b><div class="small delta {{ t.value_d|dir }}">{{ t.value_d|pct }} vs FY{{ fy - 1 }} invoiced</div></a>
<a class="card stat" href="{{ links.money }}"><span>Net sales P{{ rev.p_from[5:]|int }}–P{{ rev.p_to[5:]|int }} vs {{ rev.ref_id }}</span><b>{{ rev.net_sales|m }}</b><div class="small delta {{ rev.d|dir }}">{{ rev.d|pct }} on the periods both value</div></a>
<a class="card stat" href="{{ links.accuracy }}"><span>Forecast accuracy · lag {{ lag }} · last 12</span><b>{{ acc.accuracy|pct1 }}</b><div class="small delta {{ acc.d|dir }}">{{ acc.d|pp }} vs prior 12 · bias {{ acc.bias|pct1s }}</div></a>
<a class="card stat" href="{{ links.submissions }}"><span>Plan status</span><b>{{ ladder[2].done }} of {{ ladder[2].total }} units in</b><div class="small muted">{{ status_line }}</div></a>
</div>
<div class="grid2">
<div class="card fig"><div class="fighead"><b>{{ 'Net sales' if series.measure == 'net_sales' else 'Demand' }} per week</b><span class="crumbs">{% for n in drill.path %}{% if loop.last %}<b>{{ n.label }}</b>{% else %}<a href="{{ n.href }}">{{ n.label }}</a> ▸ {% endif %}{% endfor %}<a class="switch" href="{{ drill.other }}">by {{ 'material' if drill.dim == 'customer' else 'customer' }}</a><span class="seg">{% for g in fig.grains %}{% if g.on %}<b>{{ g.label }}</b>{% else %}<a href="{{ g.href }}">{{ g.label }}</a>{% endif %}{% endfor %}</span>{% if fig.measures %}<span class="seg">{% for g in fig.measures %}{% if g.on %}<b>{{ g.label }}</b>{% else %}<a href="{{ g.href }}">{{ g.label }}</a>{% endif %}{% endfor %}</span>{% endif %}</span><span class="legend">
<span class="key"><i class="sw actual"></i>{{ 'invoiced' if series.measure == 'net_sales' else 'shipped' }}</span><span class="key"><i class="sw plan"></i>{{ version }}</span>{% if series.ref_id %}<span class="key"><i class="sw ref"></i>{{ series.ref_id }}</span>{% endif %}<span class="key"><i class="sw py"></i>FY{{ fy - 1 }}</span></span></div>
{{ chart|safe }}<div class="tip" hidden></div>
<p class="hint">Every point is a rate per week{% if series.grain == 'period' %} — the period's total over its weeks, the week count in the label — so a five-week period does not read as a step{% else %} — the weeks themselves, a rule at each period boundary{% endif %}. {% if series.measure == 'net_sales' %}History is what was invoiced; the plan is cases at the list and terms in force.{% if not fig.measures %} Cases are read at a material — open one — and mean nothing added across materials.{% endif %}{% else %}Period totals are on the <a href="{{ links.demand }}">demand grid</a>.{% endif %}</p>
{% if drill.children %}<div class="multiples">{% for c in drill.children %}<a class="multiple" href="{{ c.href }}"><div class="mhead"><span>{{ c.label }}</span><span class="muted">{{ c.total|aud if series.measure == 'net_sales' else c.total|k }}</span></div>{{ c.chart|safe }}</a>{% endfor %}</div>
<p class="hint">Each small chart is the level below; open one to make it the chart and see its own children. Same scale within a row is not promised — read the shape, then the number.</p>{% endif %}</div>
<div class="card list" id="attention"><b>My attention<span class="count">{{ mine|length }} routed to you</span></b>
{% if mine %}<ul class="rows">{% for m in mine %}<li><div>{% if m.href %}<a href="{{ m.href }}">{{ m.item }}</a>{% else %}{{ m.item }}{% endif %}</div><div class="small muted">{{ m.name }} · {{ m.what_to_do }}</div></li>{% endfor %}</ul>{% else %}<p class="muted small">Nothing is waiting on you.</p>{% endif %}</div>
</div>
<div class="grid2">
<div id="planning"><h2>Plan by category<span class="count">FY{{ fy }} net sales · open a row for its products, a product for its materials and their cases</span></h2>
<table class="tree"><thead><tr><th>Category</th><th class="n">Net sales</th><th class="n">vs FY{{ fy - 1 }}</th>{% if tree.ref_id %}<th class="n">vs {{ tree.ref_id }}</th>{% endif %}<th class="n">Cases</th><th class="n">Accuracy</th><th class="n">Bias</th></tr></thead><tbody>
{% for c in tree.categories %}<tr><td><button type="button" class="tog" data-id="{{ c.code }}"></button>{{ c.label }}</td><td class="n">{{ c.value|aud }}</td><td class="n delta {{ c.py_d|dir }}">{{ c.py_d|pct }}</td>{% if tree.ref_id %}<td class="n delta {{ c.ref_d|dir }}">{{ c.ref_d|pct }}</td>{% endif %}<td class="n muted">·</td><td class="n">{{ acc_of[c.code].accuracy|pct1 if c.code in acc_of else '' }}</td><td class="n bias {{ acc_of[c.code].bias|hl if c.code in acc_of else '' }}">{{ acc_of[c.code].bias|pct1s if c.code in acc_of else '' }}</td></tr>
{% for p in c.children %}<tr class="l1" data-parent="{{ c.code }}"><td><button type="button" class="tog" data-id="{{ p.code }}"></button>{{ p.label }}</td><td class="n">{{ p.value|aud }}</td><td class="n delta {{ p.py_d|dir }}">{{ p.py_d|pct }}</td>{% if tree.ref_id %}<td class="n delta {{ p.ref_d|dir }}">{{ p.ref_d|pct }}</td>{% endif %}<td class="n muted">·</td><td class="n">{{ acc_of[p.code].accuracy|pct1 if p.code in acc_of else '' }}</td><td class="n bias {{ acc_of[p.code].bias|hl if p.code in acc_of else '' }}">{{ acc_of[p.code].bias|pct1s if p.code in acc_of else '' }}</td></tr>
{% for m in p.children %}<tr class="l2" data-parent="{{ p.code }}"><td>{{ m.label }} <span class="muted">{{ m.code }}</span></td><td class="n">{{ m.value|aud }}</td><td class="n delta {{ m.py_d|dir }}">{{ m.py_d|pct }}</td>{% if tree.ref_id %}<td class="n delta {{ m.ref_d|dir }}">{{ m.ref_d|pct }}</td>{% endif %}<td class="n">{{ m.cases|n }}</td><td class="n">{{ acc_of[m.code].accuracy|pct1 if m.code in acc_of else '' }}</td><td class="n bias {{ acc_of[m.code].bias|hl if m.code in acc_of else '' }}">{{ acc_of[m.code].bias|pct1s if m.code in acc_of else '' }}</td></tr>{% endfor %}{% endfor %}{% endfor %}
<tr class="total"><td>Total</td><td class="n">{{ tree.total.value|aud }}</td><td class="n delta {{ t.value_d|dir }}">{{ t.value_d|pct }}</td>{% if tree.ref_id %}<td class="n delta {{ t.ref_d|dir }}">{{ t.ref_d|pct }}</td>{% endif %}<td class="n muted">·</td><td class="n">{{ acc.accuracy|pct1 }}</td><td class="n bias {{ acc.bias|hl }}">{{ acc.bias|pct1s }}</td></tr>
</tbody></table>
<p class="hint">Money at every level; cases only at a material, where a case means one thing. Accuracy is the plan judged as a forecast: what the cycle {{ lag }} periods before said against what shipped, over the last 12 closed periods, 1 − Σ|error| ÷ Σ shipped, per material and summed. Bias is the signed error. <a href="{{ url_for('plan.accuracy') }}">Every lag, every unit, every period</a>.</p></div>
<div><h2><a href="{{ links.submissions }}">Plan by unit</a><span class="count">the structure the plan is submitted on</span></h2>
<table class="matrix"><thead><tr><th>Unit</th><th class="n">FY{{ fy }} net sales</th><th class="n">vs PY</th><th class="stage">Submission</th></tr></thead><tbody>
{% for u in units %}<tr><td><a href="{{ u.href }}">{{ u.unit_name }}</a></td><td class="n">{{ u.value|aud }}</td><td class="n delta {{ u.d|dir }}">{{ u.d|pct }}</td><td class="stage"><span class="state {{ u.cell.state }}">{{ u.cell.show }}</span>{% if u.cell.by %}<div class="small muted">{{ u.cell.by.split('@')[0] }} · {{ u.cell.on }}</div>{% endif %}</td></tr>{% endfor %}
</tbody></table>
<h2><a href="{{ links.versions }}">Versions</a></h2><table><thead><tr><th>Version</th><th>Cycle</th><th>Status</th><th>Reference</th></tr></thead><tbody>
{% for v in versions %}<tr><td>{{ v.version_id }}</td><td class="muted">{{ v.cycle }}</td><td><span class="state {{ v.status|upper }}">{{ v.status }}</span></td><td class="muted">{{ v.reference_version or '' }}</td></tr>{% endfor %}</tbody></table>
<h2>Actions<span class="count">what your roles reach</span></h2><div class="acts">{% for a in actions %}<a class="button" href="{{ a.href }}">{{ a.label }}<small>{{ a.says }}</small></a>{% endfor %}</div></div>
</div>
<div class="card ladder"><ol>{% for s in ladder %}<li class="{{ 'done' if s.done == s.total and s.total else ('now' if loop.index0 == now else '') }}"><i></i><div><b><a href="{{ links.submissions }}">{{ s.label }}</a></b><span class="small muted">{{ s.done }} of {{ s.total }} · {{ s.says }}</span></div></li>{% endfor %}
<li class="{{ 'done' if plan_cell.state == 'submitted' else '' }}"><i></i><div><b>Reference declared</b><span class="small muted">{{ 'reads against ' + series.ref_id if series.ref_id else 'no reference yet' }}</span></div></li></ol>
{% if plan_cell.can %}<form method="post" action="{{ url_for('plan.submit') }}"><input type="hidden" name="version" value="{{ version }}"><input type="hidden" name="subject" value="plan"><input type="hidden" name="node" value="ALL"><input type="hidden" name="act" value="{{ plan_cell.can }}">
<button class="primary">{{ 'Submit the demand plan' if plan_cell.can == 'submit' else 'Reopen the demand plan' }}</button><div class="hint">{{ plan_cell.title }}</div></form>
{% elif plan_cell.show %}<div class="small"><span class="state {{ plan_cell.state }}">{{ plan_cell.show }}</span>{% if plan_cell.by %} <span class="muted">{{ plan_cell.by.split('@')[0] }} · {{ plan_cell.on }}</span>{% endif %}</div>{% endif %}</div>
<style>.tiles{grid-template-columns:repeat(4,1fr)}.card.stat{margin:0}a.card.stat{display:block;text-decoration:none;color:inherit}a.card.stat:hover{border-color:var(--faint);background:var(--hover)}
.rows a,.ladder a,h2 a,table a{text-decoration:none}.rows a:hover,.ladder a:hover,h2 a:hover,table a:hover{text-decoration:underline}.card.stat b{font-size:1.75rem;margin:.3rem 0 .2rem}
.grid2{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:1.4rem;align-items:start;margin:0 0 .5rem}
@media (min-width:1900px){.grid2{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}.tiles{gap:1.4rem}h1{font-size:2.4rem}}.grid2>.card{margin:0}.grid2 h2{margin-top:1.2rem}
""" + FIG_CSS + """
.card.list b .count{font-weight:400;margin-left:.6rem;font-size:.85rem;color:var(--muted)}.card.list{max-height:460px;overflow-y:auto}.rows{list-style:none;margin:.6rem 0 0;padding:0}.rows li{padding:.5rem 0;border-top:1px solid var(--rule);font-size:.9rem}
.acts{display:flex;flex-direction:column;gap:.4rem}.acts .button{display:block;text-decoration:none;padding:.55rem .9rem;border:1px solid var(--rule);border-radius:var(--radius-s);background:var(--panel);font-weight:500;font-size:.9rem}.acts .button:hover{background:var(--soft)}.acts .button small{display:block;font-weight:400;color:var(--muted);font-size:.78rem}
.ladder{margin-top:1.4rem;display:flex;gap:2rem;align-items:center;flex-wrap:wrap}.ladder ol{list-style:none;display:flex;gap:1.4rem;margin:0;padding:0;flex:1 1 auto;flex-wrap:wrap}.ladder li{display:flex;gap:.6rem;align-items:center}
.ladder li i{display:inline-block;width:1.3rem;height:1.3rem;border-radius:50%;border:1.5px solid var(--faint);flex:0 0 auto;position:relative}.ladder li.done i{background:var(--ink);border-color:var(--ink)}
.ladder li.done i::after{content:"";position:absolute;left:.4rem;top:.18rem;width:.3rem;height:.6rem;border:solid var(--paper);border-width:0 2px 2px 0;transform:rotate(45deg)}.ladder li.now i{border-color:var(--ink);border-width:3px}
.ladder li b{display:block;font-size:.9rem}.ladder li span{display:block}.ladder form{text-align:right}
.state.submitted{background:var(--ink);color:var(--paper)}.state.open,.state.ready,.state.rolled_up{color:var(--ink)}.state.nothing{color:var(--faint);border-color:var(--faint)}.state.gap{border-style:dashed}
.state.FROZEN{color:var(--muted);border-color:var(--faint)}
@media (max-width:1100px){.tiles{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
""" + TREE_CSS + """</style>""" + TREE_JS + """
""" + FIG_JS

ACCURACY_PAGE = """<h1>Forecast accuracy<small>the plan judged as a forecast: what the cycle {{ lag }} periods before said, against what shipped · 1 − Σ|error| ÷ Σ shipped · bias is the signed error</small></h1>
<nav class="tabs">{% for l in lags %}<a href="{{ url_for('plan.accuracy', lag=l) }}" class="{{ 'active' if l == lag }}">lag {{ l }}</a>{% endfor %}</nav>
<div class="cards"><div class="card stat"><span>last 12 periods</span><b>{{ last.accuracy|pct1 }}</b><div class="small muted">bias {{ last.bias|pct1s }} · {{ last.actual|k }} cases shipped</div></div>
<div class="card stat"><span>prior 12</span><b>{{ prior.accuracy|pct1 }}</b><div class="small muted">bias {{ prior.bias|pct1s }}</div></div>
<div class="card stat"><span>change</span><b class="delta {{ d|dir }}">{{ d|pp }}</b><div class="small muted">accuracy, last 12 against prior 12</div></div></div>
<h2>By category, product, material<span class="count">last 12 periods · open a row</span></h2>
<table class="tree"><thead><tr><th>Material</th><th class="n">Shipped</th><th class="n">Forecast</th><th class="n">Accuracy</th><th class="n">Bias</th></tr></thead><tbody>
{% for c in tree %}<tr><td><button type="button" class="tog" data-id="{{ c.category_code }}"></button>{{ c.category_name }}</td><td class="n">{{ c.actual|n }}</td><td class="n">{{ c.forecast|n }}</td><td class="n">{{ c.accuracy|pct1 }}</td><td class="n bias {{ c.bias|hl }}">{{ c.bias|pct1s }}</td></tr>
{% for p in c.children %}<tr class="l1" data-parent="{{ c.category_code }}"><td><button type="button" class="tog" data-id="{{ p.product_code }}"></button>{{ p.product_name }}</td><td class="n">{{ p.actual|n }}</td><td class="n">{{ p.forecast|n }}</td><td class="n">{{ p.accuracy|pct1 }}</td><td class="n bias {{ p.bias|hl }}">{{ p.bias|pct1s }}</td></tr>
{% for m in p.children %}<tr class="l2" data-parent="{{ p.product_code }}"><td>{{ m.material_name }} <span class="muted">{{ m.standard_material }}</span></td><td class="n">{{ m.actual|n }}</td><td class="n">{{ m.forecast|n }}</td><td class="n">{{ m.accuracy|pct1 }}</td><td class="n bias {{ m.bias|hl }}">{{ m.bias|pct1s }}</td></tr>{% endfor %}{% endfor %}{% endfor %}
<tr class="total"><td>Total</td><td class="n">{{ last.actual|n }}</td><td class="n">{{ last.forecast|n }}</td><td class="n">{{ last.accuracy|pct1 }}</td><td class="n bias {{ last.bias|hl }}">{{ last.bias|pct1s }}</td></tr></tbody></table>
<div class="grid2"><div><h2>By planning unit</h2><table><thead><tr><th>Unit</th><th class="n">Shipped</th><th class="n">Accuracy</th><th class="n">Bias</th></tr></thead><tbody>
{% for u in units %}<tr><td>{{ u.planning_unit_name }}</td><td class="n">{{ u.actual|n }}</td><td class="n">{{ u.accuracy|pct1 }}</td><td class="n bias {{ u.bias|hl }}">{{ u.bias|pct1s }}</td></tr>{% endfor %}</tbody></table></div>
<div><h2>By period</h2><table><thead><tr><th>Period</th><th class="n">Shipped</th><th class="n">Accuracy</th><th class="n">Bias</th></tr></thead><tbody>
{% for p in periods %}<tr><td>{{ p.period }}</td><td class="n">{{ p.actual|n }}</td><td class="n">{{ p.accuracy|pct1 }}</td><td class="n bias {{ p.bias|hl }}">{{ p.bias|pct1s }}</td></tr>{% endfor %}</tbody></table></div></div>
<p class="hint">Each earlier cycle's latest view is kept at the plan's grain; a period is judged against the view from {{ lag }} cycle{{ 's' if lag > 1 }} before it. A material shipped but never forecast counts as a miss, and so does one forecast that never shipped.</p>
<style>.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem;align-items:start}""" + TREE_CSS + """</style>""" + TREE_JS


def _fmt(v: float, big: float) -> str:
    return f"{v / 1e6:,.1f}M" if big >= 1e6 else f"{v / 1000:,.0f}k"


def chart(series: dict, fy: int, width: int = 1100, height: int = 300, small: bool = False) -> str:
    """The fiscal year as a rate per week, as inline SVG: shipped (heavy, with a soft area), the view's plan continuing
    it, the reference dashed, the prior year faint — one axis. At period grain each point is the period's total over its
    weeks, the week count in its label; at week grain the weeks themselves with a rule at every period boundary. Per week
    because a period total on a 4-4-5 calendar steps every third period whatever the business did. Hover reads data-points."""
    keys = series["keys"]
    if not keys:
        return ""
    ml, mr, mt, mb = (6, 6, 6, 6) if small else (54, 86, 16, 28)
    pw, ph = width - ml - mr, height - mt - mb
    view = series["view"]; ref = series["ref"]; py = series["py"]
    vals = [x["rate"] for d in (view, ref, py) for x in d.values() if x["rate"] is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.25 or hi * 0.1
    y0, y1 = max(0.0, lo - pad), hi + pad
    ks = [k["k"] for k in keys]
    def X(i: int) -> float: return ml + pw * i / max(1, len(ks) - 1)
    def Y(v: float) -> float: return mt + ph * (1 - (v - y0) / (y1 - y0))
    def path(pts: list[tuple[float, float]]) -> str: return " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    actual = [(X(i), Y(view[k]["rate"])) for i, k in enumerate(ks) if k in view and view[k]["source"] == "actual"]
    planned = [(X(i), Y(view[k]["rate"])) for i, k in enumerate(ks) if k in view and view[k]["source"] == "plan"]
    join = (actual[-1:] if actual else []) + planned
    refp = [(X(i), Y(ref[k]["rate"])) for i, k in enumerate(ks) if k in ref]
    pyp = [(X(i), Y(py[k]["rate"])) for i, k in enumerate(ks) if k in py]
    # gridlines: four, at round numbers
    step = 10 ** max(0, len(str(int((y1 - y0) / 4))) - 1); step = max(step, 1)
    ticks = []; t = (int(y0 / step) + 1) * step
    while t < y1:
        ticks.append(t); t += step
    while len(ticks) > 5:
        ticks = ticks[::2]
    label = f"{series['unit']}, FY{fy}, by {series['grain']}"
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{label}"{"" if small else " data-points=" + chr(39) + _points(keys, view, ref, py, X, Y, series) + chr(39)}>']
    if small:
        if actual:
            out.append(f'<path d="{path(actual)}{f" L{actual[-1][0]:.1f},{mt + ph} L{actual[0][0]:.1f},{mt + ph} Z"}" fill="var(--soft)"/>')
        if pyp:
            out.append(f'<path d="{path(pyp)}" fill="none" stroke="var(--series-3)" stroke-width="1.2"/>')
        if refp:
            out.append(f'<path d="{path(refp)}" fill="none" stroke="var(--series-1)" stroke-width="1" stroke-dasharray="3 3"/>')
        if actual:
            out.append(f'<path d="{path(actual)}" fill="none" stroke="var(--series-1)" stroke-width="2.4" stroke-linejoin="round"/>')
        if join:
            out.append(f'<path d="{path(join)}" fill="none" stroke="var(--series-1)" stroke-width="1.4" stroke-linejoin="round"/>')
        out.append("</svg>")
        return "".join(out)
    for tv in ticks:
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(tv):.1f}" y2="{Y(tv):.1f}" stroke="var(--rule)"/>'
                   f'<text x="{ml - 8}" y="{Y(tv) + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)">{_fmt(tv, y1)}</text>')
    out.append(f'<text x="{ml - 8}" y="{mt - 4}" text-anchor="end" font-size="10" fill="var(--muted)">/ wk</text>')
    for i, k in enumerate(keys):
        if k["boundary"] and i > 0:
            out.append(f'<line x1="{X(i) - pw / (len(ks) - 1) / 2:.1f}" x2="{X(i) - pw / (len(ks) - 1) / 2:.1f}" y1="{mt}" y2="{mt + ph}" stroke="var(--rule)" stroke-dasharray="2 4"/>')
        if k["label"]:
            anchor = "start" if series["grain"] == "week" else "middle"
            out.append(f'<text x="{X(i):.1f}" y="{height - 8}" text-anchor="{anchor}" font-size="11" fill="var(--muted)">{k["label"]}</text>')
    if actual:
        area = path(actual) + f" L{actual[-1][0]:.1f},{mt + ph} L{actual[0][0]:.1f},{mt + ph} Z"
        out.append(f'<path d="{area}" fill="var(--soft)"/>')
    labels = []
    if pyp:
        out.append(f'<path d="{path(pyp)}" fill="none" stroke="var(--series-3)" stroke-width="1.5"/>')
        labels.append([pyp[-1][1], f"FY{fy - 1}", "var(--muted)", "400"])
    if refp:
        out.append(f'<path d="{path(refp)}" fill="none" stroke="var(--series-1)" stroke-width="1.5" stroke-dasharray="5 4"/>')
        labels.append([refp[-1][1], series["ref_id"], "var(--series-1)", "400"])
    if actual:
        out.append(f'<path d="{path(actual)}" fill="none" stroke="var(--series-1)" stroke-width="3.5" stroke-linejoin="round"/>')
    if join:
        out.append(f'<path d="{path(join)}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>')
        labels.append([join[-1][1], "plan", "var(--series-1)", "600"])
    # direct labels at the right edge, pushed apart where they would overlap
    labels.sort(key=lambda l: l[0])
    for i in range(1, len(labels)):
        if labels[i][0] - labels[i - 1][0] < 13:
            labels[i][0] = labels[i - 1][0] + 13
    for y, text, fill, weight in labels:
        out.append(f'<text x="{ml + pw + 8}" y="{y + 4:.1f}" font-size="11" font-weight="{weight}" fill="{fill}">{text}</text>')
    if actual and planned:
        out.append(f'<text x="{actual[-1][0]:.1f}" y="{mt + 2}" text-anchor="middle" font-size="10" fill="var(--muted)">last closed</text>')
    out.append(f'<line class="cross" style="display:none" x1="0" x2="0" y1="{mt}" y2="{mt + ph}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="2 3"/>')
    for s in ("view", "ref", "py"):
        out.append(f'<circle class="dot" data-s="{s}" style="display:none" r="4.5" fill="var(--paper)" stroke="var(--series-1)" stroke-width="2"/>')
    out.append("</svg>")
    return "".join(out)


def _points(keys, view, ref, py, X, Y, series) -> str:
    import json
    aud = series["measure"] != "cases"
    def text(x: dict) -> str:
        rate = f"{'$' if aud else ''}{x['rate']:,.0f} / wk"
        return rate if x["weeks"] == 1 else f"{rate} · {'$' if aud else ''}{x['total']:,.0f} in {x['weeks']} wks"
    pts = []
    for i, k in enumerate(keys):
        d = {"x": round(X(i), 1), "label": k["say"]}
        if k["k"] in view:
            d["view"] = {"y": round(Y(view[k["k"]]["rate"]), 1), "name": "shipped" if view[k["k"]]["source"] == "actual" else "plan", "text": text(view[k["k"]])}
        if k["k"] in ref:
            d["ref"] = {"y": round(Y(ref[k["k"]]["rate"]), 1), "name": series["ref_id"], "text": text(ref[k["k"]])}
        if k["k"] in py:
            d["py"] = {"y": round(Y(py[k["k"]]["rate"]), 1), "name": f"FY{int(k['k'][:4]) - 1}", "text": text(py[k["k"]])}
        pts.append(d)
    return json.dumps(pts).replace("'", "&#39;")


REVENUE_PAGE = """<form class="toolbar" method="get"><label>version<select name="version" onchange="this.form.submit()">{% for v in versions %}<option value="{{ v.version_id }}" {{ 'selected' if v.version_id == version }}>{{ v.version_id }} · {{ v.status }}</option>{% endfor %}</select></label></form>
<h1>Financial forecast<small>{{ version }} · FY{{ fy }} · net sales invoiced, the latest view and {{ ref_id or 'no reference' }} laid over one another, per week</small></h1>
{% if years|length > 1 %}<nav class="tabs">{% for y in years %}<a href="{{ y.href }}" class="{{ 'active' if y.fy == fy }}">FY{{ y.fy }}</a>{% endfor %}</nav>{% endif %}
<div class="cards tiles">
<div class="card stat"><span>FY{{ fy }} latest view · AUD</span><b>{{ lfl.year|m }}</b><div class="small delta {{ d.py|dir }}">{% if lfl.py_year %}{{ d.py|pct }} vs FY{{ fy - 1 }} invoiced{% elif lfl.py_part %}FY{{ fy - 1 }} is still closing — no year to read against{% else %}no FY{{ fy - 1 }} invoiced to read against{% endif %}</div></div>
<div class="card stat"><span>Invoiced to date</span><b>{{ lfl.invoiced|m }}</b><div class="small muted">{% if series.n_actual %}{{ series.n_actual }} closed period{{ 's' if series.n_actual > 1 }} of {{ table|length }}{% else %}no period closed yet{% endif %}</div></div>
<div class="card stat"><span>{% if lfl.from %}{{ lfl.from.label.split(' ')[0] }}–{{ lfl.to.label.split(' ')[0] }} vs {{ ref_id }}{% else %}Against the reference{% endif %}</span><b>{{ lfl.gap|aud if lfl.gap is not none else '—' }}</b><div class="small delta {{ d.lfl|dir }}">{% if lfl.from %}{{ d.lfl|pct }} on the periods both value{% else %}no periods both value{% endif %}</div></div>
<div class="card stat"><span>{{ ref_id or 'Reference' }} · FY{{ fy }}</span><b>{{ lfl.ref_year|m if lfl.ref_year else '—' }}</b><div class="small muted">{{ ref_kind or 'this version names no reference' }}</div></div>
</div>
<div class="card fig"><div class="fighead"><b>Net sales per week</b><span class="crumbs">{% for n in drill.path %}{% if loop.last %}<b>{{ n.label }}</b>{% else %}<a href="{{ n.href }}">{{ n.label }}</a> ▸ {% endif %}{% endfor %}<a class="switch" href="{{ drill.other }}">by {{ 'material' if drill.dim == 'customer' else 'customer' }}</a><span class="seg">{% for g in grains %}{% if g.on %}<b>{{ g.label }}</b>{% else %}<a href="{{ g.href }}">{{ g.label }}</a>{% endif %}{% endfor %}</span></span><span class="legend">
<span class="key"><i class="sw actual"></i>invoiced</span><span class="key"><i class="sw plan"></i>{{ version }}</span>{% if ref_id %}<span class="key"><i class="sw ref"></i>{{ ref_id }}</span>{% endif %}<span class="key"><i class="sw py"></i>FY{{ fy - 1 }} invoiced</span></span></div>
{{ chart|safe }}<div class="tip" hidden></div>
<p class="hint">Every point is a rate per week{% if grain == 'period' %} — the period's total over its weeks, the week count in the label — so a five-week period does not read as a step{% else %} — the weeks themselves, a rule at each period boundary{% endif %}. History is what was invoiced; the plan is cases at the list and terms in force.</p></div>
<h2>By period<span class="count">{{ drill.label }} · per week, then the period's total</span></h2>
<table><thead><tr><th>Period</th><th class="n">Weeks</th><th></th><th class="n">{{ version }} / wk</th><th class="n">{{ ref_id or 'Reference' }} / wk</th><th class="n">FY{{ fy - 1 }} / wk</th><th class="n">{{ version }}</th><th class="n">{{ ref_id or 'Reference' }}</th><th class="n">Gap</th><th class="n">Gap %</th></tr></thead><tbody>
{% for r in table %}<tr class="{{ 'closed' if r.source == 'actual' }}"><td>{{ r.label }}</td><td class="n">{{ r.weeks }}</td><td><span class="small muted">{{ 'invoiced' if r.source == 'actual' else ('plan' if r.source else '') }}</span></td><td class="n">{{ r.view_rate|aud }}</td><td class="n">{{ r.ref_rate|aud }}</td><td class="n muted">{{ r.py_rate|aud }}</td><td class="n">{{ r.view|aud }}</td><td class="n">{{ r.ref|aud }}</td><td class="n">{{ r.gap|aud }}</td><td class="n delta {{ r.gap_d|dir }}">{{ r.gap_d|pct }}</td></tr>{% endfor %}
<tr class="total"><td>FY{{ fy }}</td><td class="n">{{ table|sum(attribute='weeks') }}</td><td></td><td></td><td></td><td></td><td class="n">{{ lfl.year|aud }}</td><td class="n">{{ lfl.ref_year|aud }}</td><td class="n">{{ lfl.gap|aud }}</td><td class="n delta {{ d.lfl|dir }}">{{ d.lfl|pct }}</td></tr>
</tbody></table>
<p class="hint">The gap is read only where both versions value the period: the closed periods are what was invoiced, not a forecast, so they carry no gap here{% if lfl.from %} — the year's gap is {{ lfl.from.label.split(' ')[0] }} to {{ lfl.to.label.split(' ')[0] }}{% endif %}. Last year is read by its own weeks, so a 53-week year compares.</p>
{% if split %}<h2>By {{ split_of }}<span class="count">FY{{ fy }} · open one to make it the chart</span></h2>
<table><thead><tr><th>{{ split_of|capitalize }}</th><th class="n">FY{{ fy }} {{ version }}</th><th class="n">vs FY{{ fy - 1 }}</th><th class="n">Invoiced to date</th><th class="n">{{ version }}{% if lfl.from %} {{ lfl.from.label.split(' ')[0] }}–{{ lfl.to.label.split(' ')[0] }}{% endif %}</th><th class="n">{{ ref_id or 'Reference' }}</th><th class="n">Gap</th><th class="n">Gap %</th></tr></thead><tbody>
{% for c in split %}<tr><td><a href="{{ c.href }}">{{ c.label }}</a></td><td class="n">{{ c.lfl.year|aud }}</td><td class="n delta {{ c.py_d|dir }}">{{ c.py_d|pct }}</td><td class="n">{{ c.lfl.invoiced|aud }}</td><td class="n">{{ c.lfl.view|aud }}</td><td class="n">{{ c.lfl.ref|aud }}</td><td class="n">{{ c.lfl.gap|aud }}</td><td class="n delta {{ c.gap_d|dir }}">{{ c.gap_d|pct }}</td></tr>{% endfor %}
<tr class="total"><td>{{ drill.label }}</td><td class="n">{{ lfl.year|aud }}</td><td class="n delta {{ d.py|dir }}">{{ d.py|pct }}</td><td class="n">{{ lfl.invoiced|aud }}</td><td class="n">{{ lfl.view|aud }}</td><td class="n">{{ lfl.ref|aud }}</td><td class="n">{{ lfl.gap|aud }}</td><td class="n delta {{ d.lfl|dir }}">{{ d.lfl|pct }}</td></tr>
</tbody></table>{% endif %}
<style>.tiles{grid-template-columns:repeat(4,1fr)}.card.stat{margin:0}.card.stat b{font-size:1.75rem;margin:.3rem 0 .2rem}tr.closed td{color:var(--muted)}table a{text-decoration:none}table a:hover{text-decoration:underline}
@media (max-width:1100px){.tiles{grid-template-columns:repeat(2,1fr)}}
""" + TREE_CSS + FIG_CSS + """</style>""" + FIG_JS
