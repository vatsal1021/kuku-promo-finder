# Where the tool picks badly

Checked by reading the script lines of the top 20 and bottom 10 selected promos from the full run
(`raw_outputs/promos_ranked.json`, Gemini 3.8 Flash, 163 candidates, 93 selected), plus the lines just
before and after each cut. Timestamps are episode time, as in the screenplays. Script lines are not quoted
here because the screenplays are confidential; the episode and timestamp identify each line.

## Summary

The model's scores are usable: the bottom 10 really are the dullest clips (quiet cottage scenes, a guard
passing bread, villagers offering blankets), and the tool never cuts mid-line or off a shot boundary.
The problems are above that floor:

1. The hook scale does not separate a strong line from a strong image. 17 of the top 20 got a hook of 8 or 9, whether the first 3 seconds show a whip crack or a woman talking in bed.
2. Both stitched promos in the top 10 join moments that do not belong together, and the model did not notice.
3. Several "hooks" are replies to a line the viewer never hears.
4. The rules sometimes cut a few seconds before the real cliffhanger.
5. Some cue words in the rules match the wrong thing.
6. The same beat from episodes 1 and 2 is in the top 20 twice.

---

## 1. Hooks that are strong on paper, not on screen

**Rank 5, E009-A, episode 9, 00:05.50–00:54.00, hook 8.** The hook is a mother's plea for her feverish child (00:06.30). On screen that is a woman walking through a doorway carrying a bundle. The next 45 seconds are herbal first aid (consulting the herb book at 00:27–00:34, asking for hot water at 00:38) with no antagonist. Compare rank 13, E015-A (episode 15, 00:44.20–01:26.00), which opens on a thug shoving the heroine to the ground with her bandages bleeding (00:47.40) and got a hook of 7. The model gave the pleading line a higher hook score than the shove.

**Rank 5 also has a soft cliffhanger.** It ends on the mother asking why the remedy is not working (00:52.50). The next line, 0.3 seconds later, is Juliana telling her to wait, and by 00:58 the boy's fever breaks and the mother sobs with relief. The model gave this a cliffhanger of 9, the same as the branding iron at rank 3. The stakes are a fever, not a villain. This clip should not be in the top 10.

**Rank 10, E050-A, episode 50, 00:30.50–01:20.00, hook 8.** Opens on a quiet line about the price of discretion (00:31.00): two people talking by candlelight. Nothing happens in the first 3 seconds, and there is a 15-second stretch with no dialogue in the middle. The ending (a maid discovers the priest and Catherine, 01:10–01:20) is the only promo-worthy part.

**Rank 11, E003-A, episode 3, 01:34.00–02:25.75, hook 8.** Opens on the stranger's warning to a guard (01:34.10), a reaction to a fight that ended before the clip starts. Visually it is a glance.

**Rank 12, E043-A, episode 43, 00:16.20–01:16.00, hook 8.** Opens on Rupert shouting his own name and title (00:16.20). Then 25 seconds (00:37–01:04) of an official reading a military report aloud.

**Rank 3, X03, hook 8.** The first segment (episode 31, 02:18.00–02:25.50) opens on Juliana sobbing in chains, begging for an object back (02:18.40). It is emotional, not a jolt, and the object (her mother's book) was named in the line just before the cut (02:14.50). Rank 3 is deserved, but for its ending, not its opening.

Evidence across all 163 scored clips: hook scores of 8 or 9 went to 46 clips; only 2 clips got a 10 for anything. The top 20 ranking is therefore decided mostly by the cliffhanger score and tie-breaks, not by the hook, even though the hook carries the highest weight.

## 2. Stitched promos whose two halves do not fit

**Rank 1, X16, episode 26 00:55.80–01:07.00 + episode 27 00:26.10–00:48.80.** The second segment opens on the Duchess saying her lost son wore "that exact ring" (00:26.60), but the ring is never shown or mentioned in the clip. The line that sets it up, where she notices the crest on the ring (episode 27, 00:17.20–00:21.20), is 5 seconds before the segment starts. A new viewer hears about a ring with no ring. The first segment also ends on Juliana reassuring the Duchess that she is safe now (01:02.60–01:06.70), which releases the tension right before the cut. The ending itself (the Duchess asks the husband's name at 00:44.50 and someone pounds on the door at 00:46.40) is the best cliffhanger in the run, which is why it still ranks first.

Does it make sense without knowing who the Dowager Duchess is? Partly. The opening line (00:56.00) tells you an old noblewoman is being poisoned by two named people you never see, and the maid is helping her. What you cannot get from the clip is the payoff: that the maid's husband may be this woman's lost son. The clip hints at it (Juliana's surprise at 00:32.10) but the ring that proves it is missing. The model gave it a standalone score of 8; 5 or 6 is fairer. The fix is in the tool, not the model: the stitching rule picks the second segment's start by how close it gets the total to 20 seconds, not by where the exchange begins. Starting the second segment at 00:17.20 would fix this clip.

**Rank 9, X11, episode 21 00:30.90–00:40.50 + episode 22 00:25.80–00:46.00.** Segment 1: Prudence on her knees begging Juliana to come and save a seven-year-old (00:31.00), Juliana grabs her ledger and they go. Segment 2: Juliana sneaking into a manor disguised as a maid (00:26.00 onward). The second half has nothing to do with the dying boy; it is a different plot (saving the Duchess). A new viewer thinks she is running to the child and watches her put on a maid's disguise instead. The cliffhanger, the housekeeper asking who the new maid is (00:44.30), is answered 0.4 seconds after the cut. The model scored standalone 8 and cliffhanger 9 and described it as a tense disguise plot, so it did not see the join as a problem.

Both stitched clips share a character (that is the only coherence rule), so the rules let them through. The model was told that joined clips must make sense across the cut, and it did not enforce it.

## 3. Hooks that are replies to a line outside the clip

The rules reward short, punchy opening lines. Short lines are often answers, and the question is in the previous shot, which the viewer never sees.

- **Rank 4, E023-A, episode 23, 01:21.50.** Opens on Prudence gasping a one-word question (01:22.00). The line she is reacting to (01:19.00–01:21.50) ends exactly where the clip starts. The one-word answer at 01:26 rescues it, but the first 3 seconds are a reaction to nothing.
- **Rank 15, E001-A, episode 1, 00:39.00.** Opens on the sister's answer (00:39.10) to a question Juliana asks at 00:35.40–00:37.70, outside the clip.
- **Rank 18, E045-A, episode 45, 01:07.00.** Opens on 1.8 seconds of a silent close-up, then Catherine's one-word reaction (01:08.80). The word she is reacting to is in Alexander's line ending at 01:06.80, outside the clip.
- **Rank 92, E006-A, episode 6, 00:09.90.** Opens on a one-word reply (00:10.10). The model could not even quote it as a hook (the quote check failed), because it answers a line that ends at 00:09.85, outside the clip.

## 4. Cut a few seconds before the real cliffhanger

**Rank 19, E007-A, episode 7, 00:32.80–01:09.50.** Ends on Gerald's threat about her husband (01:08.60). The next 6 seconds (01:09.50–01:15.50) are a towering shadowed figure walking out of the fog toward the cottage: that is the cliffhanger, and the tool cut before it. The rules gave the 01:09.50 cut a bonus for landing on a scene change, which is exactly what cost it the better image.

**Rank 85, E009-B, episode 9, 01:28.00–01:48.00.** Ends on the informant leaving the room. The episode's real ending, 7 seconds later (01:49.80–01:55.50), is the nobleman's whispered one-word reaction with firelight in his widening eye, which is the cliffhanger the writers built.

## 5. Cliffhangers that are answered in the next line

Cutting right before an answer is the intended technique, and most of these work. The weak ones are where the answer is small:

- **Rank 6, E024-C, episode 24, ends 01:10.50** on the noblewoman's threat to Prudence (01:08.00). Answered 0.1 seconds later with a meek two-word reply. The threat is real, but the question is not one the viewer is dying to see answered.
- **Rank 9, X11**, the housekeeper's question answered by a name (see above).
- **Rank 5, E009-A**, the mother's question answered by "wait" (see above).
- **Rank 20, E016-A, episode 16, ends 00:55.20** on Juliana whispering a man's first name (00:53.20). The model called it a devastating name-drop betrayal that contextualises the stakes. To someone who has never seen the show, it is a name they have never heard. The model judged this with knowledge a new viewer does not have.

## 6. Promos that need earlier episodes

- **Rank 12, E043-A (episode 43).** Named lords, a war front three years ago, a man presumed dead: 60 seconds that only land if you know Alexander was presumed dead and Rupert took his title. Standalone score 8 is too high.
- **Rank 7, E044-A (episode 44, 00:46.40–01:10.50).** Opens mid-argument with Rupert held under guard in the background, a bride pleading, a woman in chains by the door and a rubble-strewn aisle. The core (he rejects the bride for the prisoner) reads without context, but the setting does not.
- **Rank 1, X16** (see section 2).

## 7. The same beat twice

**Rank 15, E001-A (episode 1, 00:39.00–01:21.40) and rank 17, E002-A (episode 2, 00:00.00–00:32.40)** are the same scene: the groom rejects the bride at the altar, and both end on her turning to her father. Episode 2 replays the end of episode 1. In the 3-episode trial the duplicate check grouped these two; in the full run, with 163 rows in one call, it did not. The model's duplicate grouping is not stable from run to run, so the "duplicate" label cannot be relied on without a human pass.

## 8. Rule-layer bugs found while checking

- The cue word `faint` (meant for fainting) matched "smiles faintly" and "gesturing faintly" in 7 candidates, giving a hook bonus to the quietest scenes (E014-A, E006-B, E006-C, E049-B all got "visual cue at open: faint").
- `explo` matched "explosive fury" in a camera description (E028-B), counted as a suspense cue at the end.
- `shatter` matched a figurative "shatters her worldview" (E045-A), counted as a physical cue at the open.
- `swell` (music swells) counts as a suspense cue and fires on 17 candidates, mostly at episode endings, whether or not anything is unresolved.
- Every episode gets 3 candidates whether or not it has promo material. Episode 6 (a quiet night in a cottage) produced E006-A, E006-B and E006-C, which are ranks 91, 92 and 93. Those cost model calls for nothing.

## 9. Checker false alarms

The code check that the quoted cliffhanger sits in the last 5 seconds flagged ranks 4 and 11 (E023-A, E003-A). In both the model quoted the last spoken line and the clip then runs 6 to 7 seconds of action to the real end (a door opening, a slow fade). The clips are fine; the check is stricter than the model's quoting habit. It also cannot verify quotes under 3 characters, so a one-word hook (E006-A) always reads as not found.

## What I would change first

1. Cap the model's hook score when nothing physical or visual happens in the first 3 seconds, or ask for a separate "visual hook" score.
2. In stitching, start the second segment where the exchange begins (first line of the speaker pair), not where the duration target lands.
3. Penalise a start whose first line is a short reply (under 5 words) to a line outside the clip.
4. Drop the scene-change bonus for end points, and score the 6 seconds after the cut: if a stronger image follows immediately, extend.
5. Clean the cue lists (`faint`, `swell`, `explo`, `shatter`) and skip candidates whose rule hook score is below a floor instead of forcing 3 per episode.
6. Run the duplicate grouping twice and keep only pairs found both times, or add a code rule for identical hook and cliffhanger lines.
