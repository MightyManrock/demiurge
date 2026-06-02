### Whisper to Mortal

1. When you mouse over either a Domain selection button or an Imāgō node when either is already selected, the label above each section should be "sticky," i.e., it will change to what you mouse over **while** you are mousing over it, but it should change back to what is currently selected when the mouse cursor has moved away.
2. When you have selected either a Domain or an Imāgō (whether you have done so by hitting tab on the keyboard or left-clicking it), the button or node should stay visibly selected (i.e., it retains the "active" CSS).
3. When interacting with the configuration modal with a mouse, the click to choose an Imāgō should **not** advance. Only an input of enter (either when the Imāgō section is focused or on the continue button, both of which are current behavior) or an explicit click on the continue button should advance to the confirmation modal.

## Shape Dream

1. As #1 under Whisper to Mortal, but it seems that this mouse-over of an Imāgō node actually **does** select it. This should not happen; only an explicit mouse click will select an Imāgō.
2. Just as #2 in Whisper to Mortal, applying to both tabs of Domains and Imāgō nodes.
3. Just as #3 in Whisper to Mortal; the fact that you have to select **two** pairs of Domains and Imāgō nodes is accounted for.

## Explore Beliefs

1. Similar to #1 under Whisper to Mortal, the chosen Domain will be "sticky" as you mouse over other Domain buttons. The Imāgō Tree preview shown in the right panel should also be "sticky" in this way; it will show you other Domains' trees as you mouse over them, but will "snap back" to the one for the selected Domain when the mouse cursor has moved away.
2. Just as #2 under Whisper to Mortal but only applying to Domain buttons, since that's all you're choosing outside of the auto-stop options.

### Explore Beliefs Log Narrative

These changes may require additions to our narrative link formatting/sentinel logic.

[[explore_beliefs_narrative_fix1.png]]

* This particular narrative should have the Domain name (here, "Change") formatted as a link to the Domain's Divine Wisdom page.

[[explore_beliefs_narrative_fix2.png]]

* These two narratives have the same problem: the Domain name (here, again, "Change") should be formatted as a link to the Domain's Divine Wisdom page.
* (Technically this applies to Reveal Imāgō and not Explore Beliefs, but since they are in the same screenshot, I will include this here.) In the second narrative, the name of the Imāgō that has been revealed (here, "The Crumbling Wall") should be formatted as a link to the Imāgō's Divine Wisdom page.

## Reveal Imāgō

1. Similar to #1 under Explore Beliefs: sticky Domain buttons. This modal actually **doesn't** show you other Imāgō trees for other Domains as you mouse-over the other, unselected Domain buttons; it **should** do this, but "snap back" to the one that is selected once the mouse cursor is not over a Domain button.
2. The #2 of previous modals discussed actually **does** work the desired way here—no changes necessary with selected Domains or selected Imāgō nodes staying "visibly selected" here.
3. The #3 of previous modals discussed works exactly as I have in mind here, as well: the modal does not advance to the confirmation screen when a valid Imāgō node is clicked, so no changes in this vein are necessary.
4. Pressing enter while keyboarding over a valid Imāgō node selection only selects the node and does not advance to the confirmation modal, which is what it should do.
5. Tabbing from the cancel button does not move the selection to the continue button properly when the continue button is selectable.

## Change Affiliated Domain

1. Keyboard navigation of the top "Domain to change" section does not seem to function; left and right arrows should move between the options (and, if moving right from the third option or left from the first option, the "tease" fourth option should be skipped).
2. Up and down navigation in the "Domain to substitute" section does not seem to work properly; the unselectable Domains (i.e., the ones you are already affiliated with) seem to be accounted for strangely in the navigation logic. This is interesting because the **old** Domain selection modals (before any of the action redesign) functioned perfectly well when certain Domains were unable to be selected. Perhaps look at those for reference for how this can be fixed.
3. As #1 in several other previous modals, the buttons in both the "Domain to change" section above and the "Domain to be substituted" section below should be "sticky," and mouse-over should not change your actual selection.
4. As #2 in several other previous modals, selected Domains in either section should stay visibly selected.
5. It seems, when using keyboard input, that pressing tab does not properly select at least the "Domain to change" but perhaps both. Tabbing out of a section should select whatever is active there.
6. Like Reveal Imāgō, clicking does not advance to the confirmation modal, which is proper behavior—no fix necessary.
7. Unfortunately, also like Reveal Imāgō, pressing enter while keyboarding over the final selection (i.e., the "Domain to substitute") does not advance to the confirmation modal, which, again, is what it should do.