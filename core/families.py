"""Food families: how "fish" knows to catch salmon, prawns and anchovies.

Each ingredient is tagged with specific families such as "salmon". A family
can have a parent, so salmon -> oily_fish -> fish -> seafood. An exclusion on
"seafood" therefore catches every family underneath it.

For ingredient names we don't have tagged (e.g. from an imported recipe),
`classify_name` guesses families from keywords as a safety net.
"""

import re

PARENTS: dict[str, str] = {
    # Seafood
    "salmon": "oily_fish",
    "worcestershire": "anchovy",
    "anchovy": "oily_fish",
    "oily_fish": "fish",
    "tuna": "fish",
    "breaded_cod": "cod",
    "cod": "white_fish",
    "white_fish": "fish",
    "fish_sauce": "fish",
    "fish": "seafood",
    "prawn": "shellfish",
    "shrimp_paste": "shellfish",
    "oyster_sauce": "oyster",
    "oyster": "shellfish",
    "mussel": "shellfish",
    "squid": "shellfish",
    "shellfish": "seafood",
    # Fungi (truffle counts as a mushroom; mycoprotein/Quorn would be fungi only)
    "truffle": "mushroom",
    "mushroom": "fungi",
    # Fruit: whole pieces only. Juice and zest ("fruit_juice") have no parent.
    "fresh_fruit": "whole_fruit",
    "dried_fruit": "whole_fruit",
    "fruit_preserve": "whole_fruit",
    # Meat substitutes (Quorn is a fungus, but it's caught here, not as a mushroom)
    "mycoprotein": "meat_substitute",
    # "paneer" is its own family with no parent.
    # Meat (used to tell whether a recipe is vegetarian)
    "chicken": "poultry",
    "turkey": "poultry",
    "duck": "poultry",
    "poultry": "meat",
    "beef": "red_meat",
    "pork": "red_meat",
    "lamb": "red_meat",
    "red_meat": "meat",
}


def ancestors(family: str) -> list[str]:
    """The family itself followed by every parent, e.g. salmon, oily_fish, fish, seafood."""
    chain = [family]
    while chain[-1] in PARENTS:
        chain.append(PARENTS[chain[-1]])
    return chain


def _words(*stems: str) -> str:
    """Regex matching whole words, allowing plural endings: apple(s), peach(es)."""
    return r"\b(?:" + "|".join(stems) + r")(?:s|es)?\b"


# Checked in order. Each match is blanked out before later rules run, so
# "fish sauce" is used up before the general "fish" rule can see it, and
# "cherry tomatoes" is used up before "cherry" can be read as fruit.
# A family of None means "this phrase is fine, ignore it".
KEYWORD_RULES: list[tuple[str | None, str]] = [
    # Phrases that look like exclusions but aren't
    (None, r"\b(?:red|green|yellow|orange)\s+(?:peppers?|lentils?|capsicums?|chillies|chilli)\b"),
    (None, r"\b(?:cherry|plum|vine|grape)\s+tomato(?:es)?\b"),
    (None, r"\b(?:kaffir\s+|makrut\s+)?lime\s+lea(?:f|ves)\b"),
    (None, r"\b(?:apple\s+cider|cider|wine|sherry|balsamic|rice|malt)\s+vinegar\b"),
    (None, r"\bcoconut\b"),
    (None, r"\bgrapeseed\b"),
    # Meat substitutes, matched early so "vegan sausages" isn't read as pork
    ("mycoprotein", r"\bquorn\b|\bmycoprotein\b"),
    ("meat_substitute", r"\b(?:tofu|tempeh|beancurd|bean\s+curd|seitan|tvp|textured\s+(?:vegetable|soya?)\s+protein|soya?\s+mince|meat\s+substitutes?)\b|"
                        r"\b(?:plant[-\s]based|meat[-\s]free|vegan|vegetarian|meatless|mock|faux|fake)\s+"
                        r"(?:\w+\s+)?(?:mince|sausages?|burgers?|chicken|bacon|meatballs?|nuggets?|pieces|strips|"
                        r"fillets?|meat|fish|fingers)\b"),
    ("paneer", _words("paneer")),
    # Juice and zest are fine for Dale
    ("fruit_juice", r"\b(?:lemon|lime|orange|grapefruit|apple|pineapple|pomegranate|yuzu|cranberry|fruit)s?\s+(?:juice|zest)\b"),
    ("fruit_juice", r"\b(?:juice|zest)\s+of\s+(?:an?\s+|\d+\s+)?(?:lemon|lime|orange)s?\b"),
    # Allowed exceptions for Jade, matched before the general fish rules
    ("fish_sauce", r"\bfish\s+sauce\b|\bnam\s+pla\b"),
    ("shrimp_paste", r"\bshrimp\s+paste\b|\bbelacan\b|\bkapi\b"),
    ("breaded_cod", r"\b(?:breaded|battered)\s+cod\b|\bcod\b[\w\s]*\bfor\s+(?:breading|battering)\b"),
    # Hidden seafood (oyster sauce and Worcestershire are allowed exceptions for Jade)
    ("mushroom", r"\boyster\s+mushrooms?\b"),
    ("oyster_sauce", r"\boyster\s+sauce\b"),
    ("oyster", r"\boysters?\b"),
    ("worcestershire", r"\bworcestershire\b"),
    ("anchovy", r"\bcaesar\b|" + _words("anchov(?:y|ie)")),
    # Fish
    ("salmon", _words("salmon")),
    ("tuna", _words("tuna")),
    ("cod", _words("cod")),
    ("oily_fish", _words("mackerel", "sardine", "pilchard", "herring", "kipper", "trout", "sprat")),
    ("white_fish", _words("haddock", "hake", "pollock", "plaice", "sole", "sea\\s+bass", "bream",
                          "monkfish", "tilapia", "basa", "coley", "halibut", "whiting", "turbot")),
    ("prawn", _words("prawn", "shrimp")),
    ("mussel", _words("mussel")),
    ("squid", _words("squid", "calamari", "octopus", "cuttlefish")),
    ("shellfish", _words("crab", "lobster", "crayfish", "langoustine", "clam", "cockle", "scallop", "shellfish")),
    ("seafood", _words("seafood")),
    ("fish", r"\bfish\w*"),
    # Mushrooms
    ("truffle", _words("truffle")),
    ("mushroom", _words("mushroom", "shiitake", "portobello", "portabella", "chanterelle", "porcini",
                        "enoki", "cep", "morel", "girolle")),
    # Fruit (bare "lemon"/"lime" are left alone: we use them for juice and zest)
    # A lemon slice as garnish is fine; preserved lemon is eaten, so it counts as fruit
    ("fruit_preserve", r"\b(?:\w+\s+)?chutney\b|\bmarmalade\b|\bjam\b|\bpreserved\s+(?:lemon|lime)s?\b"),
    ("dried_fruit", r"\bdried\s+(?:apricot|fig|mango|cranberr|cherr|date|fruit|prune)\w*|"
                    + _words("raisin", "sultana", "currant", "prune")),
    ("fresh_fruit", _words("apple", "pear", "banana", "mango", "pineapple", "papaya", "melon", "watermelon",
                           "peach", "nectarine", "plum", "apricot", "cherr(?:y|ie)", "grape", "date", "fig",
                           "berr(?:y|ie)", "strawberr(?:y|ie)", "raspberr(?:y|ie)", "blueberr(?:y|ie)",
                           "blackberr(?:y|ie)", "cranberr(?:y|ie)", "pomegranate", "kiwi", "orange",
                           "clementine", "satsuma", "mandarin", "lychee", "passion\\s+fruit", "fruit")),
    # Meat
    ("chicken", _words("chicken")),
    ("turkey", _words("turkey")),
    ("duck", _words("duck")),
    ("beef", _words("beef", "sirloin", "rump", "ribeye", "rib-eye", "brisket")),
    ("pork", _words("pork", "bacon", "ham", "chorizo", "pancetta", "prosciutto", "sausage", "salami")),
    ("lamb", _words("lamb", "mutton")),
]

_COMPILED = [(family, re.compile(pattern)) for family, pattern in KEYWORD_RULES]


def classify_name(name: str) -> set[str]:
    """Guess food families from an ingredient's name, e.g. 'King prawns' -> {'prawn'}."""
    text = name.lower()
    found: set[str] = set()
    for family, pattern in _COMPILED:
        if pattern.search(text):
            if family is not None:
                found.add(family)
            text = pattern.sub(" ", text)
    return found
