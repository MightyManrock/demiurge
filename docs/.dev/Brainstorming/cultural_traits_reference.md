# Cultural Traits Reference

Cultural traits describe the character of a Pop, civilization, or mortal — what they believe, what they value, and what they do. They are distinct from Domain beliefs, which describe metaphysical orientation toward the sixteen Domains.

All trait values are floats. For Pops and civilizations, values are always positive (0.0–1.0), representing prevalence within the group. For individual mortals, certain traits may take negative values, representing an active opposing orientation rather than mere absence.

**Mutual exclusivity (mortals only):** Certain religion traits suppress one another above threshold values in individual mortals. A coherent personal worldview cannot simultaneously hold, for example, high `luminary_worship` and high `maltheism`. In Pops, contradictory trait pairs coexist and represent demographic diversity — often a signal of internal tension or potential splintering.

---

## Religion Traits (`religion:`)

Religion traits describe a mortal's or Pop's orientation toward the divine and spiritual. They are stored as positive values only; the "negative" of a religion trait is represented by a separate named trait rather than a sign flip, because opposed religious stances are qualitatively distinct worldviews rather than mirror images.

| Trait | Meaning |
|---|---|
| `religion:ancestor_worship` | Veneration of forebears; the dead remain active participants in community life through memory, ritual, and intercession |
| `religion:animism` | Spiritual presence in natural objects, places, and phenomena; the world is alive with non-sapient agency |
| `religion:luminary_worship` | Active reverence for the Luminaries; recognition of divine beings with legitimate authority over mortal reality |
| `religion:demiurge_worship` | Recognition and reverence directed specifically at the Demiurge; a more intimate orientation than generalized luminary_worship |
| `religion:nontheism` | The belief that mortal endeavors need not involve divine beings; the divine may exist but is not meaningfully relevant to how life should be lived |
| `religion:maltheism` | Active hostility or resentment toward divine beings; the gods exist but are harmful, unjust, or otherwise to be opposed |
| `religion:void_worship` | Reverence directed toward dissolution, absence, and the Void; the divine is found in emptiness rather than presence |

**Mutual exclusivity notes:** `luminary_worship` and `maltheism` suppress one another at high values in individual mortals. `luminary_worship` and `nontheism` are compatible at low-to-moderate values (cultural participation without deep conviction) but suppress one another at high values. `demiurge_worship` and `maltheism` suppress one another.

---

## Values Traits (`values:`)

Values traits describe what a Pop, mortal, or civilization prizes — the ethical and social orientations that shape behavior and generate needs and desires. Where a trait is bipolar, the positive end names the trait; negative values describe the opposing cultural stance.

### Social Structure

| Trait | Positive meaning | Negative meaning |
|---|---|---|
| `values:hierarchy` | Rank distinctions are legitimate and should be respected — whether by birth, ordination, or nature | Active egalitarianism: rank distinctions are illegitimate and harmful |
| `values:meritocracy` | Position should be earned through demonstrated ability and effort | Negative + high hierarchy: rank is innate; mobility is dangerous or impossible. Negative + negative hierarchy: no achievement should elevate anyone above any other |
| `values:egalitarianism` | *Represented as negative `values:hierarchy`* | — |
| `values:solidarity` | Community bonds, mutual support, and shared identity are foundational values; what affects one affects all | Social atomism: each person is fundamentally alone and responsible only for themselves; community is illusion or constraint |
| `values:autonomy` | Individual freedom and self-determination are paramount | Collectivist self-erasure: individual preferences are selfishness; the group completely supersedes the person |
| `values:sedentism` | Attachment to place, stability, and rootedness are virtues; home is where meaning lives | Nomadism as positive value: attachment to place is stagnation; movement and rootlessness are freedom |
| `values:xenophilia` | Outsiders, foreign cultures, and the unfamiliar are interesting and valuable | Xenophobia: outsiders are threatening, corrupting, or inferior; cultural purity must be defended |

### Intellectual and Epistemic

| Trait | Positive meaning | Negative meaning |
|---|---|---|
| `values:erudition` | Formal learning, theoretical knowledge, and intellectual achievement are admired and sought | Anti-intellectualism: book learning is suspect; experts are out of touch or dangerous; theory is a distraction from real life |
| `values:folk_wisdom` | Traditional knowledge, accumulated practical wisdom, and cultural heritage are to be honored and preserved | Aggressive modernism: tradition is primitive baggage; everything old is an obstacle; cultural heritage is weight to be shed |
| `values:pragmatism` | What matters is what works; outcomes justify methods; flexibility is wisdom | Principled rigidity: pragmatic flexibility is moral compromise; principles must be held regardless of consequences, even unto martyrdom |
| `values:idealism` | Transcendent values, principles, and ideals are real and worth pursuing at personal cost | Cynicism/nihilism: principled stances are naive or manipulative; nothing has inherent value beyond immediate utility; ideals are lies |

### Character and Virtue

| Trait                 | Positive meaning                                                                                                                                            | Negative meaning                                                                                                                                                                         |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `values:honor`        | Following a personal or cultural code of conduct — keeping one's word, honoring commitments, and treating social contracts as genuinely binding.            | Shamelessness — complete disregard for social contract, oaths, and codes of conduct.                                                                                                     |
| `values:sincerity`    | Emotional authenticity is valued; saying what you genuinely feel is honest in the deepest sense, distinct from factual truth-telling                        | Performed presentation as cultural art: the social mask is not a lie but a craft; authentic emotional expression is crude or dangerous                                                   |
| `values:humility`     | Self-effacement and acknowledgment of one's limits are virtues; arrogance is a fault                                                                        | Pride as virtue: self-assertion and confidence are admirable; humility is weakness or dishonesty about one's worth                                                                       |
| `values:wit`          | Verbal cleverness, humor, and the ability to find levity in tense situations are admirable; being an interesting and engaging interlocutor is a social good | Active discouragement of sarcasm and irreverence: "don't be a smartass" as a cultural norm; cleverness in speech is seen as disrespectful or subversive, particularly toward authority   |
| `values:patience`     | Waiting, deliberating, and enduring discomfort before acting are virtues                                                                                    | Urgency as virtue: immediate action is decisive and strong; waiting is passivity or cowardice                                                                                            |
| `values:tenacity`     | Persistence in the face of difficulty is admirable; not giving up is a mark of character                                                                    | Graceful surrender is wisdom: knowing when to stop is intelligence; persistence beyond the right moment is stubbornness. At stronger negative: defeatism — accepting failure too readily |
| `values:adaptability` | Flexibility, openness to change, and adjusting to new circumstances are virtues                                                                             | Inflexibility as virtue: the established way must be defended against novelty; change is inherently corrupting                                                                           |

### Material and Social Orientation

| Trait               | Positive meaning                                                                                                                 | Negative meaning                                                                                                                 |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `values:indulgence` | Pleasure, comfort, and enjoyment of material goods are legitimate goods worth pursuing                                           | Asceticism: deprivation is spiritually or morally noble; pleasure-seeking is weakness or corruption                              |
| `values:moderation` | Restraint, balance, and avoiding excess are virtues                                                                              | Excess as commitment: restraint signals weakness or lack of conviction; intensity and going all-in are admired                   |
| `values:prosperity` | Wealth accumulation and material success are admirable and worth pursuing                                                        | Voluntary poverty as virtue: wealth is spiritually corrupting; material renunciation and simplicity are ideals                   |
| `values:charity`    | Generosity and giving to those with less are moral goods                                                                         | Principled self-sufficiency: charity enables weakness; accepting help is shameful; helping others undermines their development   |
| `values:prowess`    | The cultural valorization of skill, mastery, and excellence — being very good at something earns genuine admiration and respect. | Tall poppy syndrome — the active cultural suppression of visible excellence. Distinguishing oneself is threatening or offensive. |

---

## Practice Traits (`practice:`)

Practice traits describe cultural participation in specific activities — what a Pop produces and engages with, and how richly. They are distinct from values traits (which describe what is *prized*) and from mortal skill traits (which describe personal *capability*).

A high `practice:` value in a Pop means that activity is present, accessible, and performed with quality. A low value means the practice is rare or underdeveloped locally. Negative values represent active suppression of a practice — not mere absence but cultural or legal prohibition of it.

### Mortal skills

Individual mortals have parallel `skill:` traits describing their personal capability in these same domains. `practice:` and `skill:` are independent:

- A mortal with high `skill:music` but low personal preference is a professional musician who is jaded about their work.
- A mortal with no `skill:music` but strong personal preference is an enthusiastic audience member.
- A mortal without `skill:` in a practice can still seek it out to satisfy leisure desires — they are a consumer of culture, not a producer.

When a mortal's Agent evaluates how to satisfy a leisure desire, it considers both what activities it prefers and what `practice:` quality is available at nearby locations. A mortal may travel to seek out a higher-quality version of a practice they value even if the same practice exists locally at lower quality, weighted by their `values:xenophilia` and the travel cost.

### Arts and Performance

| Trait              | Positive meaning                                                                                                          | Negative meaning                                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `practice:music`   | Musical performance, composition, and communal musical culture are present and valued in daily life                       | Active suppression of music: musical performance is forbidden or stigmatized — common in certain religious reform movements or authoritarian political contexts |
| `practice:dance`   | Dance as cultural practice is present and participatory, from folk traditions to formal performance                       | Prohibition of dance: often religious or political — dance is seen as licentious, subversive, or spiritually dangerous                                          |
| `practice:visual`  | Painting, sculpture, decorative arts, and visual culture are produced and valued                                          | Iconoclasm: images are forbidden as idolatrous, dangerous, or politically subversive; visual art is actively suppressed or destroyed                            |
| `practice:theatre` | Dramatic performance, oral storytelling, and narrative performance traditions are alive in the culture                    | Theatre is seen as corrupting, immoral, or dangerous; performers are stigmatized; performance is prohibited or tightly restricted                               |
| `practice:lit`     | Written narrative, poetry, and textual culture are produced and circulated                                                | Active suppression of written culture: texts are burned, literacy is restricted, or writing is treated as a tool of oppression                                  |
| `practice:poetry`  | Poetic tradition — oral or written — is a living cultural form, distinct from prose literature in its status and practice | Poetry specifically is suppressed or dismissed as frivolous                                                                                                     |

### Craft

| Trait               | Positive meaning                                                                                                                       | Negative meaning                                                                                                                                |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `practice:crafts`   | Skilled making beyond pure utility — decorative, ceremonial, and aesthetic objects — is valued and practiced                           | Purely utilitarian culture: ornamentation is wasteful; objects should serve function only; skilled aesthetic making is seen as vain or decadent |
| `practice:culinary` | Food culture is a cultural practice in its own right — preparation, presentation, and communal eating are sites of cultural expression | Food is fuel only; elaborate preparation is wasteful or self-indulgent                                                                          |

### Physical and Ceremonial

| Trait                | Positive meaning                                                                                                                                                                                                                                           | Negative meaning                                                                                                                                                                                        |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `practice:athletics` | Physical competition, sport, and the cultivation of physical excellence are cultural practices                                                                                                                                                             | Athletic competition is frivolous or dangerous; physical prowess is irrelevant or discouraged                                                                                                           |
| `practice:combat`    | Martial arts, dueling, and ritualized combat are practiced as cultural forms distinct from actual warfare — a tradition of disciplined violence as art                                                                                                     | Ritualized combat is barbaric; the culture has moved beyond glorifying violence even in ceremonial form                                                                                                 |
| `practice:ritual`    | Secular ceremonial practice — rites of passage, civic ceremony, seasonal festivals — is present and meaningful                                                                                                                                             | Ceremony is superstition or waste; pragmatic culture has stripped communal life of ritual                                                                                                               |
| `practice:revelry`   | Social leisure as a cultural practice — communal feasting, public gathering for enjoyment, nightlife, celebration without specific artistic or athletic purpose. Spans from harvest feasts at tribal scale to urban entertainment culture at higher scales | Puritanical suppression of public social leisure: gathering for enjoyment is seen as morally dangerous, wasteful, or corrupting; the tavern is closed; communal celebration is forbidden or stigmatized |
