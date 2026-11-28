"""Planning roles under Admin (DEC-20261124-07): the role architecture, in four steps.

1. **Role types** — the kinds of job: a cardinality (single, or multiple with the dimensions and levels that tell its
   roles apart).
2. **Entitlements** — which role type owns each planning fact: exactly one type prepares a fact, and every other is
   taken to read it.
3. **Roles** — each a role type at one member of its level, with its own number and name.
4. **Assignments** — who fills each role. People change; the role does not.

Each step is a register (plan/reg_role_type, reg_planning_entitlement, reg_planning_role, reg_planning_assignment) read
as a model; what follows — a person's authority over a fact, in a place — is dims.planning_authority, and a right a fact
names is held through it. Registered on the plan's blueprint by `register(...)`, called from `face/__main__.py`.

Each step is read within one planning process (DEC-20261124-08), a selection of the context carried in the address
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
TYPES = LogLanding("plan", "reg_role_type", ["type_code", "type_name", "purpose", "cardinality", "site_level", "customer_level", "cost_centre_level", "process", "domain", "set_by", "set_on"])
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
STEPS = (("types", "Role types", "the kinds of job", "plan.planning_types"), ("entitlements", "Entitlements", "which type owns each fact", "plan.planning_entitlements"),
         ("roles", "Roles", "each type in a business context", "plan.planning_roles"), ("assignments", "Assignments", "who fills each role", "plan.planning_assignments"))

FLOW = """{% macro flow(on) %}<div class="flow">{% for k, name, says, ep in steps %}{% if not loop.first %}<span class="arrow">→</span>{% endif %}<a href="{{ url_for(ep, process=process) }}" class="{{ 'on' if k == on }}"><span class="step">{{ loop.index }}</span><b>{{ name }}</b><span class="small muted">{{ says }}</span></a>{% endfor %}</div>
<style>.procs{display:flex;gap:.4rem;align-items:center;margin:0 0 .7rem}.procs a{border:1px solid var(--line,#ccc);border-radius:999px;padding:.2rem .8rem;text-decoration:none;color:inherit}.procs a.on{border-color:var(--ink);background:var(--ink);color:var(--paper,#fff)}.procs .muted{margin-right:.3rem}
.flow{display:flex;align-items:stretch;gap:.6rem;margin:0 0 1.2rem}.flow a{flex:1;display:flex;flex-direction:column;gap:.15rem;border:1px solid var(--line,#ccc);border-radius:.6rem;padding:.55rem .8rem;text-decoration:none;color:inherit}.flow a.on{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink);background:var(--panel)}.flow .arrow{align-self:center;color:var(--muted)}
.step{display:inline-block;border:1px solid var(--ink);border-radius:999px;width:1.5rem;height:1.5rem;line-height:1.4rem;text-align:center;font-size:.8rem}
.field{display:flex;flex-direction:column;gap:.2rem;margin:.5rem 0}.field input,.field textarea,.field select{font:inherit;padding:.3rem .45rem}.fields{display:grid;grid-template-columns:9rem 1fr;gap:1rem}
.tick{display:grid;grid-template-columns:1.4rem 9rem 1fr;gap:.2rem .4rem;align-items:baseline;margin:.3rem 0}.two{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:1.4rem;align-items:start}
.actions{display:flex;gap:.8rem;align-items:center;margin-top:.8rem}tr.type td{background:var(--soft);font-weight:600}tr.type td .small{font-weight:400}td.in{padding-left:1.6rem}td.no{font-variant-numeric:tabular-nums;white-space:nowrap}
.indent{margin:.4rem 0 0 1.8rem;padding-left:.9rem;border-left:2px solid var(--ink)}
.make{display:grid;grid-template-columns:minmax(20rem,28rem) minmax(0,1fr);gap:1.8rem;align-items:start}.make>div>.card:first-child{margin-top:0}.make .scroll{overflow-x:auto}.make h2{margin-top:0}@media (max-width:900px){.make{grid-template-columns:1fr}}
.make>div>.card.lead{border:1px solid var(--ink);box-shadow:0 1px 0 var(--ink);padding:1.1rem 1.2rem}.card.lead h2{margin:0 0 .8rem;font-size:1.35rem}
.stands.quiet{background:var(--soft);border-radius:.6rem;padding:.8rem 1rem;font-size:.9rem}.stands.quiet h2{font-size:1rem;margin:0 0 .6rem}.stands.quiet .ctx{background:transparent;padding:0}.stands.quiet .card{background:var(--panel)}.stands.quiet h3{font-size:.95rem}
.ctx{background:var(--soft);border-radius:.5rem;padding:.6rem .7rem;margin:0 0 1rem}.ctx .cap{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.ctxrow{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:.6rem;margin-top:.4rem}
.ctx label{display:flex;flex-direction:column;gap:.15rem;background:var(--panel);border:1px solid var(--line,#ccc);border-radius:.4rem;padding:.4rem .6rem;font-size:.8rem;color:var(--muted)}.ctx select{font:inherit;font-size:.95rem;border:0;background:transparent;color:var(--ink);padding:0;width:100%}.pn{display:none}.allproc .pn{display:inline}
table.own th{vertical-align:bottom;position:sticky;top:0;z-index:2;background:var(--soft);min-width:5.5rem;white-space:normal}table.own td:first-child{min-width:13rem;position:sticky;left:0;z-index:1;background:var(--panel)}table.own th:first-child{left:0;z-index:3}.ownwrap{overflow:auto;max-height:75vh}table.own td.prepare{box-shadow:inset 0 0 0 1px var(--ink)}table.own select.cell{font:inherit;font-size:.85rem;background:transparent;color:inherit;border:0}table.own td.prepare select.cell{font-weight:700}</style>
<style>.inplace .edit{font:inherit;background-color:transparent;color:inherit;border:1px solid transparent;border-radius:.3rem;padding:.15rem .3rem;margin-left:-.3rem;max-width:100%;cursor:text}.inplace select.edit{appearance:none;-webkit-appearance:none;cursor:pointer;padding-right:1.3rem;background-repeat:no-repeat;background-position:right .4rem center;background-size:.6rem}.inplace input.edit{width:100%;min-width:12rem}
.inplace .edit:focus{outline:0}.inplace .edit:hover,.inplace input.edit:focus,.inplace select.edit:focus-visible{border-color:var(--ink);background-color:var(--panel)}.inplace select.edit:hover,.inplace select.edit:focus-visible{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%23888' stroke-width='1.5'/%3E%3C/svg%3E")}.inplace .edit.changed{border-color:var(--ink);background-color:var(--panel)}</style><script>document.addEventListener('DOMContentLoaded',function(){[].forEach.call(document.querySelectorAll('form.inplace'),function(f){var es=[].slice.call(f.querySelectorAll('.edit'));
function was(e){if(e.tagName!=='SELECT')return e.defaultValue;var d=[].filter.call(e.options,function(o){return o.defaultSelected;})[0]||e.options[0];return d?d.value:'';}
function say(){var n=0;es.forEach(function(e){var c=e.value!==was(e);e.classList.toggle('changed',c);if(c)n++;});var b=f.querySelector('.savebar'),c=b&&b.querySelector('.savecount');if(c){c.textContent=n?n+' change'+(n==1?'':'s')+' not saved':'nothing changed';b.classList.toggle('dirty',n>0);}}
f.addEventListener('input',say);f.addEventListener('change',say);f.addEventListener('click',function(e){if(e.target.closest('[data-discard="reset"]')){es.forEach(function(x){x.value=was(x);});setTimeout(say,0);}});setTimeout(say,0);});});</script>{% endmacro %}
{% macro ctx(persons=none) %}<div class="ctx"><span class="cap">Filter</span><div class="ctxrow">
<label>Responsibility<select data-f="level"><option value="">All</option><option value="whole">Whole business</option>{% for d, dn in dims %}{% for lv, (ln, _) in levels[d].items() %}<option value="{{ d }}:{{ lv }}">{{ ln }}{{ ' (site)' if d == 'site' and lv == 'site' }}</option>{% endfor %}{% endfor %}</select></label>
<label>Domain<select data-f="domain"><option value="">All</option>{% for p in processes %}{% if p.process == process %}{% for d in domains if d.process == p.process %}<option value="{{ d.process }}:{{ d.domain }}">{{ d.domain_name }}</option>{% endfor %}{% endif %}{% endfor %}<option value="none">Not categorised</option></select></label>
{% if persons %}<label>Person<select data-f="person"><option value="">All</option>{% for p in persons %}<option value="{{ p }}">{{ p.split('@')[0] }}</option>{% endfor %}</select></label>{% endif %}</div></div>
<script>document.addEventListener('DOMContentLoaded',function(){var box=document.querySelector('.ctx');if(!box)return;var side=box.parentNode;function v(k){var e=box.querySelector('[data-f="'+k+'"]');return e?e.value:'';}
function go(){var p=v('proc'),l=v('level'),w=v('person'),d=v('domain');[].forEach.call(side.querySelectorAll('[data-proc]'),function(e){e.hidden=!((!p||e.dataset.proc===p)&&(!l||e.dataset.level.split(' ').indexOf(l)>=0)&&(!w||!e.dataset.person||e.dataset.person===w)&&(!d||e.dataset.domain===d));});
[].forEach.call(side.querySelectorAll('[data-n]'),function(c){c.textContent=[].filter.call(side.querySelectorAll('[data-row="'+c.dataset.n+'"]'),function(e){return !e.hidden;}).length;});}
box.addEventListener('change',go);go();});</script>{% endmacro %}
{% macro at(x, row='') %}data-proc="{{ x.process }}" data-level="{{ x.levels }}" data-domain="{{ x.process ~ ':' ~ x.domain if x.domain else 'none' }}"{% if row %} data-row="{{ row }}"{% endif %}{% if x.person %} data-person="{{ x.person }}"{% endif %}{% endmacro %}
{% macro pn(x) %}<span class="pn small muted"> · {{ x.process_name }}</span>{% endmacro %}
{% macro receipt(last) %}{% if last %}<h2>Receipt</h2><table><thead><tr><th>Check</th><th></th><th>Says</th></tr></thead><tbody>{% for c in last.checks %}<tr><td>{{ c.check }}</td><td class="{{ 'ok' if c.ok else 'no' }}">{{ '✓' if c.ok else '✕' }}</td><td>{{ c.says }}</td></tr>{% endfor %}</tbody></table>{% endif %}{% endmacro %}"""

P_TYPES = FLOW + figures.SAVE_BAR + """{{ flow('types') }}<div class="make"><div>
{% if may %}<form class="card lead" method="post" action="{{ url_for('plan.planning_type_add') }}"><input type="hidden" name="process" value="{{ process }}"><h2>Create a role type</h2>
<label class="field small">Role type name <input name="type_name" required placeholder="Category buyer" autofocus></label>
<label class="field small">Domain <select name="domain"><option value="">— not categorised</option>{% for d in domains if d.process == process %}<option value="{{ d.domain }}">{{ d.domain_name }}</option>{% endfor %}</select></label>
<label class="field small">Description <span class="muted">(optional)</span> <textarea name="purpose" rows="2"></textarea></label>
<h3 style="margin-top:1rem">Cardinality</h3>
<div class="tick" title="One role, for the whole business"><input type="radio" name="cardinality" value="single" checked id="c-single"><label for="c-single">Single</label></div>
<div class="tick" title="Several roles, told apart by the dimensions ticked below"><input type="radio" name="cardinality" value="multiple" id="c-multiple"><label for="c-multiple">Multiple</label></div>
<div class="indent" id="dims" hidden><h3 style="margin:.2rem 0" title="The dimensions that tell its roles apart, and the level each is held at">One role for each</h3>
{% for d, dn in dims %}<div class="tick"><input type="checkbox" name="dim" value="{{ d }}" id="d-{{ d }}"><label for="d-{{ d }}">{{ dn }}</label><label class="small">level <select name="level_{{ d }}">{% for lv, (ln, _) in levels[d].items() %}<option value="{{ lv }}">{{ ln }}</option>{% endfor %}</select></label></div>{% endfor %}</div>
<div class="actions"><button class="primary" onclick="this.textContent='Creating…'">Create role type</button></div></form>
<script>(function(){var f=document.querySelector('form[action$="/planning/types/add"]');if(!f)return;function show(){document.getElementById('dims').hidden=!f.querySelector('#c-multiple').checked;}f.addEventListener('change',show);show();})();</script>
{% else %}<p class="hint">Role types are created by {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}{{ receipt(last) }}
</div><div class="stands quiet"><h2>Role types<span class="count" data-n="type">{{ types|length }}</span></h2>{{ ctx() }}
<form class="inplace" method="post" action="{{ url_for('plan.planning_types_set') }}"><input type="hidden" name="process" value="{{ process }}">
<div class="scroll"><table><thead><tr><th>Domain</th><th>Role type</th><th>Cardinality</th><th>Dimension</th><th>Level</th><th title="Set at step 2">Owns</th><th class="n" title="Created at step 3">Roles</th><th>Not covered</th></tr></thead><tbody>
{% for t in types %}<tr {{ at(t, 'type') }}><td class="small{{ ' muted' if not t.domain }}">{% if may %}<select class="edit" name="d|{{ t.type_code }}"><option value="">Not categorised</option>{% for d in domains if d.process == process %}<option value="{{ d.domain }}" {{ 'selected' if d.domain == t.domain }}>{{ d.domain_name }}</option>{% endfor %}</select>{% else %}{{ t.domain_name }}{% endif %}</td>
<td>{% if may %}<input class="edit" name="n|{{ t.type_code }}" value="{{ t.type_name }}" style="font-weight:700">{% else %}<b>{{ t.type_name }}</b>{% endif %}{% if t.purpose %}<div class="small muted">{{ t.purpose }}</div>{% endif %}</td><td class="small">{{ 'Multiple' if t.cardinality == 'multiple' else 'Single' }}</td>
<td class="small">{{ t.dims|map(attribute='dim_name')|join(' × ') }}</td><td class="small">{{ t.dims|map(attribute='level_name')|join(' × ') }}</td>
<td class="small">{{ t.prepares|join('; ') }}</td><td class="n">{{ t.n_roles }}</td><td class="small">{{ t.gaps|join('; ') }}</td></tr>{% endfor %}
</tbody></table></div>
{% if may %}{{ save_bar(discard='reset', note='saved by ' ~ who) }}{% endif %}</form></div></div>"""

P_ENT = FLOW + figures.SAVE_BAR + """{{ flow('entitlements') }}<h2 title="One role type owns each planning fact; every other role type reads it">Entitlements<span class="count">{{ facts|length }} planning facts</span></h2>
<form class="ctx" method="get" action="{{ url_for('plan.planning_entitlements') }}"><input type="hidden" name="process" value="{{ process }}"><span class="cap">Filter</span><div class="ctxrow">
<label>Role type<select name="type" onchange="this.form.submit()"><option value="">All role types</option>{% for t in every_type %}<option value="{{ t.type_code }}" {{ 'selected' if one and one.type_code == t.type_code }}>{{ t.type_name }}</option>{% endfor %}</select></label></div></form>
{% if one %}<p class="small"><span class="muted">facts shown:</span> {% if all_facts %}<a href="{{ url_for('plan.planning_entitlements', process=process, type=one.type_code) }}">those it owns</a> · <b>every fact</b>{% else %}<b>those it owns</b> · <a href="{{ url_for('plan.planning_entitlements', process=process, type=one.type_code, facts='all') }}">every fact</a>{% endif %}</p>{% endif %}
<form method="post" action="{{ url_for('plan.planning_entitlements_set') }}"><input type="hidden" name="process" value="{{ process }}">{% if one %}<input type="hidden" name="type" value="{{ one.type_code }}">{% if all_facts %}<input type="hidden" name="facts" value="all">{% endif %}{% endif %}
<div class="ownwrap"><table class="own"><thead><tr><th>Planning fact</th>{% if one %}<th>Owned by</th>{% endif %}{% for t in types %}<th><div class="cap">{{ t.domain_name }}</div>{{ t.type_name }}<div class="small muted">{{ 'Multiple' if t.cardinality == 'multiple' else 'Single' }} · {{ t.n_roles }} role{{ '' if t.n_roles == 1 else 's' }}{% if t.dims %}, by {{ t.dims|map(attribute='level_name')|join(' × ')|lower }}{% endif %}</div></th>{% endfor %}</tr></thead><tbody>
{% for f in facts %}<tr><td><b>{{ f.fact_name }}</b><div class="small muted">{{ f.kind_says }}</div></td>{% if one %}<td class="small{{ ' muted' if not f.prepared_by }}">{{ f.prepared_by or 'nobody' }}</td>{% endif %}
{% for t in types %}{% set o = cells.get((f.fact, t.type_code)) == 'prepare' %}<td class="{{ 'prepare' if o }}">{% if may %}<label class="owner"><input type="radio" name="o|{{ f.fact }}" value="{{ t.type_code }}" {{ 'checked' if o }}><span>Owner</span></label>{% else %}{{ 'Owner' if o else '—' }}{% endif %}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>
{% if may %}{{ save_bar(discard='reset', note='saved by ' ~ who) }}{% endif %}</form>
<style>table.own th .cap{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:400}table.own td{text-align:center}table.own td:first-child,table.own td.small{text-align:left}label.owner{display:flex;gap:.35rem;align-items:center;justify-content:center;cursor:pointer;min-height:1.6rem}label.owner input{opacity:0;margin:0}table.own td:hover label.owner input,label.owner input:focus-visible{opacity:1}label.owner span{visibility:hidden;font-weight:700;font-size:.85rem}label.owner input:checked+span{visibility:visible}</style>
<h2>What follows</h2>
<table><thead><tr><th>Role type</th><th>Owns</th><th>Through its roles</th><th>Waits on</th><th>Is waited on by</th></tr></thead><tbody>
{% for r in follows %}<tr><td><b>{{ r.type_name }}</b></td><td class="small">{{ r.prepares|join('; ') }}</td><td class="small{{ ' muted' if not r.roles }}">{{ r.roles|join(' · ') or 'no role defined yet' }}</td>
<td class="small">{% for o, fs in r.waits_on.items() %}{{ o }} <span class="muted">({{ fs|join(', ') }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nobody — set on its own</span>{% endfor %}</td>
<td class="small">{% for o, fs in r.waited_by.items() %}{{ o }} <span class="muted">({{ fs|join(', ') }})</span>{{ '; ' if not loop.last }}{% else %}<span class="muted">nobody</span>{% endfor %}</td></tr>{% endfor %}
</tbody></table>
{{ receipt(last) }}
<script>(function(){var f=document.querySelector('form[action$="/planning/entitlements/set"]');if(!f)return;var rs=[].slice.call(f.querySelectorAll('label.owner input'));
function say(){var n=0;rs.forEach(function(r){if(r.checked&&!r.defaultChecked)n++;r.closest('td').className=r.checked?'prepare':'';});var b=f.querySelector('.savebar'),c=b&&b.querySelector('.savecount');if(c){c.textContent=n?n+' fact'+(n==1?'':'s')+' moved and not saved':'nothing changed';b.classList.toggle('dirty',n>0);}}
f.addEventListener('change',say);f.addEventListener('click',function(e){if(e.target.closest('[data-discard="reset"]')){rs.forEach(function(r){r.checked=r.defaultChecked;});say();}});setTimeout(say,0);})();</script>"""

P_ROLES = FLOW + figures.SAVE_BAR + """{{ flow('roles') }}<div class="make"><div id="new">
{% if may %}<div class="card lead"><h2>Create a role</h2>
<form method="get" action="{{ url_for('plan.planning_roles') }}#new"><input type="hidden" name="process" value="{{ process }}"><label class="field small">Role type <select name="type" onchange="this.form.submit()">{% for t in own %}<option value="{{ t.type_code }}" {{ 'selected' if chosen and t.type_code == chosen.type_code }} {{ 'disabled' if not t.can_add }}>{{ t.type_name }}{{ '' if t.can_add else ' — its one role exists' }}</option>{% endfor %}</select></label></form>
{% if chosen and chosen.can_add %}<form method="post" action="{{ url_for('plan.planning_role_add') }}"><input type="hidden" name="process" value="{{ process }}"><input type="hidden" name="type_code" value="{{ chosen.type_code }}">
{% if chosen.dims %}{% for d in chosen.dims %}<label class="field small" title="Business context: the {{ d.level_name|lower }} this role is held at">Business context — {{ d.dim_name|lower }} <select name="{{ d.dim }}">{% for m in d.members %}<option value="{{ m.code }}">{{ m.name }}</option>{% endfor %}</select></label>{% endfor %}
{% else %}<label class="field small">Business context <input value="Whole business" disabled></label>{% endif %}
{% for d, dn in dims if d not in chosen.dims|map(attribute='dim') %}<label class="field small" title="Optional: {{ chosen.type_name|lower }} is not told apart by {{ dn|lower }}">Business context — {{ dn|lower }} <span class="muted">(optional)</span> <select name="{{ d }}"><option value=""></option>{% for g in extra[d] if g.members %}<optgroup label="{{ g.level_name }}">{% for m in g.members %}<option value="{{ m.code }}">{{ m.name }}</option>{% endfor %}</optgroup>{% endfor %}</select></label>{% endfor %}
<div class="fields" style="margin-top:.6rem"><label class="field small" title="The next free number; a number is never reused">Role number <input name="role_no" value="{{ next_no }}" required></label>
<label class="field small" title="Left empty, the role type{{ ' and its business context' if chosen.dims }}">Role name <input name="role_name" placeholder="{{ chosen.type_name }}{{ ', business context' if chosen.dims }}"></label></div>
<label class="field small">Description <span class="muted">(optional)</span> <textarea name="purpose" rows="2"></textarea></label>
<div class="actions"><button class="primary" onclick="this.textContent='Creating…'">Create role</button></div></form>{% endif %}</div>
{% else %}<p class="hint">Roles are created by {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}{{ receipt(last) }}
</div><div class="stands quiet"><h2>Roles<span class="count" data-n="role">{{ n_roles }}</span></h2>{{ ctx() }}
<form class="inplace" method="post" action="{{ url_for('plan.planning_roles_set') }}"><input type="hidden" name="process" value="{{ process }}">
<div class="scroll"><table><thead><tr><th>No.</th><th>Domain</th><th>Role type</th>{% for d, dn in dims %}<th>{{ dn }}</th>{% endfor %}<th>Role name</th><th title="Assigned at step 4">Held by</th></tr></thead><tbody>
{% for t in types %}{% for r in t.roles %}<tr {{ at(t, 'role') }}><td class="no">{{ r.role_no }}</td><td class="small{{ ' muted' if not t.domain }}">{{ t.domain_name }}</td><td><b>{{ t.type_name }}</b>{{ pn(t) }}</td>{% for d, dn in dims %}<td>{% set td = t.dims|selectattr('dim', 'equalto', d)|first %}{% if may and td %}<select class="edit" name="m|{{ r.role_no }}|{{ d }}">{% for m in td.members %}<option value="{{ m.code }}" {{ 'selected' if m.code == r[d] }}>{{ m.name }}</option>{% endfor %}</select>{% elif may %}<select class="edit" name="m|{{ r.role_no }}|{{ d }}" title="Optional: {{ t.type_name|lower }} is not told apart by {{ dn|lower }}"><option value=""></option>{% for g in extra[d] if g.members %}<optgroup label="{{ g.level_name }}">{% for m in g.members %}<option value="{{ m.code }}" {{ 'selected' if m.code == r[d] }}>{{ m.name }}</option>{% endfor %}</optgroup>{% endfor %}</select>{% else %}{{ r.place.get(d, '') }}{% endif %}</td>{% endfor %}<td class="small{{ '' if may else ' muted' }}">{% if may %}<input class="edit" name="t|{{ r.role_no }}" value="{{ r.role_name }}">{% else %}{{ r.role_name }}{% endif %}</td><td class="small{{ ' muted' if not r.held }}">{{ r.held|join(', ') or 'nobody yet' }}</td></tr>{% endfor %}
{% if not t.roles %}<tr {{ at(t) }}><td class="no"></td><td class="small{{ ' muted' if not t.domain }}">{{ t.domain_name }}</td><td><b>{{ t.type_name }}</b>{{ pn(t) }}</td><td class="small muted" colspan="{{ dims|length + 2 }}"><i>no role yet</i></td></tr>
{% elif t.gaps %}<tr {{ at(t) }}><td class="no"></td><td></td><td class="small muted">{{ t.type_name }}</td>{% for d, dn in dims %}<td class="small muted">{% if t.dims and t.dims[0].dim == d %}<i>not covered: {{ t.gaps|join('; ') }}</i>{% endif %}</td>{% endfor %}<td colspan="2"></td></tr>{% endif %}{% endfor %}
</tbody></table></div>
{% if may %}{{ save_bar(discard='reset', note='saved by ' ~ who) }}{% endif %}</form>


</div></div>"""

P_ASG = FLOW + """{{ flow('assignments') }}<div class="make"><div>
{% if may %}<form class="card lead" method="post" action="{{ url_for('plan.planning_assignment_give') }}"><input type="hidden" name="process" value="{{ process }}"><h2>Assign a role</h2>
<label class="field small">Person <select name="person">{% for p in people %}<option>{{ p }}</option>{% endfor %}</select></label>
<label class="field small">Role <select name="role_no">{% for r in roles %}<option value="{{ r.role_no }}">{{ r.role_no }} · {{ r.role_name }}</option>{% endfor %}</select></label>
<div class="fields" style="grid-template-columns:1fr 1fr"><label class="field small">From <input type="date" name="valid_from" value="{{ today }}"></label><label class="field small" title="Left empty, the assignment is open-ended">To <input type="date" name="valid_to"></label></div>
<div class="actions"><button class="primary" onclick="this.textContent='Assigning…'">Assign role</button></div></form>{% else %}<p class="hint">Roles are assigned by {{ holders|join(', ') or 'nobody yet' }}.</p>{% endif %}{{ receipt(last) }}
</div><div class="stands quiet"><h2>Assignments<span class="count" data-n="asg">{{ rows|length }}</span></h2>{{ ctx(rows|map(attribute='person')|unique|sort) }}
<div class="scroll"><table><thead><tr><th>Person</th><th>Domain</th><th>Role</th><th>From</th><th>To</th><th>Owns</th><th></th></tr></thead><tbody>
{% for a in rows %}<tr class="{{ 'muted' if not a.live }}" {{ at(a, 'asg') }}><td>{{ a.person }}</td><td class="small{{ ' muted' if not a.domain }}">{{ a.domain_name }}</td><td><span class="small muted">{{ a.role_no }}</span> {{ a.role_name }}{{ pn(a) }}</td><td class="small">{{ a.valid_from or '' }}</td><td class="small{{ ' muted' if not a.valid_to }}">{{ a.valid_to or 'open' }}</td><td class="small">{{ a.prepares|join('; ') }}</td>
<td class="acts">{% if may and a.live %}<form class="inline" method="post" action="{{ url_for('plan.planning_assignment_end') }}"><input type="hidden" name="process" value="{{ a.process }}"><input type="hidden" name="person" value="{{ a.person }}"><input type="hidden" name="role_no" value="{{ a.role_no }}"><button class="act">End</button></form>{% endif %}</td></tr>{% endfor %}
</tbody></table></div>
<div class="two" style="margin-top:1.2rem"><div class="card"><h3 style="margin-top:0">Roles nobody holds</h3>{% if empty %}<table><thead><tr><th>Role</th><th>Left without an owner</th></tr></thead><tbody>
{% for r in empty %}<tr {{ at(r) }}><td><span class="small muted">{{ r.role_no }}</span> {{ r.role_name }}</td><td class="small{{ ' muted' if not r.prepares }}">{{ r.prepares|join('; ') or '—' }}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">Every role is held.</p>{% endif %}</div>
<div class="card"><h3 style="margin-top:0">Roles with cover</h3>{% if cover %}<table><thead><tr><th>Role</th><th>Held by</th></tr></thead><tbody>
{% for r in cover %}<tr {{ at(r) }}><td><span class="small muted">{{ r.role_no }}</span> {{ r.role_name }}</td><td class="small">{{ r.held|join(', ') }}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="hint">No role is held by more than one person.</p>{% endif %}</div></div></div></div>"""


def members(dim: str, level: str) -> list[dict]:
    return q(LEVELS[dim][level][1]) if dim in LEVELS and level in LEVELS[dim] else []


def every_member(dim: str) -> list[dict]:
    """A dimension's members at each of its levels, for a role that adds a dimension its type does not name (ambiguity
    #145): [{level, level_name, members}], a member listed under the first level that has it."""
    out, seen = [], set()
    for lv, (ln, _) in LEVELS[dim].items():
        ms = [m for m in members(dim, lv) if m["code"] not in seen]
        seen |= {m["code"] for m in ms}
        out.append({"level": lv, "level_name": ln, "members": ms})
    return out


def processes() -> list[dict]:
    return q("select process, process_name from dims.ref_process order by ord")


def domains() -> list[dict]:
    return q("select process, domain, domain_name, ord from dims.ref_domain order by process, ord")


def current_process() -> str:
    """The process the screens read: from the address or the form, else integrated business planning."""
    p = request.values.get("process") or DEFAULT_PROCESS
    return p if p in {r["process"] for r in processes()} else DEFAULT_PROCESS


def state(process: str) -> dict:
    """The four steps as they stand within one process, and what is read across them. A role and an assignment are of
    the process of their type."""
    dom = {d["domain"]: d for d in domains() if d["process"] == process}
    types = q("select * from dims.planning_role_type where process = ?", process)
    for t in types:
        t["domain_name"] = dom[t["domain"]]["domain_name"] if t.get("domain") in dom else "Not categorised"
    types.sort(key=lambda t: (dom[t["domain"]]["ord"] if t.get("domain") in dom else 99, t["type_name"]))
    roles = q("select r.* from dims.planning_role r join dims.planning_role_type t using (type_code) where r.live and t.process = ? order by r.role_no", process)
    asg = q("""select a.* from dims.planning_assignment a join dims.planning_role r using (role_no) join dims.planning_role_type t on t.type_code = r.type_code
             where t.process = ? order by a.live desc, a.role_no, a.person""", process)
    facts = q("select * from dims.ref_fact where process = ? order by ord", process)
    cells = {(r["fact"], r["type_code"]): r["level"] for r in q("select fact, type_code, level from dims.planning_entitlement where process = ? and type_process = ?", process, process)}
    names = {f["fact"]: f["fact_name"] for f in facts}
    extra = {d: every_member(d) for d, _ in DIMS}
    label: dict = {(d, m["code"]): m["name"] for d, g in extra.items() for lv in g for m in lv["members"]}
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
    pname = {p["process"]: p["process_name"] for p in processes()}
    for t in types:
        t["process_name"] = pname.get(t["process"], t["process"])
        t["scope"] = " ".join(x["dim"] for x in t["dims"]) or "whole"
        t["levels"] = " ".join(f"{x['dim']}:{x['level']}" for x in t["dims"]) or "whole"
        t["held_at"] = " × ".join(x["level_name"] for x in t["dims"])
    of = {t["type_code"]: t for t in types}
    for r in roles:
        r.update({k: of[r["type_code"]][k] for k in ("process", "process_name", "scope", "levels", "held_at", "type_name", "domain", "domain_name")})
        r["place"] = {d: label.get((d, r[d]), r[d]) for d, _ in DIMS if r.get(d)}
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
    return {"types": types, "roles": roles, "asg": asg, "facts": facts, "cells": cells, "names": names, "extra": extra, "label": label}


def everything() -> tuple[dict, dict]:
    """The planning process of the context, and what stands in it — one process at a time (ambiguity #141); the filters
    above what stands narrow that."""
    s = state(current_process())
    return s, {k: s[k] for k in ("types", "roles", "asg")}


def register(bp, page, who_fn, busy, session, roles, run_plan, scoped: dict) -> None:
    from . import reads
    scoped["planning"] = {"what": "planning roles", "says": "run completed — the planning roles stand as set"}

    def show(tpl: str, title: str, active: str, **kw):
        who = who_fn(); ps = processes(); pr = current_process()
        return page(tpl, title=title, active=active, width="none", steps=STEPS, may=roles.may(who, VERB), holders=reads.holders(VERB), last=session.last,
                    receipt_acts=("planning.",), dims=DIMS, levels=LEVELS, domains=domains(), processes=ps, process=pr, process_name=next((p["process_name"] for p in ps if p["process"] == pr), pr), **kw)

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
            return show(P_TYPES, "Role types", "planning_roles", types=everything()[1]["types"])
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
        domain = (f.get("domain") or "").strip()
        dname = {d["domain"]: d["domain_name"] for d in domains() if d["process"] == pr}
        chosen = [d for d in f.getlist("dim") if d in LEVELS] if card == "multiple" else []
        lv = {d: f.get(f"level_{d}") or "" for d in chosen}
        taken = {t["type_code"] for t in s["types"]} | {t["type_name"].lower() for t in s["types"]}
        checks = [who_may(who),
                  {"check": "a name", "ok": bool(code), "says": f"{name} ({code})" if code else "a role type is named"},
                  {"check": "a name not taken", "ok": code not in taken and name.lower() not in taken, "says": "no other role type is called that" if code not in taken and name.lower() not in taken else f"there is already a role type {name}"},
                  {"check": "its domain", "ok": not domain or domain in dname, "says": dname.get(domain, "not categorised") if not domain or domain in dname else f"{domain} is not a domain of this planning process"},
                  {"check": "its cardinality", "ok": card == "single" or (bool(chosen) and all(lv[d] in LEVELS[d] for d in chosen)),
                   "says": "single — one role for the whole business" if card == "single" else ("multiple, by " + " × ".join(f"{d.replace('_', ' ')} at {LEVELS[d][lv[d]][0].lower()}" for d in chosen) if chosen else "a multiple type says what tells its roles apart")}]
        return done("planning.type.add", who, name or "a role type", checks,
                    lambda: TYPES.place([{"type_code": code, "type_name": name, "purpose": (f.get("purpose") or "").strip(), "cardinality": card,
                                          "site_level": lv.get("site", ""), "customer_level": lv.get("customer", ""), "cost_centre_level": lv.get("cost_centre", ""),
                                          "process": pr, "domain": domain, "set_by": who, "set_on": now()}], who),
                    f"{name} added — next, its entitlements", url_for("plan.planning_types", process=current_process()))

    @bp.post("/planning/types/set")
    def planning_types_set():
        """Role types changed where they are listed (ambiguity #144): the name and the domain. The code, the cardinality
        and the levels stand — its roles are made of them."""
        f = request.form; who = who_fn(); pr = current_process(); s = state(pr)
        dname = {d["domain"]: d["domain_name"] for d in domains() if d["process"] == pr}
        rows, says, bad = [], [], []
        names = {t["type_code"]: t["type_name"] for t in s["types"]}
        for t in s["types"]:
            tc = t["type_code"]
            name = f.get(f"n|{tc}"); name = t["type_name"] if name is None else name.strip()
            dom = f.get(f"d|{tc}"); dom = (t.get("domain") or "") if dom is None else dom.strip()
            if not name:
                bad.append(f"{t['type_name']}: a role type is named"); continue
            if dom and dom not in dname:
                bad.append(f"{name}: {dom} is not a domain of this planning process"); continue
            if name == t["type_name"] and dom == (t.get("domain") or ""):
                continue
            names[tc] = name
            rows.append({"type_code": tc, "type_name": name, "purpose": t.get("purpose") or "", "cardinality": t["cardinality"], "site_level": t.get("site_level") or "",
                         "customer_level": t.get("customer_level") or "", "cost_centre_level": t.get("cost_centre_level") or "", "process": pr, "domain": dom, "set_by": who, "set_on": now()})
            says.append(f"{name} — {dname.get(dom, 'not categorised')}")
        low = [n.lower() for n in names.values()]
        twice = sorted({n for n in names.values() if low.count(n.lower()) > 1})
        checks = [who_may(who),
                  {"check": "a role type changed", "ok": bool(rows), "says": "; ".join(says) or "no role type differs from the list standing"},
                  {"check": "a name and a domain of its process", "ok": not bad, "says": "every one named, in a domain of its process or none" if not bad else "; ".join(bad)},
                  {"check": "a name not taken", "ok": not twice, "says": "no two role types share a name" if not twice else "two role types called " + ", ".join(twice)}]
        return done("planning.types.set", who, f"{len(rows)} role types", checks, lambda: TYPES.place(rows, who),
                    f"{len(rows)} role type{'s' if len(rows) != 1 else ''} changed — {'; '.join(says)}", url_for("plan.planning_types", process=pr))

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
            s = state(current_process())
            _, fol = follows(s)
            tname = {t["type_code"]: t["type_name"] for t in s["types"]}
            prep = {fa: tc for (fa, tc), lv in s["cells"].items() if lv == "prepare"}
            for f in s["facts"]:
                f["kind_says"] = "calculated" if f["kind"] == "calculated" else "standing"
                f["prepared_by"] = tname.get(prep.get(f["fact"]))
            # ownership alone is shown and set (ambiguity #137): the matrix opens, the role view narrows it to one type
            one = next((t for t in s["types"] if t["type_code"] == request.args.get("type")), None)
            owns = bool(one and one["type_code"] in prep.values())
            all_facts = request.args.get("facts") == "all" or bool(one and not owns)
            facts, types = s["facts"], s["types"]
            if one:
                types = [one]
                fol = [r for r in fol if r["type_name"] == one["type_name"]]
                if not all_facts:
                    facts = [f for f in facts if prep.get(f["fact"]) == one["type_code"]]
            return show(P_ENT, "Entitlements", "planning_roles", facts=facts, types=types, every_type=s["types"], one=one, all_facts=all_facts,
                        cells=s["cells"], follows=fol)
        except Busy as e:
            return busy("Entitlements", e)

    @bp.post("/planning/entitlements/set")
    def planning_entitlements_set():
        f = request.form; who = who_fn(); s = state(current_process())
        tname = {t["type_code"]: t["type_name"] for t in s["types"]}
        fproc = {r["fact"]: r["process"] for r in q("select fact, process from dims.ref_fact")}
        tproc = {r["type_code"]: r["process"] for r in q("select type_code, process from dims.planning_role_type")}
        changed, across = {}, []
        for name, tc in f.items():                            # one mark a fact: the role type that owns it
            tag, _, fact = name.partition("|")
            if tag != "o":
                continue
            if fact in fproc and tc in tproc and fproc[fact] != tproc[tc]:
                across.append(f"{fact.replace('_', ' ')} — {tc.replace('_', ' ').lower()}")
            elif fact in s["names"] and tc in tname and s["cells"].get((fact, tc)) != "prepare":
                changed[(fact, tc)] = "prepare"
                for (x, was), lv in s["cells"].items():       # moving a fact clears its former owner
                    if x == fact and was != tc and lv == "prepare":
                        changed[(fact, was)] = ""
        after = {**s["cells"], **changed}
        wrong = []
        for fact, nm in s["names"].items():
            ps = [tname[tc] for (x, tc), lv in after.items() if x == fact and lv == "prepare"]
            if len(ps) != 1:
                wrong.append(f"{nm}: {'nobody owns it' if not ps else ' and '.join(ps) + ' both own it'}")
        moved = sorted((fa, tc) for (fa, tc), v in changed.items() if v == "prepare")
        says = "; ".join(f"{s['names'][fa]} — {tname[tc]}" for fa, tc in moved)
        checks = [who_may(who),
                  {"check": "a fact moved", "ok": bool(moved), "says": says or "no fact has a different owner from the table standing"},
                  {"check": "within one planning process", "ok": not across,
                   "says": "every fact is owned by a role type of its own process" if not across else "no ownership across processes: " + "; ".join(across)},
                  {"check": "exactly one role type owns each fact", "ok": not wrong, "says": "every fact has one" if not wrong else "; ".join(wrong)}]
        at = now()
        return done("planning.entitlements.set", who, f"{len(moved)} facts", checks,
                    lambda: ENTITLEMENTS.place([{"fact": fa, "type_code": tc, "level": v, "set_by": who, "set_on": at} for (fa, tc), v in sorted(changed.items())], who),
                    f"{len(moved)} fact{'s' if len(moved) != 1 else ''} moved — {says}", url_for("plan.planning_entitlements", type=f.get("type") or None, facts=f.get("facts") or None, process=current_process()))

    # ── 3 · roles ────────────────────────────────────────────────────────────────────────────────────────────────────
    def next_no() -> str:
        used = [int(r["role_no"]) for r in q("select role_no from dims.planning_role") if str(r["role_no"]).isdigit()]
        return str(max(used) + 1 if used else 1000)

    @bp.get("/planning/roles")
    def planning_roles():
        try:
            s, every = everything()
            chosen = next((t for t in s["types"] if t["type_code"] == request.args.get("type")), None) or next((t for t in s["types"] if t["can_add"]), None)
            return show(P_ROLES, "Roles", "planning_roles", own=s["types"], types=every["types"], n_roles=len(every["roles"]), chosen=chosen, next_no=next_no(), extra=s["extra"])
        except Busy as e:
            return busy("Roles", e)

    @bp.post("/planning/roles/add")
    def planning_role_add():
        f = request.form; who = who_fn(); s = state(current_process())
        t = next((x for x in s["types"] if x["type_code"] == f.get("type_code")), None)
        no = (f.get("role_no") or "").strip()
        own = {d["dim"] for d in (t["dims"] if t else [])}
        place_ = {d: (f.get(d) or "") for d, _ in DIMS if d in own or f.get(d)}      # the type's dimensions, and any the role adds
        valid = all(place_[d["dim"]] in {m["code"] for m in d["members"]} for d in (t["dims"] if t else [])) \
            and all((d, v) in s["label"] for d, v in place_.items() if d not in own)
        ctx = " × ".join(s["label"].get((d, place_[d]), place_[d]) for d, _ in DIMS if place_.get(d))
        clash = [r["role_no"] for r in (t["roles"] if t else []) if all((r.get(d) or "") == place_.get(d, "") for d, _ in DIMS)]
        ever = {str(r["role_no"]) for r in q("select role_no from dims.planning_role")}
        name = (f.get("role_name") or "").strip() or (f"{t['type_name']}, {ctx}" if t and ctx else (t["type_name"] if t else ""))
        checks = [who_may(who),
                  {"check": "a role type", "ok": bool(t), "says": t["type_name"] if t else "a role is of a role type"},
                  {"check": "its number", "ok": no.isdigit() and no not in ever, "says": f"{no} — not used before" if no.isdigit() and no not in ever else (f"{no} has been used — a number is never reused" if no in ever else "a role has a number")},
                  {"check": "its place", "ok": bool(t) and valid and not clash,
                   "says": (f"role {clash[0]} already covers {ctx or 'the whole business'}" if clash else (ctx or "the whole business") if valid else "a member at the type's level for each of its dimensions, and a member the dimension has for any it adds")}]
        return done("planning.role.add", who, f"{no} {name}", checks,
                    lambda: ROLES.place([{"role_no": no, "type_code": t["type_code"], "role_name": name, "purpose": (f.get("purpose") or "").strip(),
                                          "site": place_.get("site", ""), "customer": place_.get("customer", ""), "cost_centre": place_.get("cost_centre", ""),
                                          "status": "live", "set_by": who, "set_on": now()}], who),
                    f"role {no} defined — {name}; nobody holds it until it is assigned", url_for("plan.planning_roles", type=f.get("type_code") or None, process=current_process()))

    @bp.post("/planning/roles/set")
    def planning_roles_set():
        """Roles changed where they are listed (ambiguity #142): a member in a dimension of the type, or the title; the
        number and the type stand. A change is a new row for the same number."""
        f = request.form; who = who_fn(); s = state(current_process())
        of = {t["type_code"]: t for t in s["types"]}
        def title(t: dict, place: dict) -> str:
            ctx = " × ".join(s["label"].get((d, place[d]), place[d]) for d, _ in DIMS if place.get(d))
            return f"{t['type_name']}, {ctx}" if ctx else t["type_name"]
        rows, says, bad = [], [], []
        after = {r["role_no"]: {d: r.get(d) or "" for d, _ in DIMS} for r in s["roles"]}
        for r in s["roles"]:
            t = of[r["type_code"]]; no = r["role_no"]
            old = {d: r.get(d) or "" for d, _ in DIMS}; new = dict(old)
            for d in t["dims"]:
                v = f.get(f"m|{no}|{d['dim']}")
                if v is None:
                    continue
                if v not in {m["code"] for m in d["members"]}:
                    bad.append(f"{no}: {v or 'nothing'} is not a {d['level_name'].lower()}")
                else:
                    new[d["dim"]] = v
            for d, dn in DIMS:                                 # a dimension the type does not name: nothing, or a member it has
                v = f.get(f"m|{no}|{d}")
                if v is None or d in {x["dim"] for x in t["dims"]}:
                    continue
                if v and (d, v) not in s["label"]:
                    bad.append(f"{no}: {v} is not a member of {dn.lower()}")
                else:
                    new[d] = v
            name = f.get(f"t|{no}"); name = r["role_name"] if name is None else name.strip()
            if not name or (new != old and name == r["role_name"] and r["role_name"] == title(t, old)):
                name = title(t, new)                           # a title left as the type and place follows the place
            if new == old and name == r["role_name"]:
                continue
            after[no] = new
            rows.append({"role_no": no, "type_code": r["type_code"], "role_name": name, "purpose": r.get("purpose") or "", **new, "status": "live", "set_by": who, "set_on": now()})
            says.append(f"{no} {name}" + (f" — now at {title(t, new).split(', ', 1)[-1]}" if new != old else ""))
        seen, clash = {}, []
        for r in s["roles"]:
            if of[r["type_code"]]["cardinality"] == "multiple":
                k = (r["type_code"], *(after[r["role_no"]][d] for d, _ in DIMS))
                if k in seen:
                    clash.append(f"{seen[k]} and {r['role_no']}")
                seen[k] = r["role_no"]
        checks = [who_may(who),
                  {"check": "a role changed", "ok": bool(rows), "says": "; ".join(says) or "no role differs from the list standing"},
                  {"check": "each at a member of its type's level", "ok": not bad, "says": "every member is at its type's level, or one the dimension has where the role adds it" if not bad else "; ".join(bad)},
                  {"check": "one role of a type at a place", "ok": not clash, "says": "no two roles of a type share a place" if not clash else "the same type at the same place: " + "; ".join(clash)}]
        return done("planning.roles.set", who, f"{len(rows)} roles", checks, lambda: ROLES.place(rows, who),
                    f"{len(rows)} role{'s' if len(rows) != 1 else ''} changed — {'; '.join(says)}", url_for("plan.planning_roles", process=current_process()))

    # ── 4 · assignments ──────────────────────────────────────────────────────────────────────────────────────────────
    @bp.get("/planning/assignments")
    def planning_assignments():
        try:
            s, every = everything()
            by_no = {r["role_no"]: r for r in every["roles"]}
            tprep = {t["type_code"]: t["prepares"] for t in every["types"]}
            def prepares(r: dict) -> list[str]:
                return [f"{x}{' at ' + r['context'] if r['context'] else ''}" for x in tprep.get(r["type_code"], [])]
            rows = [{**a, **{k: by_no[a["role_no"]][k] for k in ("role_name", "process", "process_name", "scope", "levels", "domain", "domain_name")},
                     "prepares": prepares(by_no[a["role_no"]]) if a["live"] else []} for a in every["asg"] if a["role_no"] in by_no]
            people = [r["principal"] for r in q("select distinct principal from dims.ctl_role_assignment order by 1")]
            return show(P_ASG, "Assignments", "planning_roles", rows=rows, roles=s["roles"], people=people, today=dt.date.today().isoformat(),
                        empty=[{**r, "prepares": prepares(r)} for r in every["roles"] if not r["held"]], cover=[r for r in every["roles"] if len(r["held"]) > 1])
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
