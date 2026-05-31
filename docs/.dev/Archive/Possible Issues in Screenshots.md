This document is a list of game screenshots showing various things, some of which are merely UI errors, some of which point to deeper errors in the code/database, and others which merely call for an investigation into the possible underlying mechanics.

### Item A

![[civ_detail_pops_one_line.png]]

The Civilization detail page lists each Pop in this two-line format that gets rather unwieldy when there are many Pops. It would be best if each entry were a single line, listing the top four Domain affinities and including a "(+X more)" message at the end, much like how Pops are displayed on the main Universe tab. (There is also an additional error here that I believe lies in how Domain affinities for these particular Pops are stored in the database, but we'll get to that soon.)

### Item B

![[linked_pop_details.png]]

The linked Pops entries on a Pop detail page is too sparse. Their entries ought to be constructed much like my proposal in Item A and sorted by location (much like how the Civilization detail page in Item A already does).

### Items C-1, C-2, and C-3

![[mortal_pop_detail_domain_split_error.png]]

![[mortal_pop_detail_domain_split_error2.png]]

Note how, in the above two screenshots, some Domain names are in lowercase while others are capitalized. The capitalized versions function as proper links to the Divine Wisdom tab, which is what is desired. The ones that are lowercase and **not** links lead me to believe that the recently redone Naran Pops and NotableMortals do not have their Domain affinities stored in data properly; rather than the desired format of, for example, `domain:order`, it is likely that they are stored merely as `order`. All of these fields should be changed to conform to the former scheme.

![[mortal_pop_detail_domain_split_error3.png]]

Here you can see that the Civilization and Pops on Oros all have their Domain affinities displaying properly, capitalized and as links. This shows that their fields are formatted correctly.

### Item D

![[pinned_mortal_narrative.png]]

There are two issues here:

1. The text "the local community" **should** instead be a list of the actual Pop that the mortal is carrying out this action among, if that Pop is in the Window (which, at the time, was Vail's Crew which **was** in the Window). When that Pop is outside of the Window, this is perfectly fall-back text.
2. Durenn Vail **was not** pinned when these entries popped into the Log. It could have been just because we have been pushing Durenn Vail's activities to the Log whether he is pinned or not for playtesting purposes, but I happen to know that the code for pinning an entity is a bit suspect anyway. We should do an audit of the pinning code and its implications.

### Item E

![[Pop_splinter_narrative.png]]

One minor UI issue here and another major code issue:

1. The text "A faction" should be the name and link of the new Pop that has resulted from the splinter. The text "'s (Stratum) class" should be the name and link of the original Pop that underwent the splinter. Of course, both of these should only be true if the original Pop is in the Window; if not, this message shouldn't be pushed to the Log anyway except in Dev mode. Also, the Domain name should be capitalized and link to its page in the Divine Wisdom tab, but I suspect that this is due to the earlier database error we have already discussed.
2. Pop splinters have become **way** too common and seem to happen quite easily. Since we have revised all the Naran Pops to be a bit more varied, we may want to tweak the Pop splinter code to be quite a bit more forgiving in how divergence is measured. Perhaps it should also have a waiting period before it actually "fires off"?

### Item F

![[scry_increase_vis_only.png]]

You can see here that the scry action on Oros was successful but nothing was pushed to the Log. I believe this is because we stopped reporting to the Log when entities that are already in the Window have had their visibility scores increased. That was a good idea, since it was taking up a lot of room in the Log to list out every single entity that got a visibility boost, when keeping track of that is not very relevant information for the player. However, it seems here that the scry action revealed nothing new and **only** increased visibility of entities that are already in the Window, which is something that I think deserves a Log mention so that a player might understand why a "successful scry" seemingly did nothing. In this exact case, we can simply report something like `[SUCCESS] Scry of (Location) refreshed visibility but did not reveal anything new.`

### Item G

![[scry_narrative.png]]

Two things here:

1. The "Pod" text here leads to an error page, since this isn't a civilization that exists but a "wild civilization." Perhaps, when a Pop belongs to a "wild civilization" like this and is spotted by scrying or mortal influence splash or whatever, the nomenclature should be "(Species) (Pop) Pop" rather than "(Civilization) (Pop) (Pop)."
2. Since we have added occupations, it might be a good idea to update our Log narratives to follow the same naming convention for Pops as elsewhere, i.e., `name` if the Pop has an explicit name, `occupation` if it doesn't have an explicit name but has an occupation, `stratum` (or `social_class` or whatever the code actually calls it) if the Pop has neither.

### Item H

![[sell_where_narrative.png]]

Simple change: it might be nice for this particular Log narrative to state **where** the pinned mortal has performed this action.

### Item I

![[whisper_narrative_in_travel_loc_results.png]]

This is less of an error and more an observation—and something I'm curious enough to do an audit on.

I sent a Whisper to Durenn Vail while he was in transit between Neran and Sethis. At the time, I had no visibility on almost everything on Sethis, and this Whisper had a "visibility splash" that revealed these Pops in his destination. That actually may be **good**.

1. It seemed like, other than the visibility splash, there wasn't also an influence splash on these Pops. We can check the code to see if that is the case; if so, that is good. The only Pop that should have been affected by the actual influence effect should be Vail's Crew in this circumstance.
2. It may be that the code is running the visibility splash logic as if Durenn Vail is simultaneously in Sethis Surface **and** Neran Surface (or perhaps it only counted him as on Sethis Surface, which was his destination). This is fine, but we may want to capture this particular case and limit the effectiveness of this visibility splash (if it is **only** that the code saw him as on Sethis Surface, we may need to work out a way to have that visibility splash go back to his origin, as well).

### Item J

![[whisper_visibility.png]]

I had opened the Whisper action config modal while Durenn Vail was away from Neran, at a time when I had **nothing** about Sethis in my Window. I think it is fine to be able to select and target a mortal while they are in a location unknown to you (because that could be an interesting way to find new places outside of scrying), but our mortal pickers should **not** explicitly list out places outside of the Window. When the true location is not known, perhaps the mortal's entry on this modal should list the location of their parent Pop. (Because we don't want to hint to the player that they're outside of the Window until they have performed the action targeting them and see the visibility splash.)