import re
import unicodedata


def _text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_text(part) for part in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(part) for part in value)
    normalized = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def infer_game(*values):
    text = _text(values)

    # This product title omits the game, but the Vendetta Shen/Zed deck is Riftbound.
    if (
        "vendetta" in text
        and "showdown deck" in text
        and "shen" in text
        and "zed" in text
    ):
        return "Riftbound"

    rules = (
        ("Riftbound", r"\briftbound\b|\bleague of legends\b"),
        ("Magic: The Gathering", r"\bmagic(?: the gathering)?\b|\bmtg\b"),
        ("Pokémon", r"\bpokemon\b"),
        ("One Piece", r"\bone[\s-]+piece\b"),
        ("Yu-Gi-Oh!", r"\byu\s*-?\s*gi\s*-?\s*oh\b|\byugioh\b"),
        ("Naruto", r"\bnaruto\b"),
        ("Genshin Impact", r"\bgenshin(?: impact)?\b"),
        ("Cyberpunk", r"\bcyberpunk(?:\s+red)?\b"),
        ("Disney Lorcana", r"\blorcana\b"),
        ("Digimon", r"\bdigimon\b"),
        ("Flesh and Blood", r"\bflesh\s*(?:&|and)\s*blood\b"),
        ("Star Wars Unlimited", r"\bstar wars unlimited\b|\bswu\b"),
        ("Dragon Ball Super", r"\bdragon ball(?: super)?\b"),
        ("Final Fantasy", r"\bfinal fantasy\b"),
        ("Gundam", r"\bgundam\b"),
        ("Weiß Schwarz", r"\bweiss\s*schwarz\b"),
        ("Cardfight!! Vanguard", r"\bcardfight\s*!*\s*vanguard\b"),
        ("Battle Spirits Saga", r"\bbattle spirits saga\b"),
        ("Force of Will", r"\bforce of will\b"),
        ("World of Warcraft TCG", r"\bworld of warcraft(?: tcg)?\b|\bwow tcg\b"),
        ("My Little Pony", r"\bmy little pony\b"),
        ("Grand Archive", r"\bgrand archive\b"),
        ("Sorcery: Contested Realm", r"\bsorcery(?: contested realm)?\b"),
        ("Altered", r"\baltered\b"),
        ("Vampire: The Eternal Struggle", r"\bvampire(?: the eternal struggle| eternal struggle)?\b"),
        ("Dragoborne", r"\bdragoborne\b"),
        ("The Spoils", r"\bthe spoils\b"),
    )
    for game, pattern in rules:
        if re.search(pattern, text):
            return game
    return None
