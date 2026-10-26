import re, unicodedata

NOISE = {"card", "game", "tcg", "the", "of", "and", "en", "english",
         "sealed", "karte", "pokemon", "prednarudzba"}
ALIASES = {"display": "box", "decks": "deck", "boxes": "box",
           "mtg": "magic", "gathering": ""}
CODE = re.compile(r"^(me|sv|ss|bt|ex)\d+$")   # oznake setova: ME02, SV10, BT25, EX12

def normalize(name):
    s = unicodedata.normalize("NFKD", name.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " ")
    s = s.replace("league of legends", " ")
    s = re.sub(r"\b\d+\s+boostera\b", " ", s)
    s = re.sub(r"pre-?order", " ", s)
    s = re.sub(r"(?<=\d)\.(?=\d)", "", s)       # ME02.5 -> me025
    s = re.sub(r"(?<=[a-z])-(?=\d)", "", s)     # EX-10 -> ex10
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b(set 2|1st edition)\b", " ", s)             # Naruto: "Set 2 (1st Edition)"
    s = re.sub(r"\bproving grounds\b", "origins proving grounds", s)
    tokens = set()
    for t in s.split():
        t = ALIASES.get(t, t)
        if t and t not in NOISE and not CODE.match(t):
            tokens.add(t)
    return tokens

def match_key(name):
    return " ".join(sorted(normalize(name)))
