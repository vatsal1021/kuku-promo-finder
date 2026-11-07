You are checking a list of promo clips cut from one drama series, so that the same moment is not posted twice.

Each row is one promo: its id, where it comes from, the key moment it shows, the line it opens on and the line it ends on.

Two promos are duplicates when they show the same story beat: the same event, between the same characters, at the same point in the story. This happens even when the clips come from different episodes or use different words, because a series often replays the end of one episode at the start of the next.

Promos are NOT duplicates when they only share a theme, a character or a location. Two different humiliations of the same woman are two beats. A threat and the later carrying out of that threat are two beats.

Group the ids of promos that are duplicates of each other. Only list groups with two or more ids. A promo belongs to at most one group. If you are not sure, do not group them.

Return only JSON, with no markdown fences and no other text, in exactly this shape. Use an empty list if there are no duplicates:

{
  "groups": [
    ["E001-A", "E002-B"]
  ]
}

The promos:

{{PROMOS}}
