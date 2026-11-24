"""Planning roles under Admin (DEC-20261124-07): the role architecture, in four steps.

1. **Role types** — the kinds of job: a cardinality (single, or multiple with the dimensions and levels that tell its
   roles apart).
2. **Entitlements** — the authority each role type has over each planning fact: read, review or prepare, each including
   the one before; exactly one type prepares a fact.
3. **Roles** — each a role type at one member of its level, with its own number and name.
4. **Assignments** — who fills each role. People change; the role does not.

Each step is a register (plan/reg_role_type, reg_planning_entitlement, reg_planning_role, reg_planning_assignment) read
as a model; what follows — a person's authority over a fact, in a place — is dims.planning_authority, and a right a fact
names is held through it. Registered on the plan's blueprint by `register(...)`, called from `face/__main__.py`.

Each step is read within one planning process (DEC-20261124-08), chosen above the steps and carried in the address
(`?process=`): the process is set on a fact and on a role type, and an entitlement, a role and an assignment inherit it."""
from __future__ import annotations

import datetime as dt
import re

from chassis import receipts
from chassis.landing import LogLanding
from chassis.warehouse import Busy, q
from flask import redirect, request, url_for

from . import figures
from .words import said

VERB = "register.roles.maintain"
TYPES = LogLanding("plan", "reg_role_type", ["type_code", "type_name", "purpose", "cardinality", "site_level", "customer_level", "cost_centre_level", "process", "set_by", "set_on"])
DEFAULT_PROCESS = "ibp"
ENTITLEMENTS = LogLanding("plan", "reg_planning_entitlement", ["fact", "type_code", "level", "set_by", "set_on"])
ROLES = LogLanding("plan", "reg_planning_role", ["role_no", "type_code", "role_name", "purpose", "site", "customer", "cost_centre", "status", "set_by", "set_on"])
ASSIGNMENTS = LogLanding("plan", "reg_planning_assignment", ["person", "role_no", "valid_from", "valid_to", "set_by", "set_on"])
DIMS = (("site", "Site"), ("customer", "Customer"), ("cost_centre", "Cost centre"))
# each dimension's levels: what it is called, and its members
LEVELS = {
    "site": {"plant": ("Plant", "select node_code as code, node_name as name from dims.dim_node where can_make order by 2"),
             "site": ("Any site", "select node_code as code, node_name as name from dims.dim_node order by 2")},
    "customer": {"planning_unit": ("Planning unit", "select distinct planning_unit as code, planning_unit_name as name from dims.dim_account where planning_unit is not null order by 2"),
                 "account": ("Account", "select distinct account_code as code, account_name as name from dims.dim_account order by 2")},
    "cost_centre": {"function": ("Function", "select descendant_code as code, descendant_code as name from dims.dim_organisation_hierarchy where depth = 0 and descendant_level = 'function' order by 1"),
                    "cost_centre": ("Cost centre", "select descendant_code as code, descendant_code as name from dims.dim_organisation_hierarchy where depth = 0 and descendant_is_leaf order by 1")},
}
AUTH = (("", "—"), ("read", "Read"), ("review", "Review"), ("prepare", "Prepare"))
STEPS = (("types", "Role types", "the kinds of job", "plan.planning_types"), ("entitlements", "Entitlements", "each type's authority over each fact", "plan.planning_entitlements"),
         ("roles", "Roles", "each type in a business context", "plan.planning_roles"), ("assignments", "Assignments", "who fills each role", "plan.planning_assignments"))

FLOW = """{% macro flow(on) %}<div class="procs"><span class="small muted">Planning process</span>{% for p in processes %}<a href="{{ url_for(request.endpoint, process=p.process) }}" class="{{ 'on' if p.process == process }}">{{ p.process_name }}</a>{% endfor %}</div>
<div class="flow">{% for k, name, says, ep in steps %}{% if not loop.first %}<span class="arrow">→</span>{% endif %}<a href="{{ url_for(ep, process=process) }}" class="{{ 'on' if k == on }}"><span class="step">{{ loop.index }}</span><b>{{ name }}</b><span class="small muted">{{ says }}</span></a>{% endfor %}</div>
<style>.procs{display:flex;gap:.4rem;align-items:center;margin:0 0 .7rem}.procs a{border:1px solid var(--line,#ccc);border-radius:999px;padding:.2rem .8rem;text-decoration:none;color:inherit}.procs a.on{border-color:var(--ink);background:var(--ink);color:var(--paper,#fff)}.procs .muted{margin-right:.3rem}
.flow{display:flex;align-items:stretch;gap:.6rem;margin:0 0 1.2rem}.flow a{flex:1;display:flex;flex-direction:column;gap:.15rem;border:1px solid var(--line,#ccc);border-radius:.6rem;padding:.55rem .8rem;text-decoration:none;color:inherit}.flow a.on{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink);background:var(--panel)}.flow .arrow{align-self:center;color:var(--muted)}
.step{display:inline-block;border:1px solid var(--ink);border-radius:999px;width:1.5rem;height:1.5rem;line-height:1.4rem;text-align:center;font-size:.8rem}
.field{display:flex;flex-direction:column;gap:.2rem;margin:.5rem 0}.field input,.field textarea,.field select{font:inherit;padding:.3rem .45rem}.fields{display:grid;grid-template-columns:9rem 1fr;gap:1rem}
.tick{display:grid;grid-template-columns:1.4rem 9rem 1fr;gap:.2rem .4rem;align-items:baseline;margin:.3rem 0}.two{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:1.4rem;align-items:start}
.actions{display:flex;gap:.8rem;align-items:center;margin-top:.8rem}tr.type td{background:var(--soft);font-weight:600}tr.type td .small{font-weight:400}td.in{padding-left:1.6rem}td.no{font-variant-numeric:tabular-nums;white-space:nowrap}
.indent{margin:.4rem 0 0 1.8rem;padding-left:.9rem;border-left:2px solid var(--ink)}
table.own th{vertical-align:bottom;min-width:5.5rem;white-space:normal}table.own td:first-child{min-width:13rem}table.own td.prepare{box-shadow:inset 0 0 0 1px var(--ink)}table.own select.cell{font:inherit;font-size:.85rem;background:transparent;color:inherit;border:0}table.own td.prepare select.cell{font-weight:700}</style>{% endmacro %}
{% macro receipt(last) %}{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}{% endmacro %}"""

P_TYPES = FLOW + """{{ flow('types') }}<h1>Role types<small>step 1 — the kinds of job {{ process_name|lower }} works with</small></h1>
<p class="hint">A <b>role type</b> is the kind of job: demand planner, purchasing manager. It says its cardinality: <b>Single</b> — one role for the whole business — or <b>Multiple</b>, and then the dimensions that tell its roles apart and the level of each at which responsibility is held. What a type may do is step 2; its roles, each in one place, are step 3; who fills them is step 4.</p>
<h2>Role types<span class="count">{{ types|length }}</span></h2>
<table><thead><tr><th>Role type</th><th>Cardinality</th><th>Dimension</th><th>Responsibility level</th><th>Prepares <span class="small muted">— step 2</span></th><th class="n">Roles <span class="small muted">— step 3</span></th><th>Not covered</th></tr></thead><tbody>
{% for t in types %}<tr><td><b>{{ t.type_name }}</b><div class="small muted">{{ t.purpose }}</div></td><td class="small">{{ 'Multiple' if t.cardinality == 'multiple' else 'Single' }}</td>
<td class="small{{ ' muted' if not t.dims }}">{{ t.dims|map(attribute='dim_name')|join(' × ') or '—' }}</td><td class="small{{ ' muted' if not t.dims }}">{{ t.dims|map(attribute='level_name')|join(' × ') or '—' }}</td>
<td class="small{{ ' muted' if not t.prepares }}">{{ t.prepares|join('; ') or 'nothing' }}</td><td class="n">{{ t.n_roles }}</td><td class="small{{ ' muted' if not t.gaps }}">{{ t.gaps|join('; ') or '—' }}</td></tr>{% endfor %}
</tbody></table>
<p class="hint">Prepares, roles and not covered are read from the steps after this one, so a type added here shows what it still lacks.</p>
{% if may %}<form class="card" style="max-width:40rem;margin-top:1.2rem" method="post" action="{{ url_for('plan.planning_type_add') }}"><input type="hidden" name="process" value="{{ process }}"><h3 style="margin-top:0">New role type <span class="small muted">in {{ process_name|lower }}</span></h3>
<label class="field small">Name <input name="type_name" required placeholder="Category buyer"></label>
<label class="field small">What it is for <textarea name="purpose" rows="2"></textarea></label>
<h3 style="margin-top:1rem">Cardinality</h3><p class="hint">Is there one role of this type, or several?</p>
<div class="tick"><input type="radio" name="cardinality" value="single" checked id="c-single"><label for="c-single">Single</label><span class="small muted">one role, for the whole business</span></div>
<div class="tick"><input type="radio" name="cardinality" value="multiple" id="c-multiple"><label for="c-multiple">Multiple</label><span class="small muted">several roles — say below what tells them apart</span></div>
<div class="indent" id="dims" hidden><h3 style="margin:.2rem 0">One role for each…</h3><p class="hint">Tick the dimensions that tell its roles apart, and for each the level responsibility is held at. This is the pattern only: the roles the business needs are named at step 3.</p>
{% for d, dn in dims %}<div class="tick"><input type="checkbox" name="dim" value="{{ d }}" id="d-{{ d }}"><label for="d-{{ d }}">{{ dn }}</label><label class="small">level <select name="level_{{ d }}">{% for lv, (ln, _) in levels[d].items() %}<option value="{{ lv }}">{{ ln }}</option>{% endfor %}</select></label></div>{% endfor %}</div>
<div class="actions"><button class="primary" onclick="this.textContent='Adding…'">Add the role type</button><span class="hint">next: its entitlements</span></div></form>
<script>(function(){var f=document.querySelector('form[action$="/planning/types/add"]');if(!f)return;function show(){document.getElementById('dims').hidden=!f.querySelector('#c-multiple').checked;}f.addEventListener('change',show);show();})();</script>
{% else %}<p class="hint">Role types are set up by {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}{{ receipt(last) }}"""

P_ENT = FLOW + figures.SAVE_BAR + """{{ flow('entitlements') }}<h1>Entitlements<small>step 2 — the authority each role type has over each planning fact</small></h1>
<p class="hint">Authority over a fact is one of three levels, each including the one before. <b>Read</b>: uses the figure once it is published. <b>Review</b>: also sees it once it is sent, before it is final. <b>Prepare</b>: also enters it and sends it. Exactly <b>one role type prepares</b> a fact — its owner — and each of its roles prepares it in its own place. Entitlements are set on the type, never on a role.</p>
<form class="toolbar" method="get" action="{{ url_for('plan.planning_entitlements') }}" style="display:flex;gap:.8rem;align-items:center;flex-wrap:wrap"><input type="hidden" name="process" value="{{ process }}"><label class="small">role type <select name="type" onchange="this.form.submit()"><option value="">all</option>{% for t in every_type %}<option value="{{ t.type_code }}" {{ 'selected' if one and one.type_code == t.type_code }}>{{ t.type_name }}</option>{% endfor %}</select></label>
{% if one %}<span class="small">{% if all_facts %}<b>every fact</b> · <a href="{{ url_for('plan.planning_entitlements', process=process, type=one.type_code) }}">only its facts</a>{% else %}<b>the facts it has a cell on or reads</b> · <a href="{{ url_for('plan.planning_entitlements', process=process, type=one.type_code, facts='all') }}">every fact</a>{% endif %}</span>{% endif %}</form>
{% if not one %}<p class="small"><span class="muted">role types shown:</span> {% if all_types %}<a href="{{ url_for('plan.planning_entitlements', process=process) }}">those with a cell</a> · <b>every role type</b>{% else %}<b>those with a cell</b> · <a href="{{ url_for('plan.planning_entitlements', types='all', process=process) }}">every role type</a>{% endif %} <span class="muted">· the facts and role types of {{ process_name|lower }}; a fact of another process is used, once published, through what it is calculated from — never given here</span></p>{% endif %}
<form method="post" action="{{ url_for('plan.planning_entitlements_set') }}"><input type="hidden" name="process" value="{{ process }}">{% if all_types %}<input type="hidden" name="types" value="all">{% endif %}{% if one %}<input type="hidden" name="type" value="{{ one.type_code }}">{% if all_facts %}<input type="hidden" name="facts" value="all">{% endif %}{% endif %}
<div style="overflow-x:auto"><table class="own"><thead><tr><th>Planning fact</th>{% if one %}<th>Prepared by<div class="small muted">its owner</div></th>{% endif %}{% for t in types %}<th>{{ t.type_name }}<div class="small muted">{{ 'Multiple' if t.cardinality == 'multiple' else 'Single' }} · {{ t.n_roles }} role{{ '' if t.n_roles == 1 else 's' }}{% if t.dims %}, by {{ t.dims|map(attribute='level_name')|join(' × ')|lower }}{% endif %}</div></th>{% endfor %}</tr></thead><tbody>
{% for f in facts %}<tr><td><b>{{ f.fact_name }}</b><div class="small muted">{{ f.kind_says }}{% if f.right_verb %} · the app's right follows this row{% endif %}</div></td>{% if one %}<td class="small">{{ f.prepared_by or '—' }}</td>{% endif %}
{% for t in types %}{% set c = cells.get((f.fact, t.type_code), '') %}<td class="{{ c }}">{% if may %}<select class="cell" name="c|{{ f.fact }}|{{ t.type_code }}">{% for v, lab in auth %}<option value="{{ v }}" {{ 'selected' if v == c }}>{{ lab }}</option>{% endfor %}</select>{% else %}{{ c|capitalize }}{% endif %}{% if not c and (f.fact, t.type_code) in implied %}<div class="small muted"><i>reads it — its own fact uses it</i></div>{% endif %}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>
{% if may %}{{ save_bar(discard='reset', note='saved by ' ~ who ~ ' · choosing Prepare moves the fact: its former preparer becomes Review') }}{% endif %}</form>
<h2>What follows<span class="count">read from the table and from what each fact uses</span></h2>
<table><thead><tr><th>Role type</th><th>Prepares</th><th>Through its roles</th><th>Waits on</th><th>Is waited on by</th></tr></thead><tbody>
{% for r in follows %}<tr><td><b>{{ r.type_name }}</b></td><td class="small">{{ r.prepares|join('; ') }}</td><td class="small{{ ' muted' if not r.roles }}">{{ r.roles|join(' · ') or 'no role defined yet' }}</td>
<td class="small">{% for o, fs in r.waits_on.items() %}{{ o }} <span class="muted">({{ fs|join(', ') }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nobody — set on its own</span>{% endfor %}</td>
<td class="small">{% for o, fs in r.waited_by.items() %}{{ o }} <span class="muted">({{ fs|join(', ') }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nobody</span>{% endfor %}</td></tr>{% endfor %}
</tbody></table>
<p class="hint">Signing off is not a level of authority over a fact: it is held for a stage of the review cycle, and is set with the stages under plan administration.</p>{{ receipt(last) }}
<script>(function(){var f=document.querySelector('form[action$="/planning/entitlements/set"]');if(!f)return;[].forEach.call(f.querySelectorAll('select.cell'),function(s){s.setAttribute('data-was',s.value);});
function say(){var n=0;[].forEach.call(f.querySelectorAll('select.cell'),function(s){if(s.value!==s.getAttribute('data-was'))n++;s.closest('td').className=s.value;});var b=f.querySelector('.savebar'),c=b&&b.querySelector('.savecount');if(c){c.textContent=n?n+' cell'+(n==1?'':'s')+' changed and not saved':'nothing changed';b.classList.toggle('dirty',n>0);}}
f.addEventListener('change',function(e){var s=e.target;if(!s.matches('select.cell'))return;if(s.value==='prepare'){[].forEach.call(s.closest('tr').querySelectorAll('select.cell'),function(o){if(o!==s&&o.value==='prepare')o.value='review';});}say();});
f.addEventListener('click',function(e){if(e.target.closest('[data-discard="reset"]')){[].forEach.call(f.querySelectorAll('select.cell'),function(s){s.value=s.getAttribute('data-was');});say();}});setTimeout(say,0);})();</script>"""

P_ROLES = FLOW + """{{ flow('roles') }}<h1>Roles<small>step 3 — each role is a role type in one business context</small></h1>
<p class="hint">A <b>role</b> is a role type at one member of its level, with its own number: demand planner for one planning unit, for another — several roles of one type. It has its type's authority there, and nothing of its own. Every role of a type sits at the type's level, one member each, so two never cover the same ground.</p>
<div class="two"><div>
<h2>Role types and their roles<span class="count">{{ types|length }} types · {{ n_roles }} roles</span></h2>
<table><thead><tr><th>No.</th><th>Role</th><th>Business context</th><th>Held by</th></tr></thead><tbody>
{% for t in types %}<tr class="type"><td colspan="2">{{ t.type_name }} <span class="small muted">· role type · {{ 'Multiple, by ' ~ (t.dims|map(attribute='says')|join(' × ')) if t.cardinality == 'multiple' else 'Single' }}</span></td><td></td>
<td class="acts">{% if may and t.can_add %}<a class="button act" href="{{ url_for('plan.planning_roles', type=t.type_code, process=process) }}#new">Add a role</a>{% endif %}</td></tr>
{% for r in t.roles %}<tr><td class="no in">{{ r.role_no }}</td><td>{{ r.role_name }}</td><td class="small{{ ' muted' if not r.context }}">{{ r.context or 'whole business' }}</td><td class="small{{ ' muted' if not r.held }}">{{ r.held|join(', ') or 'nobody yet' }}</td></tr>{% endfor %}
{% if t.gaps %}<tr><td class="in"></td><td class="small muted" colspan="3"><i>no {{ t.type_name|lower }} covers: {{ t.gaps|join('; ') }}</i></td></tr>{% endif %}{% endfor %}
</tbody></table>
<p class="hint">The number is the role's identity and never changes. A place no role of the type covers is listed beneath it.</p>
</div><div id="new">
{% if may %}<div class="card"><h3 style="margin-top:0">New planning role</h3>
<form method="get" action="{{ url_for('plan.planning_roles') }}#new"><input type="hidden" name="process" value="{{ process }}"><label class="field small">Role type <select name="type" onchange="this.form.submit()">{% for t in types %}<option value="{{ t.type_code }}" {{ 'selected' if chosen and t.type_code == chosen.type_code }} {{ 'disabled' if not t.can_add }}>{{ t.type_name }}{{ '' if t.can_add else ' — its one role exists' }}</option>{% endfor %}</select>
<span class="muted">{% if chosen %}{{ 'Multiple, by ' ~ (chosen.dims|map(attribute='says')|join(' × ')) if chosen.cardinality == 'multiple' else 'Single — one role, whole business' }} · what it may do is set on the type{% endif %}</span></label></form>
{% if chosen and chosen.can_add %}<form method="post" action="{{ url_for('plan.planning_role_add') }}"><input type="hidden" name="process" value="{{ process }}"><input type="hidden" name="type_code" value="{{ chosen.type_code }}">
{% if chosen.dims %}<h3 style="margin-top:1rem">Business context</h3><p class="hint">Where this role is held. The type says which dimension and level, so only the members at that level are offered.</p>
{% for d in chosen.dims %}<label class="field small">{{ d.dim_name }} — {{ d.level_name|lower }} <select name="{{ d.dim }}">{% for m in d.members %}<option value="{{ m.code }}">{{ m.name }}</option>{% endfor %}</select></label>{% endfor %}
{% if chosen.taken %}<p class="small muted">Already covered: {{ chosen.taken|join('; ') }}.</p>{% endif %}{% endif %}
<div class="fields" style="margin-top:.6rem"><label class="field small">Role number <input name="role_no" value="{{ next_no }}" required><span class="muted">next free · unique across every process · never reused</span></label>
<label class="field small">Name <input name="role_name" placeholder="{{ chosen.type_name }}{{ ', its place' if chosen.dims }}"><span class="muted">left empty: the type{{ ' and the place' if chosen.dims }}</span></label></div>
<label class="field small">What it is for <textarea name="purpose" rows="2"></textarea></label>
<div class="actions"><button class="primary" onclick="this.textContent='Defining…'">Define the role</button><span class="hint">nobody holds it until it is assigned</span></div></form>{% endif %}</div>
{% else %}<p class="hint">Roles are defined by {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}
</div></div>{{ receipt(last) }}"""

P_ASG = FLOW + """{{ flow('assignments') }}<h1>Assignments<small>step 4 — who fills each role</small></h1>
<p class="hint">A person is assigned a role. The role already says where: its business context is part of it. People change; the role does not — cover and handover are another assignment to the same role, so a role may be given to more than one person and a person may hold several. The role is the owner; whoever fills it acts as it.</p>
<table><thead><tr><th>Person</th><th>Role</th><th>From</th><th>To</th><th>So prepares</th><th></th></tr></thead><tbody>
{% for a in rows %}<tr class="{{ 'muted' if not a.live }}"><td>{{ a.person }}</td><td><span class="small muted">{{ a.role_no }}</span> {{ a.role_name }}</td><td class="small">{{ a.valid_from or '' }}</td><td class="small{{ ' muted' if not a.valid_to }}">{{ a.valid_to or 'open' }}</td><td class="small{{ ' muted' if not a.prepares }}">{{ a.prepares|join('; ') or '—' }}</td>
<td class="acts">{% if may and a.live %}<form class="inline" method="post" action="{{ url_for('plan.planning_assignment_end') }}"><input type="hidden" name="process" value="{{ process }}"><input type="hidden" name="person" value="{{ a.person }}"><input type="hidden" name="role_no" value="{{ a.role_no }}"><button class="act">End</button></form>{% endif %}</td></tr>{% endfor %}
</tbody></table>
{% if may %}<form class="card" style="margin-top:1rem" method="post" action="{{ url_for('plan.planning_assignment_give') }}"><input type="hidden" name="process" value="{{ process }}"><h3 style="margin-top:0">Assign a role</h3>
<div style="display:flex;flex-wrap:wrap;gap:1rem;align-items:end"><label class="field small">Person <select name="person">{% for p in people %}<option>{{ p }}</option>{% endfor %}</select></label>
<label class="field small">Role <select name="role_no">{% for r in roles %}<option value="{{ r.role_no }}">{{ r.role_no }} · {{ r.role_name }}</option>{% endfor %}</select></label>
<label class="field small">From <input type="date" name="valid_from" value="{{ today }}"></label><label class="field small">To <input type="date" name="valid_to"><span class="muted">empty: open</span></label>
<button class="primary" style="margin-bottom:.5rem" onclick="this.textContent='Assigning…'">Assign</button></div></form>{% else %}<p class="hint">Roles are assigned by {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}
<div class="two" style="margin-top:1.2rem"><div class="card"><h3 style="margin-top:0">Roles nobody holds</h3>{% if empty %}<table><thead><tr><th>Role</th><th>Left with no one to prepare</th></tr></thead><tbody>
{% for r in empty %}<tr><td><span class="small muted">{{ r.role_no }}</span> {{ r.role_name }}</td><td class="small{{ ' muted' if not r.prepares }}">{{ r.prepares|join('; ') or '—' }}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">Every role is held.</p>{% endif %}</div>
<div class="card"><h3 style="margin-top:0">Roles with cover</h3>{% if cover %}<table><thead><tr><th>Role</th><th>Held by</th></tr></thead><tbody>
{% for r in cover %}<tr><td><span class="small muted">{{ r.role_no }}</span> {{ r.role_name }}</td><td class="small">{{ r.held|join(', ') }}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">No role is held by more than one person.</p>{% endif %}</div></div>{{ receipt(last) }}"""


def members(dim: str, level: str) -> list[dict]:
    return q(LEVELS[dim][level][1]) if dim in LEVELS and level in LEVELS[dim] else []


def processes() -> list[dict]:
    return q("select process, process_name from dims.ref_process order by ord")


def current_process() -> str:
    """The process the screens read: from the address or the form, else integrated business planning."""
    p = request.values.get("process") or DEFAULT_PROCESS
    return p if p in {r["process"] for r in processes()} else DEFAULT_PROCESS


def state(process: str) -> dict:
    """The four steps as they stand within one process, and what is read across them. A role and an assignment are of
    the process of their type."""
    types = q("select * from dims.planning_role_type where process = ? order by type_name", process)
    roles = q("select r.* from dims.planning_role r join dims.planning_role_type t using (type_code) where r.live and t.process = ? order by r.role_no", process)
    asg = q("""select a.* from dims.planning_assignment a join dims.planning_role r using (role_no) join dims.planning_role_type t on t.type_code = r.type_code
             where t.process = ? order by a.live desc, a.role_no, a.person""", process)
    facts = q("select * from dims.ref_fact where process = ? order by ord", process)
    cells = {(r["fact"], r["type_code"]): r["level"] for r in q("select fact, type_code, level from dims.planning_entitlement where process = ? and type_process = ?", process, process)}
    names = {f["fact"]: f["fact_name"] for f in facts}
    label: dict = {}
    for t in types:
        t["dims"] = []
        for d, dn in DIMS:
            lv = t.get(f"{d}_level")
            if t["cardinality"] == "multiple" and lv in LEVELS[d]:
                ms = members(d, lv)
                label.update({(d, m["code"]): m["name"] for m in ms})
                t["dims"].append({"dim": d, "dim_name": dn, "level": lv, "level_name": LEVELS[d][lv][0], "says": f"{dn.lower()} at {LEVELS[d][lv][0].lower()}", "members": ms})
    held: dict = {}
    for a in asg:
        if a["live"]:
            held.setdefault(a["role_no"], []).append(a["person"].split("@")[0])
    for r in roles:
        r["context"] = " × ".join(label.get((d, r[d]), r[d]) for d, _ in DIMS if r.get(d))
        r["held"] = held.get(r["role_no"], [])
    for t in types:
        t["roles"] = [r for r in roles if r["type_code"] == t["type_code"]]
        t["n_roles"] = len(t["roles"])
        t["prepares"] = [names[f] for f in names if cells.get((f, t["type_code"])) == "prepare"]
        t["can_add"] = t["cardinality"] == "multiple" or not t["roles"]
        t["gaps"], t["taken"] = [], [r["context"] for r in t["roles"] if r["context"]]
        if len(t["dims"]) == 1:                               # one dimension: a member with no role is a gap; with two, only the combinations needed are defined
            d = t["dims"][0]
            used = {r[d["dim"]] for r in t["roles"]}
            t["gaps"] = [m["name"] for m in d["members"] if m["code"] not in used]
    return {"types": types, "roles": roles, "asg": asg, "facts": facts, "cells": cells, "names": names}


def register(bp, page, who_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    scoped["planning"] = {"what": "planning roles", "says": "run completed — the planning roles stand as set"}

    def show(tpl: str, title: str, active: str, **kw):
        who = who_fn(); ps = processes(); pr = current_process()
        return page(tpl, title=title, active=active, steps=STEPS, may=roles.may(who, VERB), holders=reads.holders(VERB), last=session.last,
                    receipt_acts=("planning.",), processes=ps, process=pr, process_name=next((p["process_name"] for p in ps if p["process"] == pr), pr), **kw)

    def who_may(who: str) -> dict:
        may = roles.may(who, VERB)
        return {"check": "who may set up planning roles", "ok": may,
                "says": f"{who} holds {said(VERB)}" if may else f"{who} does not hold {said(VERB)} — set up by {', '.join(reads.holders(VERB)) or 'nobody yet'}"}

    def done(act: str, who: str, subject: str, checks: list, place, ok_says: str, back: str):
        placed = receipts.judge(checks)
        if placed:
            place()
        session.last = receipts.write(act, who, subject, checks, placed)
        if not placed:
            session.say("not saved: " + "; ".join(c["says"] for c in checks if not c["ok"]), False)
            return redirect(back)
        if run_plan(who, "planning"):
            session.say(ok_says, True)
            return redirect(back)
        return redirect(url_for("plan.run"))

    now = lambda: dt.datetime.now().isoformat(timespec="seconds")

    # ── 1 · role types ───────────────────────────────────────────────────────────────────────────────────────────────
    @bp.get("/planning/types")
    def planning_types():
        try:
            return show(P_TYPES, "Role types", "planning_types", types=state(current_process())["types"], dims=DIMS, levels=LEVELS)
        except Busy as e:
            return busy("Role types", e)

    @bp.post("/planning/types/add")
    def planning_type_add():
        f = request.form; who = who_fn(); pr = current_process(); s = state(pr)
        name, card = (f.get("type_name") or "").strip(), f.get("cardinality") or "single"
        code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        elsewhere = {r["type_code"] for r in q("select type_code from dims.planning_role_type where process <> ?", pr)}
        if code in elsewhere:                                 # a type of the same name in another process is another type (DEC-20261124-08 point 4)
            code = f"{pr.upper()}_{code}"
        chosen = [d for d in f.getlist("dim") if d in LEVELS] if card == "multiple" else []
        lv = {d: f.get(f"level_{d}") or "" for d in chosen}
        taken = {t["type_code"] for t in s["types"]} | {t["type_name"].lower() for t in s["types"]}
        checks = [who_may(who),
                  {"check": "a name", "ok": bool(code), "says": f"{name} ({code})" if code else "a role type is named"},
                  {"check": "a name not taken", "ok": code not in taken and name.lower() not in taken, "says": "no other role type is called that" if code not in taken and name.lower() not in taken else f"there is already a role type {name}"},
                  {"check": "its cardinality", "ok": card == "single" or (bool(chosen) and all(lv[d] in LEVELS[d] for d in chosen)),
                   "says": "single — one role for the whole business" if card == "single" else ("multiple, by " + " × ".join(f"{d.replace('_', ' ')} at {LEVELS[d][lv[d]][0].lower()}" for d in chosen) if chosen else "a multiple type says what tells its roles apart")}]
        return done("planning.type.add", who, name or "a role type", checks,
                    lambda: TYPES.place([{"type_code": code, "type_name": name, "purpose": (f.get("purpose") or "").strip(), "cardinality": card,
                                          "site_level": lv.get("site", ""), "customer_level": lv.get("customer", ""), "cost_centre_level": lv.get("cost_centre", ""),
                                          "process": pr, "set_by": who, "set_on": now()}], who),
                    f"{name} added — next, its entitlements", url_for("plan.planning_types", process=current_process()))

    # ── 2 · entitlements ─────────────────────────────────────────────────────────────────────────────────────────────
    def follows(s: dict) -> tuple[set, list]:
        prep = {f: t for (f, t), lv in s["cells"].items() if lv == "prepare"}
        tname = {t["type_code"]: t["type_name"] for t in s["types"]}
        uses = [(r["fact"], r["other_fact"]) for r in q("select fact, other_fact from dims.ref_fact_relation where relation = 'uses'")]
        implied = {(o, prep[f]) for f, o in uses if f in prep and prep.get(o) != prep[f]}
        out = []
        for t in s["types"]:
            if not t["prepares"]:
                continue
            tc = t["type_code"]; waits, waited = {}, {}
            for f, o in uses:
                if prep.get(f) == tc and prep.get(o) and prep[o] != tc:
                    waits.setdefault(tname[prep[o]], set()).add(s["names"][o])
                if prep.get(o) == tc and prep.get(f) and prep[f] != tc:
                    waited.setdefault(tname[prep[f]], set()).add(s["names"][o])
            out.append({"type_name": t["type_name"], "prepares": t["prepares"], "roles": [f"{r['role_no']}{' at ' + r['context'] if r['context'] else ''}" for r in t["roles"]],
                        "waits_on": {k: sorted(v) for k, v in waits.items()}, "waited_by": {k: sorted(v) for k, v in waited.items()}})
        return implied, out

    @bp.get("/planning/entitlements")
    def planning_entitlements():
        try:
            s = state(current_process()); every = request.args.get("types") == "all"
            used = {tc for (_, tc) in s["cells"]}
            implied, fol = follows(s)
            tname = {t["type_code"]: t["type_name"] for t in s["types"]}
            prep = {fa: tname.get(tc) for (fa, tc), lv in s["cells"].items() if lv == "prepare"}
            for f in s["facts"]:
                f["kind_says"] = "calculated in the cycle" if f["kind"] == "calculated" else "standing — set on its own, dated"
                f["prepared_by"] = prep.get(f["fact"])
            one = next((t for t in s["types"] if t["type_code"] == request.args.get("type")), None)
            all_facts = request.args.get("facts") == "all"
            facts, types = s["facts"], [t for t in s["types"] if every or t["type_code"] in used]
            if one:                                           # one role type: its column, the facts it has a cell on or reads
                types = [one]
                if not all_facts:
                    facts = [f for f in facts if (f["fact"], one["type_code"]) in s["cells"] or (f["fact"], one["type_code"]) in implied]
            return show(P_ENT, "Entitlements", "planning_entitlements", facts=facts, types=types, every_type=s["types"], one=one, all_facts=all_facts,
                        cells=s["cells"], implied=implied, follows=fol, auth=AUTH, all_types=every)
        except Busy as e:
            return busy("Entitlements", e)

    @bp.post("/planning/entitlements/set")
    def planning_entitlements_set():
        f = request.form; who = who_fn(); s = state(current_process())
        tname = {t["type_code"]: t["type_name"] for t in s["types"]}
        fproc = {r["fact"]: r["process"] for r in q("select fact, process from dims.ref_fact")}
        tproc = {r["type_code"]: r["process"] for r in q("select type_code, process from dims.planning_role_type")}
        posted, across = {}, []
        for name, v in f.items():
            tag, _, rest = name.partition("|")
            fact, _, tc = rest.partition("|")
            if tag == "c" and v and fact in fproc and tc in tproc and fproc[fact] != tproc[tc]:
                across.append(f"{fact.replace('_', ' ')} — {tc.replace('_', ' ').lower()}")
            elif tag == "c" and fact in s["names"] and tc in tname and v in ("", "read", "review", "prepare"):
                posted[(fact, tc)] = v
        changed = {k: v for k, v in posted.items() if v != s["cells"].get(k, "")}
        after = {**s["cells"], **changed}
        for fact in s["names"]:                               # choosing Prepare moves the fact: the former preparer becomes Review
            ps = [tc for (x, tc), lv in after.items() if x == fact and lv == "prepare"]
            new = [tc for tc in ps if changed.get((fact, tc)) == "prepare"]
            if len(ps) > 1 and len(new) == 1:
                for tc in ps:
                    if tc != new[0]:
                        changed[(fact, tc)] = after[(fact, tc)] = "review"
        wrong = []
        for fact, nm in s["names"].items():
            ps = [tname[tc] for (x, tc), lv in after.items() if x == fact and lv == "prepare"]
            if len(ps) != 1:
                wrong.append(f"{nm}: {'nobody prepares it' if not ps else ' and '.join(ps) + ' both prepare it'}")
        says = "; ".join(f"{s['names'][fa]} — {tname[tc]}: {v or 'cleared'}" for (fa, tc), v in sorted(changed.items()))
        checks = [who_may(who),
                  {"check": "a cell changed", "ok": bool(changed), "says": says or "no cell differs from the table standing"},
                  {"check": "within one planning process", "ok": not across,
                   "says": "every cell joins a fact and a role type of the same process" if not across else "no entitlement across processes: " + "; ".join(across)},
                  {"check": "exactly one role type prepares each fact", "ok": not wrong, "says": "every fact has one" if not wrong else "; ".join(wrong)}]
        at = now()
        return done("planning.entitlements.set", who, f"{len(changed)} cells", checks,
                    lambda: ENTITLEMENTS.place([{"fact": fa, "type_code": tc, "level": v, "set_by": who, "set_on": at} for (fa, tc), v in sorted(changed.items())], who),
                    f"{len(changed)} cell{'s' if len(changed) != 1 else ''} saved — {says}", url_for("plan.planning_entitlements", types=f.get("types") or None, type=f.get("type") or None, facts=f.get("facts") or None, process=current_process()))

    # ── 3 · roles ────────────────────────────────────────────────────────────────────────────────────────────────────
    def next_no() -> str:
        used = [int(r["role_no"]) for r in q("select role_no from dims.planning_role") if str(r["role_no"]).isdigit()]
        return str(max(used) + 1 if used else 1000)

    @bp.get("/planning/roles")
    def planning_roles():
        try:
            s = state(current_process())
            chosen = next((t for t in s["types"] if t["type_code"] == request.args.get("type")), None) or next((t for t in s["types"] if t["can_add"]), None)
            return show(P_ROLES, "Roles", "planning_roles", types=s["types"], n_roles=len(s["roles"]), chosen=chosen, next_no=next_no())
        except Busy as e:
            return busy("Roles", e)

    @bp.post("/planning/roles/add")
    def planning_role_add():
        f = request.form; who = who_fn(); s = state(current_process())
        t = next((x for x in s["types"] if x["type_code"] == f.get("type_code")), None)
        no = (f.get("role_no") or "").strip()
        place_ = {d["dim"]: (f.get(d["dim"]) or "") for d in (t["dims"] if t else [])}
        valid = all(place_[d["dim"]] in {m["code"] for m in d["members"]} for d in (t["dims"] if t else []))
        ctx = " × ".join(next((m["name"] for m in d["members"] if m["code"] == place_[d["dim"]]), place_[d["dim"]]) for d in (t["dims"] if t else []))
        clash = [r["role_no"] for r in (t["roles"] if t else []) if all((r.get(d) or "") == place_.get(d, "") for d, _ in DIMS)]
        ever = {str(r["role_no"]) for r in q("select role_no from dims.planning_role")}
        name = (f.get("role_name") or "").strip() or (f"{t['type_name']}, {ctx}" if t and ctx else (t["type_name"] if t else ""))
        checks = [who_may(who),
                  {"check": "a role type", "ok": bool(t), "says": t["type_name"] if t else "a role is of a role type"},
                  {"check": "its number", "ok": no.isdigit() and no not in ever, "says": f"{no} — not used before" if no.isdigit() and no not in ever else (f"{no} has been used — a number is never reused" if no in ever else "a role has a number")},
                  {"check": "its place", "ok": bool(t) and valid and not clash,
                   "says": (f"role {clash[0]} already covers {ctx or 'the whole business'}" if clash else (ctx or "the whole business") if valid else "a member at the type's level, for each of its dimensions")}]
        return done("planning.role.add", who, f"{no} {name}", checks,
                    lambda: ROLES.place([{"role_no": no, "type_code": t["type_code"], "role_name": name, "purpose": (f.get("purpose") or "").strip(),
                                          "site": place_.get("site", ""), "customer": place_.get("customer", ""), "cost_centre": place_.get("cost_centre", ""),
                                          "status": "live", "set_by": who, "set_on": now()}], who),
                    f"role {no} defined — {name}; nobody holds it until it is assigned", url_for("plan.planning_roles", type=f.get("type_code") or None, process=current_process()))

    # ── 4 · assignments ──────────────────────────────────────────────────────────────────────────────────────────────
    @bp.get("/planning/assignments")
    def planning_assignments():
        try:
            s = state(current_process())
            by_no = {r["role_no"]: r for r in s["roles"]}
            tprep = {t["type_code"]: t["prepares"] for t in s["types"]}
            def prepares(r: dict) -> list[str]:
                return [f"{x}{' at ' + r['context'] if r['context'] else ''}" for x in tprep.get(r["type_code"], [])]
            rows = [{**a, "role_name": by_no[a["role_no"]]["role_name"], "prepares": prepares(by_no[a["role_no"]]) if a["live"] else []} for a in s["asg"] if a["role_no"] in by_no]
            people = [r["principal"] for r in q("select distinct principal from dims.ctl_role_assignment order by 1")]
            return show(P_ASG, "Assignments", "planning_assignments", rows=rows, roles=s["roles"], people=people, today=dt.date.today().isoformat(),
                        empty=[{**r, "prepares": prepares(r)} for r in s["roles"] if not r["held"]], cover=[r for r in s["roles"] if len(r["held"]) > 1])
        except Busy as e:
            return busy("Assignments", e)

    def _assign(end: bool):
        f = request.form; who = who_fn(); s = state(current_process())
        person, no = (f.get("person") or "").strip(), (f.get("role_no") or "").strip()
        role = next((r for r in s["roles"] if r["role_no"] == no), None)
        cur = next((a for a in s["asg"] if a["person"] == person and a["role_no"] == no), None)
        known = person in {r["principal"] for r in q("select distinct principal from dims.ctl_role_assignment")}
        today = dt.date.today()
        vf = (cur["valid_from"].isoformat() if cur and cur["valid_from"] else "") if end else (f.get("valid_from") or today.isoformat())
        vt = (today - dt.timedelta(days=1)).isoformat() if end else (f.get("valid_to") or "")
        checks = [who_may(who),
                  {"check": "a person", "ok": known, "says": person if known else "a person the plan knows"},
                  {"check": "a role", "ok": bool(role), "says": f"{no} {role['role_name']}" if role else "a role that is defined"},
                  {"check": "holding it" if end else "the dates", "ok": bool(cur and cur["live"]) if end else (not vt or vt >= vf),
                   "says": (f"held since {vf}; ended as of {vt}" if cur and cur["live"] else "not holding it") if end else (f"from {vf}" + (f" to {vt}" if vt else ", open") if not vt or vt >= vf else "it ends before it starts")}]
        return done("planning.assignment.end" if end else "planning.assignment.give", who, f"{person} · {no}", checks,
                    lambda: ASSIGNMENTS.place([{"person": person, "role_no": no, "valid_from": vf, "valid_to": vt, "set_by": who, "set_on": now()}], who),
                    f"{person} {'no longer holds' if end else 'is assigned'} {role['role_name'] if role else no}", url_for("plan.planning_assignments", process=current_process()))

    @bp.post("/planning/assignments/give")
    def planning_assignment_give():
        return _assign(False)

    @bp.post("/planning/assignments/end")
    def planning_assignment_end():
        return _assign(True)
