1. Pop info pages should list notable mortals who are members, in the same style as how they are listed on the Universe tab.
2. After messing with it some, I have decided that the way tabs open in the current UI is more confusing than helpful. Instead, I would like only new tabs to be opened when a link is clicked from either the left panel's tabs or from the Universe tabs. When you click a link and you're already in an info tab, the page you jump to just opens in the same tab you are in. (None of this applies to Domains, of course, since their content always opens in the Divine Wisdom tab.)
3. As an addendum to the above, I would like for links to Luminary info pages to open in the Luminaries tab, with a breadcrumb leading back to the main Luminaries tab page.
4. I would like for dev mode to show the original Proxius Goal (with the increased detail) in a Proxius's notable mortal info page. For reference, here is the code in `ui/detail_renderers.py` before it was changed:

```python
# ─────────────────────────────────────────
# MORTAL  (works for both notable mortals and Proxiī)
# ─────────────────────────────────────────

def render_mortal_detail(state: "SimulationState", mortal_id: str) -> Text:
    m = state.mortals.get(str(mortal_id))
    if not m:
        return _not_found(f"Mortal {mortal_id}")

    lines: list[str] = []
    a = lines.append

    role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
    status_str = m.status.value.upper()

    a(f"[bold #4a80b0]MORTAL: {_e(m.name)}[/]")
    a("")
    a(f"  \\[{role_str}]   status: \\[{status_str}]")
    a(f"  alignment: {m.alignment:+.2f}")
    age_str = f"age:{m.chrono_age:.0f}"
    if m.bio_age != m.chrono_age:
        age_str += f"  (bio:{m.bio_age:.0f})"
    a(f"  {age_str}")
    if m.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {m.visibility:.2f}")
    a(f"  {_e(_prominence_label(m))}")

    sp_obj = state.species.get(str(m.species_id)) if m.species_id else None
    if sp_obj:
        sp_md = _maybe_gold("species", str(sp_obj.id), f"[#3a6a8a]{_e(sp_obj.name)}[/]")
        a(f"  species: {sp_md}")

    dev = display.DEV_MODE

    def _gated(entity, line_markup: str) -> None:
        """Emit a line only if the referenced entity is in the Window
        (or always, when running with --dev — dimmed if OOW)."""
        if entity is None:
            return
        oow = not is_in_window(entity)
        if oow and not dev:
            return
        if oow:
            a(f"  [dim]{line_markup}[/dim]")
        else:
            a(f"  {line_markup}")

    loc = state.locations.get(str(m.current_location)) if m.current_location else None
    if loc:
        loc_link = _location_link(state, m.current_location, f"[#3a6a8a]{_e(loc.name)}[/]")
        _gated(loc, f"location: {loc_link}")

    home = state.locations.get(str(m.home_location)) if m.home_location else None
    if home and (not loc or str(home.id) != str(loc.id)):
        home_link = _location_link(state, m.home_location, f"[#3a6a8a]{_e(home.name)}[/]")
        _gated(home, f"origin:   {home_link}")

    civ = state.civilizations.get(str(m.civilization_id)) if m.civilization_id else None
    if civ:
        civ_link = _click_link("civ", str(m.civilization_id), f"[#3a6a8a]{_e(civ.name)}[/]")
        _gated(civ, f"civilization: {civ_link}")

    pop = state.pops.get(str(m.pop_id)) if m.pop_id else None
    if pop:
        stratum = pop.stratum.title() if pop.stratum else "Pop"
        sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
        pop_md = _maybe_gold("pop", str(pop.id), f"[#3a6a8a]{_e(stratum)}[/]")
        if sp_obj:
            sp_md = _maybe_gold("species", str(sp_obj.id), _e(sp_obj.name))
            _gated(pop, f"pop:      {pop_md} ({sp_md})  sz:{pop.size_magnitude}")
        else:
            _gated(pop, f"pop:      {pop_md}  sz:{pop.size_magnitude}")

    if m.status_tags or m.personal_tags or m.belief_tags or m.culture_tags:
        a("")
    if m.status_tags:
        a(f"  status:  {_e(', '.join(_short_tag(t) for t in m.status_tags))}")
    if m.personal_tags:
        a(f"  tags:    {_e(', '.join(_short_tag(t) for t in m.personal_tags))}")
    if m.belief_tags:
        a(f"  beliefs: {_format_beliefs_markup(m.belief_tags)}")
    if m.culture_tags:
        a(f"  culture: {_format_culture_markup(m.culture_tags)}")

    if m.role == MortalRole.PROXIUS:
        a("")
        a("[bold #4a80b0]PROXIUS GOAL[/]")
        if m.active_goal:
            g = m.active_goal
            if g.label:
                a(f"  directive: {_e(g.label)}")
            if g.last_action is not None:
                a(f"  last action: [#a0d080]{_e(g.last_action.value.replace('_', ' '))}[/]")
            else:
                a(f"  last action: [#5a7090](not yet acted)[/]")
            if g.imago_node_id:
                from utilities.imago_registry import get_registry as get_imago_registry
                ireg = get_imago_registry()
                node = ireg.get_node(g.imago_node_id)
                imago_label = node.name if node else g.imago_node_id
                a(f"  imago: [#a0b8d0]{_e(imago_label)}[/]")
            if g.target_civilization_id:
                civ = state.civilizations.get(str(g.target_civilization_id))
                if civ:
                    civ_link = _click_link(
                        "civ", str(g.target_civilization_id),
                        f"[#3a6a8a]{_e(civ.name)}[/]",
                    )
                    a(f"  target civilization: {civ_link}")
            if g.source_pop_id:
                src = state.pops.get(str(g.source_pop_id))
                if src:
                    label = src.stratum.title() if src.stratum else "Pop"
                    a(f"  source pop: [#3a6a8a]{_e(label)}[/]  sz:{src.size_magnitude}")
            if g.goal_pop_id:
                gp = state.pops.get(str(g.goal_pop_id))
                if gp:
                    label = gp.stratum.title() if gp.stratum else "Pop"
                    a(f"  goal pop:   [#3a6a8a]{_e(label)}[/]  sz:{gp.size_magnitude}")
            if g.research_domain:
                a(f"  researching: {_e(_short_tag(g.research_domain))}")
            if g.petition_pending:
                a(f"  [#c09030]petition pending ({g.petition_pending_ticks}/5 ticks)[/]")
        else:
            a("  [#5a7090](idle — no active directive)[/]")

    return Text.from_markup("\n".join(lines))
```