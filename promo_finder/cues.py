"""Cue words used by the layer 1 rules. Edit these lists to tune the rules for a new show or genre.

Each entry is a word stem matched at the start of a word, case-insensitive:
"explo" matches "explodes" and "explosion".
"""

# Physical or visual events in action / sound / camera text that stop a scrolling viewer.
PHYSICAL = [
    "slap", "strik", "struck", "explo", "detonat", "crash", "burst", "shatter", "kick", "blood",
    "flame", "blaze", "inferno", "seiz", "grab", "drag", "shov", "scream", "shriek", "chain", "shackle",
    "sword", "blade", "dagger", "pistol", "whip", "riding crop", "kneel", "one knee", "kiss", "collaps",
    "faint", "punch", "hurl", "slam", "gasp", "branding", "red-hot", "lunge", "throws", "rips", "tears off",
]

# Words in a spoken line that carry shock, threat or a reveal.
SHOCK = [
    "liar", "lied", "betray", "traitor", "treason", "kill", "murder", "dead", "death", "die", "dying",
    "hang", "gallows", "execut", "poison", "witch", "arrest", "guilty", "thief", "theft", "stole",
    "marry", "marrying", "married", "wedding", "husband", "wife", "bride", "pregnan", "affair", "bastard",
    "secret", "truth", "worthless", "disown", "banish", "duke", "duchess", "how dare", "get out",
    "seize", "swear", "revenge", "pay for", "never", "nothing", "invalid", "burn",
]

# Delivery notes on a line, e.g. **CATHERINE (Cruel, Resonant):**
INTENSE = [
    "scream", "shout", "furious", "fury", "rage", "outrage", "cold", "cruel", "menac", "threat", "venom",
    "command", "desperat", "terrif", "horrif", "shock", "sob", "weep", "crying", "begging", "plead",
    "defiant", "sadistic", "mocking", "gloat", "snarl", "roar", "hiss", "panic", "devastat", "heartbroken",
    "accus", "trembl", "vicious", "ruthless", "stunned",
]

# Action / sound / camera cues near the end of a clip that leave something unresolved.
SUSPENSE = [
    "door", "opens", "reveal", "silhouette", "emerg", "appears", "steps in", "steps forward", "freez",
    "gasp", "explo", "cliffhanger", "cut to black", "swell", "raises", "lung", "draws", "approach",
    "footsteps", "shadow", "stares", "eyes widen", "realiz", "recogni", "interrupt", "sudden", "abrupt",
    "halts", "ominous", "latch", "knock",
]

# Cues near the end of a clip that mean the tension has been released.
RESOLVED = [
    "smiles warmly", "smiles softly", "smiles gently", "soft smile", "embrac", "relief", "reliev", "laugh",
    "tender", "peace", "calm", "comfort", "sleep", "content", "serene", "nestl",
]
