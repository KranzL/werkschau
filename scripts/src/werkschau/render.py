from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from .org import Org, Person
from .scoring import Initiative, Scores, median


NOT_LOCKED_THRESHOLD: float = -0.6


@dataclass
class UserBlock:
    person: Person
    scores: Scores
    narrative: str


def render_html(
    org: Org,
    blocks: list[UserBlock],
    since_iso: str,
    until_iso: str,
    issue_number: int = 1,
    skip_briefs: bool = False,
) -> str:
    by_id = {b.person.id: b for b in blocks}
    locked_in, not_locked_in = _classify_callouts(blocks)
    headline_dek = _headline_dek(blocks, locked_in, not_locked_in)
    until_dt = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
    until_human = until_dt.strftime("%A, %B %-d, %Y") if hasattr(until_dt, "strftime") else until_iso
    until_short = until_dt.strftime("%B %-d, %Y") if hasattr(until_dt, "strftime") else until_iso

    callouts_html = _render_callouts(locked_in, not_locked_in)
    chart_html = _render_chart_svg(blocks)
    rollup_html = _render_rollup(org, by_id)
    ledger_html = _render_ledger(org, by_id)
    briefs_html = "" if skip_briefs else _render_briefs(org, by_id)
    briefs_section = "" if not briefs_html.strip() else f'''
  <section class="briefs">
    <div class="briefs-head">
      <h2>The Breakdown</h2>
      <p>A page for each manager — what they and their team shipped this week.</p>
    </div>
    {briefs_html}
  </section>'''

    return _PAGE.format(
        css=_CSS,
        nameplate_meta=_render_nameplate_meta(issue_number, until_human),
        kicker_aud=_html(f"Prepared for {org.vp.name}"),
        title="A scored snapshot of the org's week.",
        dek=headline_dek,
        byline=_render_byline(blocks, until_short),
        callouts=callouts_html,
        chart=chart_html,
        rollup=rollup_html,
        ledger=ledger_html,
        briefs_section=briefs_section,
        about=_about_text(),
    )


def _render_nameplate_meta(issue_number: int, until_human: str) -> str:
    return (
        f'<span>Vol. I</span><span class="sep">·</span>'
        f'<span>No. {issue_number}</span><span class="sep">·</span>'
        f'<span>{_html(until_human)}</span><span class="sep">·</span>'
        f'<span>Engineering Edition</span>'
    )


def _is_not_locked(b: UserBlock) -> bool:
    return (
        b.scores.output <= NOT_LOCKED_THRESHOLD
        and b.scores.focus <= NOT_LOCKED_THRESHOLD
        and not b.person.is_director
    )


def _classify_callouts(blocks: list[UserBlock]) -> tuple[list[UserBlock], list[UserBlock]]:
    locked = [b for b in blocks if b.scores.output > 0 and b.scores.focus > 0]
    not_locked = [b for b in blocks if _is_not_locked(b)]
    locked.sort(key=lambda b: (b.scores.output + b.scores.focus), reverse=True)
    not_locked.sort(key=lambda b: (b.scores.output + b.scores.focus))
    return locked, not_locked


def _headline_dek(blocks: list[UserBlock], locked: list[UserBlock], not_locked: list[UserBlock]) -> str:
    n_locked = len(locked)
    n_not = len(not_locked)
    n_total = len(blocks)
    n_middle = n_total - n_locked - n_not

    def number_word(n: int) -> str:
        return ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"][n] if n < 11 else str(n)

    parts: list[str] = []
    if n_locked == 1:
        parts.append("One contributor is running ahead of pace this week.")
    elif n_locked > 1:
        parts.append(f"{number_word(n_locked).capitalize()} contributors are running ahead of pace this week.")
    else:
        parts.append("No contributors are running ahead of pace this week.")
    if n_not == 1:
        parts.append("One is running behind.")
    elif n_not > 1:
        parts.append(f"{number_word(n_not).capitalize()} are running behind.")
    if n_middle > 0:
        parts.append("The rest hold the middle of the chart.")
    return " ".join(parts)


def _render_byline(blocks: list[UserBlock], until_short: str) -> str:
    n_total = len(blocks)
    n_mgr = sum(1 for b in blocks if b.person.is_manager or b.person.is_director)
    return (
        f'By <strong>The Werkschau Desk</strong>'
        f'<span class="mast-byline-sep">·</span>{_html(until_short)}'
        f'<span class="mast-byline-sep">·</span>'
        f'{n_total} contributors, {n_mgr} of whom manage teams'
    )


def _render_callouts(locked: list[UserBlock], not_locked: list[UserBlock]) -> str:
    def names(blocks: list[UserBlock]) -> str:
        if not blocks:
            return '<li><em>none</em></li>'
        items: list[str] = []
        for b in blocks:
            label = b.person.github or b.person.name
            if b.person.github is None:
                tag = "no github"
            else:
                tag = (b.person.level or "").lower()
            items.append(f'<li>{_html(label)}<em>{_html(tag)}</em></li>')
        return "".join(items)
    return f"""
  <div class="callout callout-pos">
    <div class="callout-label">Locked in</div>
    <ol class="callout-names">{names(locked)}</ol>
  </div>
  <div class="callout callout-neg">
    <div class="callout-label">Not locked in</div>
    <ol class="callout-names">{names(not_locked)}</ol>
  </div>"""


def _render_chart_svg(blocks: list[UserBlock]) -> str:
    dots: list[str] = []
    for b in blocks:
        x = 80 + (b.scores.focus + 1) * 200
        y = 360 - (b.scores.output + 1) * 150
        is_mgr = b.person.is_manager or b.person.is_director
        is_director = b.person.is_director
        is_offgrid = b.person.github is None
        if is_offgrid:
            stroke, fill = "#bbbbbb", "#ffffff"
            text_weight, text_fill = "400", "#999999"
        elif is_director and not (b.scores.output > 0 and b.scores.focus > 0):
            stroke = "#999999"
            fill = "#999999"
            text_weight, text_fill = "500", "#666666"
        elif b.scores.output > 0 and b.scores.focus > 0:
            stroke, fill = "#1a7c36", "#1a7c36"
            text_weight, text_fill = "600", "#121212"
        elif _is_not_locked(b):
            stroke, fill = "#c4192c", "#c4192c"
            text_weight, text_fill = "600", "#121212"
        else:
            stroke = "#999999"
            fill = "#666666" if (b.scores.output > 0 or b.scores.focus < 0) else "#999999"
            text_weight, text_fill = "400", "#666666"
        label_x = x + 9
        label_y = y + 4
        anchor = "start"
        if x > 420:
            label_x = x - 9
            anchor = "end"
        label = b.person.github or b.person.name
        if is_offgrid:
            dots.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}" stroke="{stroke}" stroke-width="1" stroke-dasharray="2 2"/>'
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
                f'font-family="\'Source Serif Pro\', Georgia, serif" font-style="italic" '
                f'font-size="10.5" font-weight="{text_weight}" fill="{text_fill}">{_html(label)}</text>'
            )
            continue
        if is_mgr:
            label_y = y - 13
            anchor = "middle"
            label_x = x
            dots.append(
                f'<rect x="{x-7:.1f}" y="{y-7:.1f}" width="14" height="14" '
                f'fill="#ffffff" stroke="{stroke}" stroke-width="1.5"/>'
                f'<rect x="{x-3.4:.1f}" y="{y-3.4:.1f}" width="6.8" height="6.8" '
                f'fill="{fill}" filter="url(#dotShadow)"/>'
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
                f'font-family="\'Helvetica Neue\', Helvetica, Arial, sans-serif" '
                f'font-size="11.5" font-weight="{text_weight}" fill="{text_fill}">{_html(label)}</text>'
            )
        else:
            dots.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#ffffff" stroke="{stroke}" stroke-width="1.5"/>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{fill}" filter="url(#dotShadow)"/>'
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
                f'font-family="\'Helvetica Neue\', Helvetica, Arial, sans-serif" '
                f'font-size="11.5" font-weight="{text_weight}" fill="{text_fill}">{_html(label)}</text>'
            )
    return _CHART_SVG_TEMPLATE.format(dots="\n      ".join(dots))


def _render_mini_chart_svg(blocks: list[UserBlock]) -> str:
    if not blocks:
        return ""
    dots: list[str] = []
    for b in blocks:
        x = 70 + (b.scores.focus + 1) * 180
        y = 310 - (b.scores.output + 1) * 130
        is_mgr = b.person.is_manager or b.person.is_director
        is_director = b.person.is_director
        is_offgrid = b.person.github is None
        if is_offgrid:
            stroke, fill = "#bbbbbb", "#ffffff"
            label_fill, label_weight = "#999999", "400"
        elif is_director and not (b.scores.output > 0 and b.scores.focus > 0):
            stroke, fill = "#999999", "#999999"
            label_fill, label_weight = "#666666", "500"
        elif b.scores.output > 0 and b.scores.focus > 0:
            stroke, fill = "#1a7c36", "#1a7c36"
            label_fill, label_weight = "#121212", "600"
        elif _is_not_locked(b):
            stroke, fill = "#c4192c", "#c4192c"
            label_fill, label_weight = "#121212", "600"
        else:
            stroke, fill = "#999999", "#999999"
            label_fill, label_weight = "#666666", "400"
        label_x = x + 9
        anchor = "start"
        if x > 350:
            label_x = x - 9
            anchor = "end"
        label = b.person.github or b.person.name
        if is_offgrid:
            dots.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}" stroke="{stroke}" stroke-width="1.1" stroke-dasharray="2 2"/>'
                f'<text x="{label_x:.1f}" y="{y+4:.1f}" text-anchor="{anchor}" font-family="\'Source Serif Pro\', Georgia, serif" font-style="italic" font-size="11" font-weight="{label_weight}" fill="{label_fill}">{_html(label)}</text>'
            )
            continue
        if is_mgr:
            dots.append(
                f'<rect x="{x-6.5:.1f}" y="{y-6.5:.1f}" width="13" height="13" fill="#ffffff" stroke="{stroke}" stroke-width="1.4"/>'
                f'<rect x="{x-3.2:.1f}" y="{y-3.2:.1f}" width="6.4" height="6.4" fill="{fill}"/>'
                f'<text x="{label_x:.1f}" y="{y+4:.1f}" text-anchor="{anchor}" font-family="\'Helvetica Neue\', Helvetica, sans-serif" font-size="11.5" font-weight="{label_weight}" fill="{label_fill}">{_html(label)}</text>'
            )
        else:
            dots.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="#ffffff" stroke="{stroke}" stroke-width="1.4"/>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{fill}"/>'
                f'<text x="{label_x:.1f}" y="{y+4:.1f}" text-anchor="{anchor}" font-family="\'Helvetica Neue\', Helvetica, sans-serif" font-size="11.5" font-weight="{label_weight}" fill="{label_fill}">{_html(label)}</text>'
            )
    return f'''<svg viewBox="0 0 480 380" width="100%" style="max-width: 480px; display: block; margin: 12px 0 18px;" xmlns="http://www.w3.org/2000/svg">
  <rect x="70" y="50" width="360" height="260" fill="#ffffff"/>
  <rect x="250" y="50" width="180" height="130" fill="#1a7c36" fill-opacity="0.07"/>
  <rect x="70" y="258" width="72" height="52"  fill="#c4192c" fill-opacity="0.20"/>
  <line x1="250" y1="50" x2="250" y2="310" stroke="#999999" stroke-width="0.7" stroke-dasharray="3 3"/>
  <line x1="70" y1="180" x2="430" y2="180" stroke="#999999" stroke-width="0.7" stroke-dasharray="3 3"/>
  <rect x="70" y="50" width="360" height="260" fill="none" stroke="#121212" stroke-width="0.95"/>
  <text x="425" y="68" text-anchor="end" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="11.5" fill="#1a7c36" font-weight="600">locked in</text>
  <text x="75" y="68" text-anchor="start" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="11.5" fill="#666666">deep dive</text>
  <text x="425" y="304" text-anchor="end" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="11.5" fill="#666666">scattered</text>
  <text x="75" y="304" text-anchor="start" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="11.5" fill="#c4192c" font-weight="600">not locked in</text>
  <text x="250" y="338" text-anchor="middle" font-family="'Helvetica Neue', Helvetica, sans-serif" font-size="9.5" font-weight="700" letter-spacing="0.22em" fill="#666666">FOCUS</text>
  <g transform="translate(28, 180) rotate(-90)"><text text-anchor="middle" font-family="'Helvetica Neue', Helvetica, sans-serif" font-size="9.5" font-weight="700" letter-spacing="0.22em" fill="#666666">OUTPUT</text></g>
  {chr(10).join(dots)}
</svg>'''


def _render_rollup(org: Org, by_id: dict) -> str:
    rows: list[str] = []
    for leader in (*org.directors(), *org.managers()):
        reports = org.reports_of(leader.id)
        scored_reports = [by_id[p.id] for p in reports if p.id in by_id]
        if not scored_reports:
            continue
        team_minutes = sum(b.scores.weighted_minutes for b in scored_reports)
        team_loc = sum(sum(b.scores.churn_by_kind.values()) for b in scored_reports)
        n_locked = sum(1 for b in scored_reports if b.scores.output > 0 and b.scores.focus > 0)
        n_below = sum(1 for b in scored_reports if b.scores.output < 0 and b.scores.focus < 0)
        n_active = sum(1 for b in scored_reports if b.scores.commit_count > 0)
        label = leader.github or leader.name
        rows.append(f"""
    <div class="rollup-row">
      <span class="rollup-mgr">{_html(label)} <small>{len(reports)} reports · {n_active} active</small></span>
      <span class="rollup-stat"><span class="rollup-stat-key">Team</span><span class="rollup-stat-val">{int(team_minutes):,}<small> min</small></span></span>
      <span class="rollup-stat"><span class="rollup-stat-key">LOC</span><span class="rollup-stat-val">{team_loc:,}</span></span>
      <span class="rollup-stat"><span class="rollup-stat-key">Locked</span><span class="rollup-stat-val pos">{n_locked}</span><span class="rollup-stat-key" style="margin-left:6px">/ Below</span><span class="rollup-stat-val neg">{n_below}</span></span>
    </div>""")
    return "\n".join(rows)


def _render_ledger(org: Org, by_id: dict) -> str:
    scored_blocks = [by_id[p.id] for p in org.scored_people() if p.id in by_id]
    offgrid_blocks = [by_id[p.id] for p in org.offgrid_people() if p.id in by_id]
    sorted_blocks = sorted(scored_blocks, key=lambda b: b.scores.weighted_minutes, reverse=True) + offgrid_blocks
    rows: list[str] = []
    for b in sorted_blocks:
        is_offgrid = b.person.github is None
        if is_offgrid:
            row_cls = "in-neg is-offgrid"
        elif b.scores.output > 0 and b.scores.focus > 0:
            row_cls = "in-pos"
        elif _is_not_locked(b):
            row_cls = "in-neg"
        else:
            row_cls = ""
        if b.person.is_manager or b.person.is_director:
            row_cls = (row_cls + " is-mgr").strip()
        boss = org.by_id(b.person.manager) if b.person.manager else None
        manager_label = (boss.github or boss.name) if boss else (org.vp.github or org.vp.name)
        level = (b.person.level or "—").lower()
        role = (b.person.role or "").upper()
        if is_offgrid:
            init_cell = '<em>no github account</em>'
            stack_cell = '<em>—</em>'
            minutes_cell = '<em>—</em>'
            commits_cell = '<em>—</em>'
        else:
            top = b.scores.top_initiative
            if top:
                init_cell = f'{_html(top.name)} <small>{int(b.scores.top_initiative_share * 100)}%</small>'
            elif b.scores.commit_count == 0:
                init_cell = '<em>—</em>'
            else:
                init_cell = '<em>scattered</em>'
            stack_cell = _format_loc_by_language(b.scores.loc_by_language, b.scores.churn_by_kind)
            minutes_cell = f'{b.scores.weighted_minutes:.0f}'
            commits_cell = str(b.scores.commit_count)
        rows.append(f"""
        <tr class="{row_cls}">
          <td class="name">{_html(b.person.github or b.person.name)}</td>
          <td class="mgr">{_html(manager_label)}</td>
          <td class="lvl">{_html(level)} <span class="role">{_html(role)}</span></td>
          <td class="init">{init_cell}</td>
          <td class="stack">{stack_cell}</td>
          <td class="num">{minutes_cell}</td>
          <td class="num">{commits_cell}</td>
        </tr>""")
    return "\n".join(rows)


def _format_loc_by_language(loc: dict[str, int], churn_fallback: dict[str, int]) -> str:
    if loc:
        items = [(k, v) for k, v in loc.items() if v >= 5][:3]
        if items:
            return " · ".join(f'{_html(k)} <small>{v:,}</small>' for k, v in items)
    pretty_kind = {
        "code": "code",
        "data_pipeline": "data",
        "test": "tests",
        "infra": "infra",
        "config": "config",
        "docs": "docs",
        "lockfile": "deps",
        "other": "other",
    }
    items = [(k, v) for k, v in churn_fallback.items() if v >= 5][:3]
    if not items:
        return '<em>—</em>'
    return " · ".join(f'{pretty_kind.get(k, k)} <small>{v:,}</small>' for k, v in items)


def _render_briefs(org: Org, by_id: dict) -> str:
    articles: list[str] = []

    vp_direct = [p for p in org.reports_of(org.vp.id)
                 if not p.is_director and not p.is_manager]
    if vp_direct:
        articles.append(_render_vp_direct_brief(org, vp_direct, by_id))

    for director in org.directors():
        articles.append(_render_leader_brief(org, director, by_id, scope="director"))

    for manager in org.managers():
        articles.append(_render_leader_brief(org, manager, by_id, scope="manager"))

    articles = [a for a in articles if a.strip()]
    if not articles:
        return ""
    return "\n".join(articles)


def _render_leader_brief(org: Org, leader: Person, by_id: dict, scope: str) -> str:
    direct_reports = [p for p in org.reports_of(leader.id)
                      if not p.is_manager and not p.is_director]
    if scope == "manager":
        team_label = f"{_html(leader.name)}'s team"
    else:
        team_label = f"{_html(leader.name)}'s direct reports"

    boss = org.by_id(leader.manager) if leader.manager else None
    boss_label = (boss.github or boss.name) if boss else (org.vp.github or org.vp.name)

    leader_block = by_id.get(leader.id)
    if not leader_block and not direct_reports:
        return ""

    cards: list[str] = []
    if leader_block:
        cards.append(_card(leader_block, lead=True))
    else:
        cards.append(_offgrid_card(leader, lead=True))
    for p in direct_reports:
        block = by_id.get(p.id)
        if block:
            cards.append(_card(block, lead=False))
        else:
            cards.append(_offgrid_card(p, lead=False))

    role_label = f"{(leader.level or '').upper()} {(leader.role or '').upper()}".strip()
    if not role_label:
        role_label = "—"

    team_blocks: list[UserBlock] = []
    if leader_block:
        team_blocks.append(leader_block)
    team_blocks.extend(by_id[p.id] for p in direct_reports if p.id in by_id)
    chart_html = _render_mini_chart_svg(team_blocks) if team_blocks else ""

    return f"""
    <article class="brief">
      <h2 class="brief-name">{team_label}</h2>
      <p class="brief-meta">{_html(role_label)} · {len(direct_reports)} reports · reports to {_html(boss_label or '—')}</p>
      {chart_html}
      {''.join(cards)}
    </article>"""


def _render_vp_direct_brief(org: Org, direct_reports: list[Person], by_id: dict) -> str:
    cards: list[str] = []
    blocks_for_chart: list[UserBlock] = []
    for p in direct_reports:
        block = by_id.get(p.id)
        if block:
            cards.append(_card(block, lead=False))
            blocks_for_chart.append(block)
        else:
            cards.append(_offgrid_card(p, lead=False))
    chart_html = _render_mini_chart_svg(blocks_for_chart) if blocks_for_chart else ""
    return f"""
    <article class="brief">
      <h2 class="brief-name">Reports to {_html(org.vp.name)}</h2>
      <p class="brief-meta">VP-direct contributors · {len(direct_reports)} reports</p>
      {chart_html}
      {''.join(cards)}
    </article>"""


def _card(block: UserBlock, lead: bool) -> str:
    if block.person.github is None:
        return _offgrid_card(block.person, lead)
    meta = _meta_chip(block)
    narrative = block.narrative.strip()
    summary, bullets = _parse_brief(narrative) if narrative else ("", [])
    if not summary and not bullets:
        summary = "No commit-visible activity this week."
    cls = "brief-person brief-person-lead" if lead else "brief-person"
    label = block.person.name or (block.person.github or "")

    parts = [f'<h3>{_html(label)} <em>{meta}</em></h3>']
    if block.person.description:
        parts.append(
            f'<p class="brief-person-owns"><em>Owns</em> {_html(block.person.description)}</p>'
        )
    if summary:
        parts.append(f'<p class="brief-person-summary">{_bold_md(summary)}</p>')
    if bullets:
        items = "".join(f'<li>{_bold_md(b)}</li>' for b in bullets)
        parts.append(f'<ul class="brief-person-bullets">{items}</ul>')
    return f"""
      <div class="{cls}">
        {''.join(parts)}
      </div>"""


def _offgrid_card(person: Person, lead: bool) -> str:
    cls = "brief-person brief-person-lead" if lead else "brief-person"
    role_chip = f"{(person.level or '').upper()} {(person.role or '').upper()}".strip()
    chip = (role_chip + " · no github").strip(" ·") if role_chip else "no github account"
    label = person.name or (person.github or "")
    parts = [f'<h3>{_html(label)} <em>{_html(chip)}</em></h3>']
    if person.description:
        parts.append(
            f'<p class="brief-person-owns"><em>Owns</em> {_html(person.description)}</p>'
        )
    parts.append(
        '<p class="brief-person-summary"><em>No GitHub account on record. No commit-visible work is tracked here.</em></p>'
    )
    return f"""
      <div class="{cls}">
        {''.join(parts)}
      </div>"""


def _parse_brief(narrative: str) -> tuple[str, list[str]]:
    lines = [l.rstrip() for l in narrative.strip().split("\n")]
    summary_parts: list[str] = []
    bullets: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ", "• ")):
            bullets.append(line[2:].strip())
        elif line.startswith("-") and len(line) > 1 and line[1] != "-":
            bullets.append(line[1:].strip())
        else:
            if not bullets:
                summary_parts.append(line)
    return " ".join(summary_parts).strip(), bullets


def _bold_md(s: str) -> str:
    parts = s.split("**")
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(f"<strong>{_html(part)}</strong>")
        else:
            out.append(_html(part))
    return "".join(out)


def _meta_chip(b: UserBlock) -> str:
    level = (b.person.level or "").upper()
    role = (b.person.role or "").upper()
    if b.scores.commit_count == 0:
        return _html(f"{level} {role} · no commits")
    return _html(f"{level} {role} · {b.scores.commit_count} commits · est. {b.scores.weighted_minutes:.0f} min")


def _html(s: str) -> str:
    return html.escape(s or "")


def _about_text() -> str:
    return (
        "<span class=\"dropcap\">W</span>erkschau measures commit-visible work only. "
        "Code review, design, mentorship, debugging, exploratory analysis in notebooks, "
        "and dashboards built in BI tools are invisible here — a bias largest for senior "
        "ICs and for Data Scientists, ML Engineers, and Data Analysts. Managers and "
        "directors are scored as contributors alongside ICs whenever they ship code; "
        "only the audience leader (the VP) is exempt. The horizontal axis is "
        "<em>breadth</em> — how many distinct <em>initiatives</em> the contributor "
        "had this week. Two commits join the same initiative when they happen "
        "within 48 hours of each other and share a conventional-commit scope, a "
        "meaningful message token, or a top-level directory; so a 4-repo shipped "
        "change for one feature collapses into a single initiative and lands on "
        "the left, not scattered. The vertical axis is <em>output</em> — log-ratio "
        "of weighted commit minutes to a fixed 600 minute / week reference. "
        "Per-commit effort is heuristic-base × complexity multiplier × file-kind "
        "weight: code, SQL/Airflow/dbt, tests, and infrastructure count at full "
        "weight; generic configuration at 60%; documentation at 20%; lockfile-only "
        "commits at 10%. A week of pure README edits will not register as locked "
        "in. The two callouts are diagonal: <em>locked in</em> is the top-right "
        "(lots of code shipped across many initiatives), <em>not locked in</em> "
        "is the bottom-left (little code, one initiative or none). The other two "
        "quadrants are descriptive rather than judged: top-left is a deep dive "
        "(lots of code, one focused initiative); bottom-right is scattered (many "
        "initiatives, little code on each). Levels and roles appear on each card "
        "and in the ledger as context but do not enter the score formula. Each "
        "commit is also categorized into a stack mix (code, data, tests, infra, "
        "config, docs, deps); the dominant initiative and stack appear in the "
        "per-contributor ledger. Manager rollups are the median of each manager's "
        "direct reports."
    )


_CHART_SVG_TEMPLATE = """<svg class="chart-svg" viewBox="0 0 540 460" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Quadrant chart of focus by output">
  <defs>
    <pattern id="grid" width="40" height="30" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 30" fill="none" stroke="#e2e2e2" stroke-width="0.4"/>
    </pattern>
    <filter id="dotShadow" x="-50%" y="-50%" width="200%" height="200%">
      <feDropShadow dx="0" dy="0.6" stdDeviation="0.7" flood-color="#000000" flood-opacity="0.18"/>
    </filter>
  </defs>
  <rect x="80" y="60" width="400" height="300" fill="#ffffff"/>
  <rect x="280" y="60"  width="200" height="150" fill="#1a7c36" fill-opacity="0.07"/>
  <rect x="80"  y="300" width="80"  height="60"  fill="#c4192c" fill-opacity="0.20"/>
  <rect x="80" y="60" width="400" height="300" fill="url(#grid)"/>
  <line x1="280" y1="60" x2="280" y2="360" stroke="#999999" stroke-width="0.7" stroke-dasharray="3 3"/>
  <line x1="80" y1="210" x2="480" y2="210" stroke="#999999" stroke-width="0.7" stroke-dasharray="3 3"/>
  <rect x="80" y="60" width="400" height="300" fill="none" stroke="#121212" stroke-width="1"/>
  <text x="475" y="80"  text-anchor="end"   font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="12" letter-spacing="0.04em" fill="#1a7c36" font-weight="600">locked in</text>
  <text x="85"  y="80"  text-anchor="start" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="12" letter-spacing="0.04em" fill="#666666">deep dive</text>
  <text x="475" y="350" text-anchor="end"   font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="12" letter-spacing="0.04em" fill="#666666">scattered</text>
  <text x="85"  y="350" text-anchor="start" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="12" letter-spacing="0.04em" fill="#c4192c" font-weight="600">not locked in</text>
  <g transform="translate(26, 210) rotate(-90)"><text text-anchor="middle" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10" font-weight="700" letter-spacing="0.24em" fill="#121212">OUTPUT</text></g>
  <text x="72" y="64"  text-anchor="end" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700" fill="#121212">+1</text>
  <text x="72" y="76"  text-anchor="end" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="9.5" fill="#666666">≈1200 min/wk</text>
  <text x="72" y="214" text-anchor="end" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="600" fill="#666666">0</text>
  <text x="72" y="226" text-anchor="end" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="9.5" fill="#666666">≈600 min/wk</text>
  <text x="72" y="364" text-anchor="end" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700" fill="#121212">−1</text>
  <text x="72" y="352" text-anchor="end" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="9.5" fill="#666666">≈300 min/wk</text>
  <g stroke="#121212" stroke-width="1">
    <line x1="76" y1="60"  x2="80" y2="60"/>
    <line x1="76" y1="210" x2="80" y2="210"/>
    <line x1="76" y1="360" x2="80" y2="360"/>
  </g>
  <text x="280" y="408" text-anchor="middle" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10" font-weight="700" letter-spacing="0.24em" fill="#121212">FOCUS</text>
  <text x="280" y="423" text-anchor="middle" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="10" fill="#666666">breadth across initiatives</text>
  <text x="80"  y="378" text-anchor="middle" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700" fill="#121212">−1</text>
  <text x="80"  y="392" text-anchor="middle" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="9.5" fill="#666666">one initiative</text>
  <text x="280" y="378" text-anchor="middle" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="600" fill="#666666">0</text>
  <text x="280" y="392" text-anchor="middle" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="9.5" fill="#666666">two equal</text>
  <text x="480" y="378" text-anchor="middle" font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700" fill="#121212">+1</text>
  <text x="480" y="392" text-anchor="middle" font-family="'Source Serif Pro', Georgia, serif" font-style="italic" font-size="9.5" fill="#666666">many initiatives</text>
  <g stroke="#121212" stroke-width="1">
    <line x1="80"  y1="360" x2="80"  y2="364"/>
    <line x1="280" y1="360" x2="280" y2="364"/>
    <line x1="480" y1="360" x2="480" y2="364"/>
  </g>
  {dots}
</svg>"""


_CSS = """*,*::before,*::after { box-sizing: border-box; }
html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; text-rendering: optimizeLegibility; }
:root {
  --paper: #ffffff; --paper-deep: #f7f7f7; --ink: #121212; --body: #2b2b2b; --mute: #666666;
  --rule: #e2e2e2; --rule-strong: #999999;
  --pos: #1a7c36; --pos-fill: #e6f1ea; --neg: #c4192c; --neg-fill: #fbeaec; --kicker: #c4192c;
  --bar-base: #d8d8d8; --bar-top: #121212;
  --blackletter: "UnifrakturCook", "Engravers MT", "Old English Text MT", serif;
  --serif: "Source Serif Pro", "Source Serif 4", "Hoefler Text", "Iowan Old Style", "Times New Roman", Georgia, serif;
  --sans: "Helvetica Neue", Helvetica, "Arial Nova", Arial, sans-serif;
}
body { margin: 0; background: var(--paper); color: var(--body); font: 14px/1.55 var(--sans); }
main { max-width: 760px; margin: 0 auto; padding: 32px 36px 80px; position: relative; }
.nameplate { text-align: center; padding: 14px 0 16px; border-top: 1px solid var(--ink); border-bottom: 1px solid var(--ink); position: relative; margin-bottom: 22px; }
.nameplate::before { content: ""; position: absolute; top: -5px; left: 0; right: 0; border-top: 1px solid var(--ink); }
.nameplate-name { font-family: var(--blackletter); font-weight: 700; font-size: 78px; line-height: 0.95; letter-spacing: 0.005em; color: var(--ink); margin: 0; padding: 4px 0 2px; }
.nameplate-meta { display: flex; justify-content: center; align-items: baseline; gap: 16px; font-family: var(--sans); font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink); margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--rule); }
.nameplate-meta span { font-weight: 600; }
.nameplate-meta .sep { color: var(--rule-strong); font-weight: 400; }
.mast { padding-bottom: 22px; margin-bottom: 36px; border-bottom: 1px solid var(--rule-strong); }
.mast-kicker { display: flex; align-items: center; gap: 10px; font-size: 10px; letter-spacing: 0.26em; text-transform: uppercase; margin-bottom: 18px; font-family: var(--sans); }
.mast-flag { width: 9px; height: 9px; background: var(--kicker); flex: 0 0 9px; }
.mast-section { font-weight: 700; color: var(--ink); }
.mast-section-sep { color: var(--rule-strong); margin: 0 2px; font-weight: 400; letter-spacing: 0; }
.mast-aud { margin-left: auto; color: var(--mute); font-weight: 600; letter-spacing: 0.18em; }
.mast-title { font-family: var(--serif); font-weight: 700; font-size: 48px; line-height: 1.04; letter-spacing: -0.012em; color: var(--ink); margin: 0 0 14px; max-width: 17ch; }
.mast-dek { font-family: var(--serif); font-style: italic; font-size: 19px; line-height: 1.42; color: var(--ink); margin: 0 0 22px; max-width: 50ch; font-weight: 400; }
.mast-byline { font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--mute); margin: 0; padding-top: 14px; border-top: 1px solid var(--rule); line-height: 1.6; font-family: var(--sans); }
.mast-byline strong { color: var(--ink); font-weight: 700; letter-spacing: 0.16em; }
.mast-byline-sep { color: var(--rule-strong); margin: 0 8px; }
.callouts { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 1px solid var(--ink); margin: 0 0 44px; }
.callout { padding: 18px 20px 18px 22px; background: var(--paper); position: relative; }
.callout-pos { background: var(--pos-fill); }
.callout-neg { background: var(--neg-fill); border-left: 1px solid var(--ink); }
.callout-label { display: flex; align-items: center; gap: 9px; font-size: 10px; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; margin-bottom: 10px; font-family: var(--sans); }
.callout-pos .callout-label { color: var(--pos); }
.callout-neg .callout-label { color: var(--neg); }
.callout-label::before { content: ""; width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.callout-pos .callout-label::before { background: var(--pos); }
.callout-neg .callout-label::before { background: var(--neg); }
.callout-names { list-style: none; margin: 0; padding: 0; font-family: var(--serif); font-size: 18px; line-height: 1.4; color: var(--ink); font-weight: 600; }
.callout-names li { display: inline; }
.callout-names li:not(:last-child)::after { content: " · "; color: var(--rule-strong); margin: 0 1px; font-weight: 400; }
.callout-names em { font-family: var(--sans); font-style: normal; font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--mute); margin-left: 4px; vertical-align: 1px; font-weight: 600; }
.sec { margin: 40px 0 0; }
.sec-head { display: flex; justify-content: space-between; align-items: center; font-size: 10.5px; font-weight: 700; letter-spacing: 0.24em; text-transform: uppercase; color: var(--ink); margin: 0 0 14px; padding-bottom: 8px; border-bottom: 1.5px solid var(--ink); font-family: var(--sans); }
.sec-head-l { display: inline-flex; align-items: center; gap: 11px; }
.sec-mark { width: 9px; height: 9px; background: var(--ink); display: inline-block; flex: 0 0 9px; }
.sec-head em { font-style: italic; font-weight: 400; letter-spacing: 0.04em; text-transform: none; color: var(--mute); font-family: var(--serif); font-size: 13px; }
.chart { margin: 0 0 36px; }
.chart-svg { display: block; width: 100%; height: auto; }
.chart-cap { margin: 14px 0 0; padding: 12px 4px 0; border-top: 1px solid var(--rule); }
.chart-cap p { font-family: var(--serif); font-style: italic; font-size: 13px; line-height: 1.6; color: var(--mute); margin: 0 0 8px; }
.chart-cap p:last-child { margin-bottom: 0; }
.chart-cap b { font-style: normal; font-family: var(--sans); font-weight: 700; font-size: 9.5px; letter-spacing: 0.20em; text-transform: uppercase; color: var(--ink); margin-right: 8px; padding-right: 9px; border-right: 1px solid var(--rule-strong); }
.rollup-row { display: grid; grid-template-columns: 1fr auto auto auto; gap: 22px; align-items: baseline; padding: 13px 4px; border-bottom: 1px solid var(--rule); }
.rollup-row:last-child { border-bottom: 1px solid var(--rule-strong); }
.rollup-mgr { font-family: var(--serif); font-size: 17px; color: var(--ink); font-weight: 600; }
.rollup-mgr small { font-family: var(--sans); font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--mute); margin-left: 10px; font-weight: 600; }
.rollup-stat { display: flex; align-items: baseline; gap: 8px; justify-content: flex-end; white-space: nowrap; }
.rollup-stat-key { font-size: 9.5px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--mute); font-weight: 600; font-family: var(--sans); }
.rollup-stat-val { font-family: var(--sans); font-variant-numeric: tabular-nums; font-size: 15px; color: var(--ink); font-weight: 700; text-align: right; }
.rollup-stat-val.pos { color: var(--pos); }
.rollup-stat-val.neg { color: var(--neg); }
.rollup-stat-val small { font-family: var(--sans); font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--mute); font-weight: 600; margin-left: 3px; }
table { width: 100%; border-collapse: collapse; font-family: var(--sans); }
thead th { text-align: left; font-size: 9.5px; font-weight: 700; letter-spacing: 0.20em; text-transform: uppercase; color: var(--mute); padding: 10px 8px 8px; border-bottom: 1px solid var(--rule-strong); }
thead th.num { text-align: right; }
tbody td { padding: 10px 8px; border-bottom: 1px solid var(--rule); color: var(--body); vertical-align: baseline; }
tbody tr:last-child td { border-bottom: 1px solid var(--rule-strong); }
td.num { text-align: right; font-family: var(--sans); font-variant-numeric: tabular-nums; font-size: 13.5px; font-weight: 600; }
td.name { font-family: var(--serif); font-size: 16px; color: var(--ink); font-weight: 600; }
td.name::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 9px; vertical-align: 2px; background: var(--rule-strong); }
tr.in-pos td.name::before { background: var(--pos); }
tr.in-neg td.name::before { background: var(--neg); }
tr.in-pos { background: var(--pos-fill); }
tr.in-neg { background: var(--neg-fill); }
tr.is-mgr td.name::after { content: " mgr"; font-family: var(--sans); font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--mute); font-weight: 700; margin-left: 6px; vertical-align: 1px; }
td.lvl { font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--mute); font-weight: 600; white-space: nowrap; }
td.lvl .role { font-weight: 700; color: var(--ink); margin-left: 4px; letter-spacing: 0.18em; }
td.mgr { font-size: 13px; color: var(--mute); }
td.init { font-family: var(--serif); font-size: 13.5px; color: var(--ink); font-weight: 600; }
td.init small { font-family: var(--sans); font-variant-numeric: tabular-nums; font-size: 10.5px; letter-spacing: 0.04em; color: var(--mute); margin-left: 6px; font-weight: 500; }
td.init em { font-family: var(--serif); font-style: italic; color: var(--mute); font-weight: 400; }
td.stack { font-size: 10px; letter-spacing: 0.10em; text-transform: lowercase; color: var(--mute); font-weight: 600; }
td.stack small { font-family: var(--sans); font-variant-numeric: tabular-nums; font-size: 9px; letter-spacing: 0; color: var(--mute); margin-left: 3px; font-weight: 500; }
td.stack em { font-family: var(--serif); font-style: italic; color: var(--mute); font-weight: 400; text-transform: none; letter-spacing: 0; }
.pos { color: var(--pos); font-weight: 700; }
.neg { color: var(--neg); font-weight: 700; }
.briefs { margin-top: 64px; }
.briefs-head { text-align: center; border-top: 4px solid var(--ink); padding: 24px 0 0; margin-bottom: 32px; position: relative; }
.briefs-head::before { content: ""; position: absolute; top: -7px; left: 0; right: 0; border-top: 1px solid var(--ink); }
.briefs-head h2 { font-family: var(--blackletter); font-weight: 700; font-size: 38px; line-height: 1; letter-spacing: 0.005em; color: var(--ink); margin: 0 0 8px; }
.briefs-head p { font-family: var(--serif); font-style: italic; font-size: 14px; color: var(--mute); margin: 0; }
.brief { padding-top: 32px; margin-top: 40px; border-top: 1px solid var(--rule-strong); page-break-before: always; }
.brief:first-of-type { border-top: 0; padding-top: 0; margin-top: 0; page-break-before: auto; }
.brief-name { font-family: var(--serif); font-weight: 700; font-size: 32px; line-height: 1.04; letter-spacing: -0.012em; color: var(--ink); margin: 0 0 6px; }
.brief-meta { font-family: var(--sans); font-size: 10.5px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--mute); margin: 0 0 22px; font-weight: 600; }
.brief-person { padding: 14px 0 16px; border-bottom: 1px solid var(--rule); }
.brief-person:last-child { border-bottom: 0; }
.brief-person-lead { background: var(--paper-deep); padding: 16px 16px 14px; margin: 4px -16px 12px; border-top: 1px solid var(--rule-strong); border-bottom: 1px solid var(--rule-strong); }
.brief-person h3 { font-family: var(--serif); font-weight: 700; font-size: 18px; line-height: 1.3; color: var(--ink); margin: 0 0 6px; letter-spacing: -0.005em; }
.brief-person h3 em { font-style: normal; font-family: var(--sans); font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--mute); margin-left: 8px; font-weight: 600; vertical-align: 1px; }
.brief-person-owns { font-family: var(--serif); font-size: 13px; line-height: 1.5; color: var(--mute); margin: 0 0 8px; padding: 0; font-style: italic; }
.brief-person-owns em { font-family: var(--sans); font-style: normal; font-size: 9px; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink); margin-right: 8px; padding: 1px 6px; background: var(--paper-deep); border: 1px solid var(--rule); vertical-align: 1px; }
.brief-person-summary { font-family: var(--serif); font-size: 15.5px; line-height: 1.55; color: var(--body); margin: 0 0 8px; }
.brief-person-bullets { font-family: var(--serif); font-size: 14.5px; line-height: 1.55; color: var(--body); margin: 0; padding: 0; list-style: none; }
.brief-person-bullets li { margin: 0 0 5px; padding-left: 14px; position: relative; }
.brief-person-bullets li::before { content: ""; position: absolute; left: 0; top: 0.7em; width: 5px; height: 1px; background: var(--ink); }
.brief-person-bullets li:last-child { margin-bottom: 0; }
.brief-person-bullets strong { font-weight: 700; color: var(--ink); }
.colophon { margin-top: 60px; padding-top: 20px; border-top: 3px double var(--ink); }
.colophon-head { display: flex; align-items: center; gap: 11px; font-size: 10.5px; font-weight: 700; letter-spacing: 0.24em; text-transform: uppercase; color: var(--ink); margin: 0 0 16px; font-family: var(--sans); }
.colophon-body { font-family: var(--serif); font-size: 14.5px; line-height: 1.65; color: var(--body); margin: 0 0 14px; }
.colophon-body::after { content: " ■"; color: var(--ink); margin-left: 4px; font-size: 11px; vertical-align: 1px; }
.colophon-body em { font-style: italic; }
.dropcap { font-family: var(--serif); float: left; font-size: 52px; font-weight: 700; line-height: 0.86; margin: 4px 8px -2px 0; color: var(--ink); }
.colophon-warn { font-family: var(--serif); font-style: italic; font-size: 13px; color: var(--neg); margin: 0; padding: 8px 0 0 14px; border-left: 2px solid var(--neg); }
@media print { body { background: white; color: var(--ink); } main { padding: 24px; max-width: 100%; } .callouts { break-inside: avoid; } .chart { break-inside: avoid; } }
@media (max-width: 620px) {
  main { padding: 24px 18px 60px; }
  .nameplate-name { font-size: 54px; }
  .mast-title { font-size: 32px; max-width: 100%; }
  .mast-dek { font-size: 16px; }
  .mast-aud { display: none; }
  .callouts { grid-template-columns: 1fr; }
  .callout-neg { border-left: 0; border-top: 1px solid var(--ink); }
  .rollup-row { grid-template-columns: 1fr; gap: 6px; }
  .rollup-stat { justify-content: flex-start; }
  thead th, tbody td { padding: 8px 5px; }
  td.mgr { font-size: 12px; }
  td.stack { display: none; }
  .callout-names { font-size: 16px; }
  .dropcap { font-size: 42px; }
}"""


@dataclass
class IndexEntry:
    filename: str
    month_label: str
    since_iso: str
    until_iso: str
    contributor_count: int
    locked_in_count: int
    not_locked_in_count: int


def render_index(
    entries: list[IndexEntry],
    org_name: str,
    generated_iso: str,
) -> str:
    rows: list[str] = []
    for entry in entries:
        rows.append(
            f'<li class="idx-row">'
            f'<a class="idx-link" href="{_html(entry.filename)}">'
            f'<span class="idx-month">{_html(entry.month_label)}</span>'
            f'<span class="idx-range">{_html(_range_label(entry.since_iso, entry.until_iso))}</span>'
            f'<span class="idx-stats">'
            f'<span class="idx-stat"><b>{entry.contributor_count}</b> contributors</span>'
            f'<span class="idx-stat pos"><b>{entry.locked_in_count}</b> locked in</span>'
            f'<span class="idx-stat neg"><b>{entry.not_locked_in_count}</b> not locked in</span>'
            f'</span>'
            f'</a></li>'
        )
    generated_dt = datetime.fromisoformat(generated_iso.replace("Z", "+00:00"))
    generated_human = generated_dt.strftime("%B %-d, %Y")
    return _INDEX_PAGE.format(
        css=_CSS + _INDEX_CSS,
        org_name=_html(org_name),
        generated=_html(generated_human),
        rows="\n".join(rows),
        report_count=len(entries),
    )


def _range_label(since_iso: str, until_iso: str) -> str:
    s = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    u = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
    return f"{s.strftime('%b %-d')} – {u.strftime('%b %-d, %Y')}"


_INDEX_CSS = """
.idx-list { list-style: none; padding: 0; margin: 32px 0; border-top: 1px solid var(--ink); }
.idx-row { border-bottom: 1px solid var(--rule); }
.idx-link {
  display: grid;
  grid-template-columns: 1.5fr 1fr 2fr;
  gap: 16px;
  align-items: baseline;
  padding: 18px 4px;
  text-decoration: none;
  color: var(--ink);
}
.idx-link:hover { background: var(--paper-deep); }
.idx-month { font-family: var(--serif); font-size: 26px; font-weight: 600; letter-spacing: -0.01em; }
.idx-range { font-family: var(--serif); font-style: italic; font-size: 14px; color: var(--mute); }
.idx-stats { display: flex; gap: 18px; justify-content: flex-end; font-family: var(--sans); font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }
.idx-stat b { font-family: var(--sans); font-size: 16px; font-weight: 700; margin-right: 4px; letter-spacing: 0; text-transform: none; }
.idx-stat.pos b { color: var(--pos); }
.idx-stat.neg b { color: var(--neg); }
@media (max-width: 700px) {
  .idx-link { grid-template-columns: 1fr; gap: 4px; }
  .idx-stats { justify-content: flex-start; flex-wrap: wrap; }
}
"""


_INDEX_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Werkschau · Monthly Index</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=UnifrakturCook:wght@700&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400;1,600&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<main>
  <div class="nameplate">
    <h1 class="nameplate-name">Werkschau</h1>
    <div class="nameplate-meta">
      <span>Monthly Archive</span><span class="sep">·</span>
      <span>{org_name}</span><span class="sep">·</span>
      <span>Generated {generated}</span>
    </div>
  </div>

  <header class="mast">
    <h2 class="mast-title">Monthly retrospective archive.</h2>
    <p class="mast-dek">{report_count} complete calendar months of engineering activity. Select a month to read its full report.</p>
  </header>

  <ul class="idx-list">{rows}</ul>
</main>
</body>
</html>"""


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Engineering Org Snapshot · Werkschau</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=UnifrakturCook:wght@700&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400;1,600&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<main>

  <div class="nameplate">
    <h1 class="nameplate-name">Werkschau</h1>
    <div class="nameplate-meta">{nameplate_meta}</div>
  </div>

  <header class="mast">
    <div class="mast-kicker">
      <span class="mast-flag" aria-hidden="true"></span>
      <span class="mast-section">Engineering</span>
      <span class="mast-section-sep">/</span>
      <span class="mast-section">Weekly Analysis</span>
      <span class="mast-aud">{kicker_aud}</span>
    </div>
    <h2 class="mast-title">{title}</h2>
    <p class="mast-dek">{dek}</p>
    <p class="mast-byline">{byline}</p>
  </header>

  <section class="callouts" aria-label="Headline call-outs">{callouts}</section>

  <figure class="chart">
    {chart}
    <figcaption class="chart-cap">
      <p><b>Note</b>Output is the log-ratio of complexity-weighted, file-kind-weighted commit minutes to a 600 minute / week reference. Focus is breadth across <em>initiative clusters</em> (commits sharing a scope, token, or top-level directory within 48 hours): a single coherent change spanning many repos counts as one initiative and lands on the left; multiple distinct initiatives land on the right. Top-right (lots of code, many initiatives) is "locked in"; bottom-left (little code, single initiative) is "not locked in".</p>
    </figcaption>
  </figure>

  <section class="sec">
    <h2 class="sec-head"><span class="sec-head-l"><span class="sec-mark" aria-hidden="true"></span>Manager rollup</span> <em>team totals across direct reports</em></h2>
    {rollup}
  </section>

  <section class="sec">
    <h2 class="sec-head"><span class="sec-head-l"><span class="sec-mark" aria-hidden="true"></span>Per-contributor ledger</span></h2>
    <table>
      <thead><tr><th>Contributor</th><th>Manager</th><th>Role</th><th>Top initiative</th><th>LOC by language</th><th class="num">Est. minutes</th><th class="num">Commits</th></tr></thead>
      <tbody>{ledger}</tbody>
    </table>
  </section>

  {briefs_section}

  <aside class="colophon">
    <h2 class="colophon-head"><span class="sec-mark" aria-hidden="true"></span>About this report</h2>
    <p class="colophon-body">{about}</p>
    <p class="colophon-warn">Not intended as a primary input to performance-management decisions.</p>
  </aside>

</main>
</body>
</html>"""
