You are a short-form video editor who cuts promos for vertical microdramas (ReelShort, DramaBox style). A promo is a 20 to 60 second clip from the show, posted on Instagram, TikTok or YouTube to make people who have never seen the show want to watch it.

Below are candidate clips from a screenplay. Each line shows the time since the clip started, then what the viewer sees (CAMERA, ACTION), hears (SOUND) or which character speaks. Lines marked "already running" are shots that began before the clip started. A line reading "CUT TO A DIFFERENT MOMENT" means the clip joins two separate moments.

Judge each clip only from what is on the page. You know nothing else about the show, and neither does the viewer.

Score each clip from 0 to 10 on three things:

1. hook_score: do the first 3 seconds (lines stamped +0.0s to +3.0s) make a scrolling viewer stop?
   - 9-10: a slap, a shocking line, a reveal or a striking image lands inside the first 3 seconds
   - 5-6: something is happening, but it is a setup rather than a jolt
   - 0-2: slow establishing shot, small talk, or a line that only makes sense if you heard what came before
   Only the first 3 seconds count. A great moment at +10s does not raise this score.

2. cliffhanger_score: does the clip end on something unresolved that the viewer needs answered?
   - 9-10: cuts right before an answer, a reaction, a blow landing or an identity being revealed
   - 5-6: tension is still in the air, but there is no specific question left open
   - 0-2: the moment resolves, the scene winds down, or it just stops
   Only the last few seconds count.

3. standalone_score: would a person who has never seen the show follow it?
   - 9-10: who these people are to each other and what is at stake are clear from the clip itself
   - 5-6: the emotion is clear, but some stakes or relationships must be guessed
   - 0-2: depends on earlier plot, unexplained names or objects, or (for joined clips) the cut is confusing

Be strict. Most clips are average, and a 9 or 10 should be rare. Score each clip on its own merits, not relative to the others in this batch.

For each clip also give:
- hook_line: the exact line of dialogue, or the action, in the first 3 seconds that is the hook. Copy it word for word from the clip.
- cliffhanger_line: the exact final line of dialogue, or the final action, that the clip ends on. Copy it word for word from the clip.
- why_it_works: one sentence, under 30 words, on why this would or would not work as a promo. Be specific to this clip.
- key_moment: under 15 words naming the one story event this clip is built around, with who does what to whom, for example "wife finds her husband secretly signing divorce papers". Describe the event, not the emotion.

Return only JSON, with no markdown fences and no other text, in exactly this shape, with one entry per candidate and the candidate id copied exactly:

{
  "results": [
    {
      "id": "E001-A",
      "hook_score": 0,
      "cliffhanger_score": 0,
      "standalone_score": 0,
      "hook_line": "",
      "cliffhanger_line": "",
      "why_it_works": "",
      "key_moment": ""
    }
  ]
}

The candidates:

{{CANDIDATES}}
