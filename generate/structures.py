"""Caldera's structures: what it makes, who it sells to, where it operates, how it is organised.

Caldera is a fruit and vegetable processor of about $300M net sales a year: canned fruit, fruit snack cups, canned
tomatoes, baked beans and spaghetti, jams and spreads, pasta sauces and passata — its own brands and private label for
the major retailers, with an export importer and a foodservice distributor. About 300 materials: each product in its
retail sizes, multipacks, club packs and foodservice packs, the retailers' own-label packs of the mainstream lines as
variants of our standard materials, a few bonus packs, a handful launching and a handful delisting. Volume is
Pareto-shaped — a fifth of the materials carry about four-fifths of the cases — and the long tail is ranged narrowly.

Two plants that make and store: Echuca in northern Victoria (the tomato hall with the sauce and passata line, beans and
spaghetti, spreads, and part of the fruit hall) and Loxton in the Riverland, South Australia (the rest of the fruit
hall and the snack cup hall). Canned fruit is made at both, each with its own lines, rates and capacity, so a DC can be
served from the nearer plant or the further one. Three third-party DCs store and ship — Melbourne, Sydney and
Brisbane — each replenished from both plants and each serving the customers' DCs in its own region; no customer is
served direct from a plant. One reporting entity: the plants are a supply network, not a consolidation.

Everything here is deterministic and legible: the catalogue is built from a product × format × variant recipe, volume
from a rank rule, ranging from the rank — no hand-typed rows beyond the products themselves. Figures are
order-of-magnitude, not any real company's.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

# ---------------------------------------------------------------------------------------------
# Materials — category → segment → brand → product → format → material
# ---------------------------------------------------------------------------------------------

CATEGORIES = {
    "CANNED_FRUIT":  ("Canned fruit", "declining"),
    "SNACK_CUPS":    ("Fruit snack cups", "growing"),
    "TOMATOES":      ("Canned tomatoes", "flat"),
    "BEANS_SPAG":    ("Baked beans and spaghetti", "flat"),
    "SPREADS":       ("Jams and spreads", "flat"),
    "PASTA_SAUCE":   ("Pasta sauces and passata", "growing"),
}

# (product_code, product name, category, segment, brand, sub_brand, price_tier, branded, seasonal, campaign_input)
PRODUCTS = [
    ("PEACH_SL",     "Peach slices in juice",            "CANNED_FRUIT", "Stone fruit", "Valley Gold",    "",        "mainstream", "own", "year-round", "PEACH"),
    ("PEACH_DICED",  "Diced peaches in juice",           "CANNED_FRUIT", "Stone fruit", "Valley Gold",    "",        "mainstream", "own", "year-round", "PEACH"),
    ("PEACH_HV",     "Peach halves in syrup",            "CANNED_FRUIT", "Stone fruit", "Valley Gold",    "Classic", "premium",    "own", "year-round", "PEACH"),
    ("APRICOT_HV",   "Apricot halves in syrup",          "CANNED_FRUIT", "Stone fruit", "Valley Gold",    "Classic", "premium",    "own", "year-round", "APRICOT"),
    ("PEAR_HV",      "Pear halves in juice",             "CANNED_FRUIT", "Pears",       "Valley Gold",    "",        "mainstream", "own", "year-round", "PEAR"),
    ("PEAR_DICED",   "Diced pears in juice",             "CANNED_FRUIT", "Pears",       "Valley Gold",    "",        "mainstream", "own", "year-round", "PEAR"),
    ("FRUIT_SAL",    "Fruit salad in juice",             "CANNED_FRUIT", "Mixed",       "Valley Gold",    "",        "mainstream", "own", "year-round", "PEACH"),
    ("TWO_FRUITS",   "Peach and pear in juice",          "CANNED_FRUIT", "Mixed",       "Valley Gold",    "",        "mainstream", "own", "year-round", "PEAR"),
    ("TROPICAL",     "Tropical fruit salad in juice",    "CANNED_FRUIT", "Mixed",       "Valley Gold",    "",        "mainstream", "own", "year-round", "PEACH"),
    ("PEACH_MANGO",  "Peach and mango in juice",         "CANNED_FRUIT", "Mixed",       "Valley Gold",    "",        "mainstream", "own", "year-round", "PEACH"),
    ("LITE_PEACH",   "Peach slices, no added sugar",     "CANNED_FRUIT", "Stone fruit", "Valley Gold",    "Lite",    "mainstream", "own", "year-round", "PEACH"),
    ("LITE_PEAR",    "Pear halves, no added sugar",      "CANNED_FRUIT", "Pears",       "Valley Gold",    "Lite",    "mainstream", "own", "year-round", "PEAR"),
    ("APRICOT_JC", "Apricot halves in juice", "CANNED_FRUIT", "Stone fruit", "Valley Gold", "", "mainstream", "own", "year-round", "APRICOT"),
    ("FRUIT_COCKTAIL", "Fruit cocktail in syrup", "CANNED_FRUIT", "Mixed", "Valley Gold", "", "mainstream", "own", "year-round", "PEACH"),
    ("PEAR_QTR", "Pear quarters in syrup", "CANNED_FRUIT", "Pears", "Valley Gold", "Classic", "premium", "own", "year-round", "PEAR"),
    ("CUP_PEACH",    "Peach cups in juice",              "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEACH"),
    ("CUP_PEAR",     "Pear cups in juice",               "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEAR"),
    ("CUP_MIXED",    "Mixed fruit cups",                 "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEACH"),
    ("CUP_JELLY",    "Peach in jelly cups",              "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEACH"),
    ("CUP_TROPICAL", "Tropical fruit cups",              "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEACH"),
    ("CUP_SALAD",    "Fruit salad cups in juice",        "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEACH"),
    ("CUP_NAS",      "Fruit cups, no added sugar",       "SNACK_CUPS",   "Kids",        "Caldera Snacks", "",        "mainstream", "own", "year-round", "PEAR"),
    ("CUP_PEACH_PEAR", "Peach and pear cups in juice", "SNACK_CUPS", "Kids", "Caldera Snacks", "", "mainstream", "own", "year-round", "PEACH"),
    ("CUP_APPLE_PEAR", "Apple and pear cups", "SNACK_CUPS", "Kids", "Caldera Snacks", "", "mainstream", "own", "year-round", "PEAR"),
    ("CUP_JELLY_MIX", "Mixed fruit in jelly cups", "SNACK_CUPS", "Kids", "Caldera Snacks", "", "mainstream", "own", "year-round", "PEACH"),
    ("CUP_ADULT",    "Fruit and chia cups",              "SNACK_CUPS",   "Adult",       "Caldera Snacks", "Plus",    "premium",    "own", "year-round", "PEAR"),
    ("CUP_MANGO",    "Mango and passionfruit cups",      "SNACK_CUPS",   "Adult",       "Caldera Snacks", "Plus",    "premium",    "own", "year-round", "PEACH"),
    ("TOM_DICED",    "Diced tomatoes",                   "TOMATOES",     "Diced",       "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_WHOLE",    "Whole peeled tomatoes",            "TOMATOES",     "Whole",       "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_CRUSHED",  "Crushed tomatoes",                 "TOMATOES",     "Diced",       "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_PASTE",    "Tomato paste",                     "TOMATOES",     "Paste",       "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_BASIL",    "Diced tomatoes with basil and garlic", "TOMATOES", "Flavoured",   "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_ONION",    "Diced tomatoes with onion and herbs",  "TOMATOES", "Flavoured",   "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_CHILLI",   "Diced tomatoes with chilli",       "TOMATOES",     "Flavoured",   "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_NAS",      "Diced tomatoes, no added salt",    "TOMATOES",     "Diced",       "Redgum",         "",        "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_PUREE", "Tomato purée", "TOMATOES", "Paste", "Redgum", "", "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_ITALIAN", "Diced tomatoes with Italian herbs", "TOMATOES", "Flavoured", "Redgum", "", "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_OLIVE", "Diced tomatoes with olive oil and garlic", "TOMATOES", "Flavoured", "Redgum", "", "mainstream", "own", "year-round", "TOMATO"),
    ("TOM_CHERRY", "Cherry tomatoes in juice", "TOMATOES", "Whole", "Redgum", "Select", "premium", "own", "year-round", "TOMATO"),
    ("BEANS",        "Baked beans in tomato sauce",      "BEANS_SPAG",   "Beans",       "Caldera",        "",        "mainstream", "own", "year-round", ""),
    ("BEANS_RS",     "Baked beans, reduced salt and sugar", "BEANS_SPAG", "Beans",      "Caldera",        "",        "mainstream", "own", "year-round", ""),
    ("BEANS_BBQ",    "Barbecue baked beans",             "BEANS_SPAG",   "Beans",       "Caldera",        "",        "mainstream", "own", "year-round", ""),
    ("SPAG",         "Spaghetti in tomato sauce",        "BEANS_SPAG",   "Spaghetti",   "Caldera",        "",        "mainstream", "own", "year-round", ""),
    ("SPAG_LOOPS",   "Pasta loops in tomato sauce",      "BEANS_SPAG",   "Spaghetti",   "Caldera",        "",        "mainstream", "own", "year-round", ""),
    ("SPAG_CHEESE",  "Spaghetti in tomato and cheese sauce", "BEANS_SPAG", "Spaghetti", "Caldera",        "",        "mainstream", "own", "year-round", ""),
    ("BEANS_SAUS", "Baked beans with mini sausages", "BEANS_SPAG", "Beans", "Caldera", "", "mainstream", "own", "year-round", ""),
    ("BEAN_MIX", "Four-bean mix", "BEANS_SPAG", "Beans", "Caldera", "", "mainstream", "own", "year-round", ""),
    ("BEANS_CHILLI", "Chilli beans", "BEANS_SPAG", "Beans", "Caldera", "", "mainstream", "own", "year-round", ""),
    ("SPAG_BOLOG", "Spaghetti bolognese", "BEANS_SPAG", "Spaghetti", "Caldera", "", "mainstream", "own", "year-round", ""),
    ("JAM_APR",      "Apricot jam",                      "SPREADS",      "Jam",         "Orchard House",  "",        "mainstream", "own", "year-round", "APRICOT"),
    ("JAM_STRAW",    "Strawberry jam",                   "SPREADS",      "Jam",         "Orchard House",  "",        "mainstream", "own", "year-round", ""),
    ("JAM_RASP",     "Raspberry jam",                    "SPREADS",      "Jam",         "Orchard House",  "",        "mainstream", "own", "year-round", ""),
    ("JAM_PEACH",    "Peach and passionfruit jam",       "SPREADS",      "Jam",         "Orchard House",  "",        "mainstream", "own", "year-round", "PEACH"),
    ("JAM_BERRY",    "Mixed berry jam",                  "SPREADS",      "Jam",         "Orchard House",  "",        "mainstream", "own", "year-round", ""),
    ("MARMALADE",    "Orange marmalade",                 "SPREADS",      "Marmalade",   "Orchard House",  "",        "mainstream", "own", "year-round", ""),
    ("SPREAD_LITE",  "Apricot fruit spread, reduced sugar", "SPREADS",   "Jam",         "Orchard House",  "Lite",    "mainstream", "own", "year-round", "APRICOT"),
    ("JAM_PLUM", "Plum jam", "SPREADS", "Jam", "Orchard House", "", "mainstream", "own", "year-round", ""),
    ("JAM_BLACKBERRY", "Blackberry jam", "SPREADS", "Jam", "Orchard House", "", "mainstream", "own", "year-round", ""),
    ("JAM_FIG", "Fig and ginger jam", "SPREADS", "Jam", "Orchard House", "Classic", "premium", "own", "year-round", ""),
    ("PASSATA",      "Passata",                          "PASTA_SAUCE",  "Passata",     "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_NAPO",   "Napoletana pasta sauce",           "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_BASIL",  "Tomato and basil pasta sauce",     "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_BOLOG",  "Bolognese pasta sauce",            "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_ARRAB",  "Arrabbiata pasta sauce",           "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_GARLIC", "Roasted garlic pasta sauce",       "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_VEG",    "Roasted vegetable pasta sauce",    "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "",        "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_OLIVE",  "Olive and caper pasta sauce",      "PASTA_SAUCE",  "Pasta sauce", "Rosso Vale",     "Riserva", "premium",    "own", "year-round", "TOMATO"),
    ("PASSATA_BASIL", "Passata with basil", "PASTA_SAUCE", "Passata", "Rosso Vale", "", "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_PUTT", "Puttanesca pasta sauce", "PASTA_SAUCE", "Pasta sauce", "Rosso Vale", "", "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_RICOTTA", "Tomato and ricotta pasta sauce", "PASTA_SAUCE", "Pasta sauce", "Rosso Vale", "", "mainstream", "own", "year-round", "TOMATO"),
    ("SAUCE_MUSH", "Mushroom pasta sauce", "PASTA_SAUCE", "Pasta sauce", "Rosso Vale", "", "mainstream", "own", "year-round", "TOMATO"),
]


def _fmt(name: str, container: str, piece_g: int, pieces: int, upc: int) -> tuple:
    """A format: container × piece size × pieces per selling unit, and selling units per case."""
    return (name, container, piece_g * pieces, upc, round(upc * piece_g * pieces / 1000, 2), piece_g, pieces)


# format_code → (format name, container, size_g, units_per_case, case_net_kg, piece_g, pieces per unit)
FORMATS = {
    "CAN_130":    _fmt("130 g snack can",                 "tinplate can",  130, 1, 24),
    "CAN_220":    _fmt("220 g snack can",                 "tinplate can",  220, 1, 24),
    "CAN_410":    _fmt("410 g can",                       "tinplate can",  410, 1, 12),
    "CAN_825":    _fmt("825 g can",                       "tinplate can",  825, 1, 12),
    "CAN_400T":   _fmt("400 g tomato can",                "tinplate can",  400, 1, 12),
    "CAN_800T":   _fmt("800 g tomato can",                "tinplate can",  800, 1, 6),
    "CAN_3KG":    _fmt("3 kg foodservice can",            "tinplate can", 3000, 1, 3),
    "MP_4x220":   _fmt("4 x 220 g multipack",             "tinplate can",  220, 4, 6),
    "MP_4x410":   _fmt("4 x 410 g multipack",             "tinplate can",  410, 4, 3),
    "MP_4x400T":  _fmt("4 x 400 g tomato multipack",      "tinplate can",  400, 4, 3),
    "TUBE_140":   _fmt("140 g paste tube",                "laminate tube", 140, 1, 24),
    "CUP_4x120":  _fmt("4 x 120 g cups",                  "plastic cup",   120, 4, 6),
    "CUP_6x120":  _fmt("6 x 120 g cups",                  "plastic cup",   120, 6, 4),
    "CUP_12x120": _fmt("12 x 120 g cups club pack",       "plastic cup",   120, 12, 4),
    "CUP_FS_120": _fmt("120 g single cups, foodservice",  "plastic cup",   120, 1, 48),
    "CUP_2x170":  _fmt("2 x 170 g cups",                  "plastic cup",   170, 2, 8),
    "JAR_250":    _fmt("250 g jar",                       "glass jar",     250, 1, 12),
    "JAR_500":    _fmt("500 g jar",                       "glass jar",     500, 1, 6),
    "BTL_700":    _fmt("700 g bottle",                    "glass bottle",  700, 1, 12),
    "PORT_FS":    _fmt("14 g portions, foodservice",      "portion tub",    14, 1, 360),
    "POUCH_2KG":  _fmt("2 kg foodservice pouch",          "pouch",        2000, 1, 6),
}
FOODSERVICE_FORMATS = {"CAN_3KG", "CUP_FS_120", "PORT_FS", "POUCH_2KG"}
CLUB_FORMATS = {"CUP_12x120", "CAN_825", "CAN_800T", "MP_4x220", "MP_4x410", "MP_4x400T"}

# product → (volume weight, formats it is made in, most important first). The weight orders the catalogue for the
# volume rule; the format order sets each format's share within its product.
PRODUCT_RANGE = {
    "PEACH_SL":     (10.0, ["CAN_410", "CAN_825", "MP_4x410", "CAN_220", "CAN_3KG"]),
    "PEACH_DICED":  (6.0,  ["CAN_410", "CAN_220", "MP_4x220", "CAN_825", "CAN_3KG"]),
    "PEACH_HV":     (3.0,  ["CAN_410", "CAN_825", "CAN_3KG"]),
    "APRICOT_HV":   (1.0,  ["CAN_410"]),
    "PEAR_HV":      (7.0,  ["CAN_410", "CAN_825", "MP_4x410", "CAN_3KG"]),
    "PEAR_DICED":   (3.5,  ["CAN_410", "CAN_220", "CAN_3KG"]),
    "FRUIT_SAL":    (8.0,  ["CAN_410", "CAN_825", "CAN_220", "MP_4x220", "MP_4x410", "CAN_3KG"]),
    "TWO_FRUITS":   (2.0,  ["CAN_410", "CAN_825"]),
    "TROPICAL":     (3.0,  ["CAN_410", "CAN_825", "CAN_220"]),
    "PEACH_MANGO":  (2.0,  ["CAN_410", "CAN_220"]),
    "LITE_PEACH":   (2.5,  ["CAN_410", "CAN_220"]),
    "LITE_PEAR":    (1.2,  ["CAN_410"]),
    "APRICOT_JC":   (2.0,  ["CAN_410", "CAN_825", "CAN_3KG"]),
    "FRUIT_COCKTAIL": (2.5, ["CAN_410", "CAN_825", "CAN_220", "CAN_3KG"]),
    "PEAR_QTR":     (1.2,  ["CAN_825", "CAN_410"]),
    "CUP_PEACH":    (8.0,  ["CUP_4x120", "CUP_6x120", "CUP_12x120", "CUP_FS_120"]),
    "CUP_PEAR":     (4.0,  ["CUP_4x120", "CUP_6x120", "CUP_12x120"]),
    "CUP_MIXED":    (7.0,  ["CUP_4x120", "CUP_6x120", "CUP_12x120", "CUP_FS_120"]),
    "CUP_JELLY":    (3.5,  ["CUP_4x120", "CUP_6x120", "CUP_12x120"]),
    "CUP_TROPICAL": (3.0,  ["CUP_4x120", "CUP_12x120"]),
    "CUP_SALAD":    (2.5,  ["CUP_4x120", "CUP_FS_120"]),
    "CUP_NAS":      (1.5,  ["CUP_4x120"]),
    "CUP_PEACH_PEAR": (2.0, ["CUP_4x120", "CUP_12x120"]),
    "CUP_APPLE_PEAR": (1.5, ["CUP_4x120"]),
    "CUP_JELLY_MIX": (2.5, ["CUP_4x120", "CUP_12x120"]),
    "CUP_ADULT":    (1.0,  ["CUP_2x170"]),
    "CUP_MANGO":    (1.0,  ["CUP_2x170"]),
    "TOM_DICED":    (10.0, ["CAN_400T", "CAN_800T", "MP_4x400T", "CAN_3KG"]),
    "TOM_WHOLE":    (5.0,  ["CAN_400T", "CAN_800T", "CAN_3KG"]),
    "TOM_CRUSHED":  (4.5,  ["CAN_400T", "CAN_800T", "CAN_3KG"]),
    "TOM_PASTE":    (3.0,  ["TUBE_140", "CAN_3KG"]),
    "TOM_BASIL":    (3.0,  ["CAN_400T", "MP_4x400T", "CAN_800T"]),
    "TOM_ONION":    (2.0,  ["CAN_400T"]),
    "TOM_CHILLI":   (1.2,  ["CAN_400T"]),
    "TOM_NAS":      (1.5,  ["CAN_400T"]),
    "TOM_PUREE":    (1.5,  ["CAN_400T", "CAN_3KG"]),
    "TOM_ITALIAN":  (2.0,  ["CAN_400T", "MP_4x400T"]),
    "TOM_OLIVE":    (1.2,  ["CAN_400T"]),
    "TOM_CHERRY":   (1.0,  ["CAN_400T"]),
    "BEANS":        (10.0, ["CAN_410", "CAN_220", "MP_4x220", "CAN_130", "MP_4x410", "CAN_3KG"]),
    "BEANS_RS":     (3.0,  ["CAN_410", "CAN_220", "MP_4x220"]),
    "BEANS_BBQ":    (2.0,  ["CAN_410", "CAN_220"]),
    "SPAG":         (6.0,  ["CAN_410", "CAN_220", "MP_4x220", "CAN_130", "CAN_3KG"]),
    "SPAG_LOOPS":   (2.5,  ["CAN_410", "CAN_220", "CAN_130"]),
    "SPAG_CHEESE":  (1.5,  ["CAN_410", "CAN_220"]),
    "BEANS_SAUS":   (1.8,  ["CAN_410", "CAN_220"]),
    "BEAN_MIX":     (2.0,  ["CAN_410", "CAN_3KG"]),
    "BEANS_CHILLI": (1.2,  ["CAN_410"]),
    "SPAG_BOLOG":   (1.5,  ["CAN_410", "CAN_220"]),
    "JAM_APR":      (3.0,  ["JAR_500", "JAR_250", "PORT_FS"]),
    "JAM_STRAW":    (4.0,  ["JAR_500", "JAR_250", "PORT_FS"]),
    "JAM_RASP":     (2.0,  ["JAR_500", "JAR_250", "PORT_FS"]),
    "JAM_PEACH":    (1.0,  ["JAR_250"]),
    "JAM_BERRY":    (1.0,  ["JAR_250"]),
    "MARMALADE":    (1.8,  ["JAR_500", "JAR_250", "PORT_FS"]),
    "SPREAD_LITE":  (0.8,  ["JAR_250"]),
    "JAM_PLUM":     (0.8,  ["JAR_250", "JAR_500"]),
    "JAM_BLACKBERRY": (0.9, ["JAR_250", "JAR_500"]),
    "JAM_FIG":      (0.6,  ["JAR_250"]),
    "PASSATA":      (6.0,  ["BTL_700", "JAR_500", "POUCH_2KG"]),
    "SAUCE_NAPO":   (5.0,  ["JAR_500", "POUCH_2KG"]),
    "SAUCE_BASIL":  (4.0,  ["JAR_500", "POUCH_2KG"]),
    "SAUCE_BOLOG":  (3.5,  ["JAR_500", "POUCH_2KG"]),
    "SAUCE_ARRAB":  (2.0,  ["JAR_500"]),
    "SAUCE_GARLIC": (2.0,  ["JAR_500"]),
    "SAUCE_VEG":    (1.0,  ["JAR_500"]),
    "SAUCE_OLIVE":  (1.0,  ["JAR_500"]),
    "PASSATA_BASIL": (2.0, ["BTL_700"]),
    "SAUCE_PUTT":   (1.2,  ["JAR_500"]),
    "SAUCE_RICOTTA": (1.0, ["JAR_500"]),
    "SAUCE_MUSH":   (1.0,  ["JAR_500"]),
}
PRODUCT_FORMATS = {pc: fmts for pc, (_, fmts) in PRODUCT_RANGE.items()}
FORMAT_SHARE = [1.0, 0.50, 0.32, 0.22, 0.15, 0.10]              # a product's formats, most important first
FOODSERVICE_SHARE = 0.18                                         # a foodservice pack against its product's lead format

# Lifecycle: a handful launching (no history yet; the plan's launch layer carries them) and a handful delisting (history
# runs down through FY2027; the plan's exit layer has somewhere to land).
LAUNCHING = {"CUP_ADULT-CUP_2x170", "CUP_MANGO-CUP_2x170", "JAM_BERRY-JAR_250", "SAUCE_OLIVE-JAR_500", "TOM_CHILLI-CAN_400T"}
DELISTING = {"APRICOT_HV-CAN_410", "SAUCE_VEG-JAR_500", "LITE_PEAR-CAN_410", "PEACH_HV-CAN_3KG", "SPAG_CHEESE-CAN_220"}

# Private label: the major grocers' own-label packs of our mainstream lines. Physically distinct (their label), so each
# is a material of its own, a variant of our standard material that rolls to it for every reading; it is ranged only
# at its owner. (product → the formats offered as own label)
PRIVATE_LABEL_OWNERS = {"WES": "Westbrook", "CAR": "Carters", "ALS": "Alders"}
PRIVATE_LABEL_RANGE = {
    "PEACH_SL": ["CAN_410", "CAN_825", "CAN_220", "MP_4x410"], "PEACH_DICED": ["CAN_410", "CAN_220"], "PEAR_HV": ["CAN_410", "CAN_825"],
    "PEAR_DICED": ["CAN_410"], "APRICOT_JC": ["CAN_410"], "FRUIT_COCKTAIL": ["CAN_410", "CAN_825"], "FRUIT_SAL": ["CAN_410", "CAN_220"], "TROPICAL": ["CAN_410"], "CUP_TROPICAL": ["CUP_4x120"], "CUP_PEACH_PEAR": ["CUP_4x120"],
    "CUP_PEACH": ["CUP_4x120", "CUP_12x120"], "CUP_MIXED": ["CUP_4x120", "CUP_12x120"],
    "CUP_JELLY": ["CUP_4x120"], "TOM_DICED": ["CAN_400T", "CAN_800T", "MP_4x400T"], "TOM_WHOLE": ["CAN_400T", "CAN_800T"], "TOM_PUREE": ["CAN_400T"], "TOM_ITALIAN": ["CAN_400T"],
    "TOM_CRUSHED": ["CAN_400T", "CAN_800T"], "TOM_PASTE": ["TUBE_140"], "BEANS": ["CAN_410", "CAN_220", "MP_4x220"],
    "SPAG": ["CAN_410", "CAN_220", "MP_4x220"], "BEANS_RS": ["CAN_410"], "BEAN_MIX": ["CAN_410"], "SPAG_LOOPS": ["CAN_220"], "JAM_STRAW": ["JAR_500"], "JAM_APR": ["JAR_500"], "MARMALADE": ["JAR_500"], "JAM_RASP": ["JAR_500"],
    "PASSATA": ["BTL_700"], "SAUCE_NAPO": ["JAR_500"], "SAUCE_BOLOG": ["JAR_500"], "SAUCE_BASIL": ["JAR_500"], "PASSATA_BASIL": ["BTL_700"],
}
PRIVATE_LABEL_TAKE = {"WES": 85, "CAR": 80, "ALS": 90}          # % of the offered packs each grocer takes
PRIVATE_LABEL_SHARE = {"WES": 0.40, "CAR": 0.34, "ALS": 0.30}    # an own-label pack against our standard pack

# Bonus packs: physically distinct promotional packs that roll to their parent. (parent, suffix, name, net kg factor)
BONUS_PACKS = [
    ("PEACH_SL-CAN_410",  "BONUS", "bonus 10% pack",    1.10),
    ("BEANS-MP_4x220",    "BONUS", "5 for 4 bonus pack", 1.25),
    ("CUP_PEACH-CUP_4x120", "BONUS", "5 for 4 bonus pack", 1.25),
]

# The volume rule: base cases per week by rank over the catalogue, a Pareto shape — rank r carries 1 / (r + OFFSET) ^ SHAPE
# of the total — calibrated so a year's net sales invoiced lands near $300M.
TOTAL_CASES_PER_WEEK = 222_000
PARETO_SHAPE, PARETO_OFFSET = 1.9, 14.0


def _h(*parts: str) -> int:
    """A stable hash for deterministic choices (Python's own hash is salted per process)."""
    return zlib.crc32("|".join(parts).encode())


@dataclass(frozen=True)
class Material:
    material_code: str
    material_name: str
    product_code: str
    format_code: str
    category_code: str
    segment: str
    brand: str
    sub_brand: str
    price_tier: str
    branded: str                 # own | private_label
    seasonal_flag: str
    lifecycle_status: str        # active | launching | delisting
    parent_material: str         # for variants that roll to a standard material
    units_per_case: int
    case_net_kg: float
    campaign_input: str          # the fruit or tomato it is made from, or ''
    base_cases_per_week: float   # legible scale anchor for the history generator


_MATERIALS: list[Material] | None = None
_RANK: dict[str, float] = {}       # material → its volume rank as a fraction of the catalogue (0 = the top)


def build_materials() -> list[Material]:
    """The catalogue from the recipe: every product in each of its formats; the grocers' own-label packs of the
    mainstream lines as variants; the bonus packs. Then the volume rule over the whole of it."""
    global _MATERIALS, _RANK
    if _MATERIALS is not None:
        return list(_MATERIALS)
    prod = {p[0]: p for p in PRODUCTS}
    draft: list[tuple[dict, float]] = []                         # (material fields, volume score)
    for pc, pname, cat, seg, brand, sub, tier, branded, seasonal, cinput in PRODUCTS:
        weight, fmts = PRODUCT_RANGE[pc]
        retail_i = 0
        for fc in fmts:
            fname, _, _, upc, netkg, _, _ = FORMATS[fc]
            code = f"{pc}-{fc}"
            if fc in FOODSERVICE_FORMATS:
                share = FOODSERVICE_SHARE
            else:
                share = FORMAT_SHARE[retail_i]; retail_i += 1
            status = "launching" if code in LAUNCHING else "delisting" if code in DELISTING else "active"
            draft.append((dict(material_code=code, material_name=f"{pname}, {fname}", product_code=pc, format_code=fc,
                               category_code=cat, segment=seg, brand=brand, sub_brand=sub, price_tier=tier, branded=branded,
                               seasonal_flag=seasonal, lifecycle_status=status, parent_material="", units_per_case=upc,
                               case_net_kg=netkg, campaign_input=cinput), weight * share))
    score = {d["material_code"]: s for d, s in draft}
    for pc, fmts in PRIVATE_LABEL_RANGE.items():
        _, pname, cat, seg, *_rest = prod[pc]
        cinput = prod[pc][9]
        for fc in fmts:
            parent = f"{pc}-{fc}"
            fname, _, _, upc, netkg, _, _ = FORMATS[fc]
            for acct, owner in PRIVATE_LABEL_OWNERS.items():
                if _h("pl", acct, parent) % 100 >= PRIVATE_LABEL_TAKE[acct]:
                    continue
                draft.append((dict(material_code=f"{parent}-PL{acct}", material_name=f"{pname}, {fname}, {owner} own label",
                                   product_code=pc, format_code=fc, category_code=cat, segment=seg, brand="Private label",
                                   sub_brand="", price_tier="value", branded="private_label", seasonal_flag="year-round",
                                   lifecycle_status="active", parent_material=parent, units_per_case=upc, case_net_kg=netkg,
                                   campaign_input=cinput), score[parent] * PRIVATE_LABEL_SHARE[acct]))
    for parent, suffix, label, kg_factor in BONUS_PACKS:
        base = next(d for d, _ in draft if d["material_code"] == parent)
        draft.append(({**base, "material_code": f"{parent}-{suffix}", "material_name": f"{base['material_name']}, {label}",
                       "parent_material": parent, "case_net_kg": round(base["case_net_kg"] * kg_factor, 2)}, score[parent] * 0.08))

    # the volume rule: rank by score (ties broken by code), Pareto weights, launching materials carry no history
    ranked = sorted((d for d in draft if d[0]["lifecycle_status"] != "launching"), key=lambda x: (-x[1], x[0]["material_code"]))
    w = [1.0 / (r + PARETO_OFFSET) ** PARETO_SHAPE for r in range(1, len(ranked) + 1)]
    base_of = {d["material_code"]: round(TOTAL_CASES_PER_WEEK * wi / sum(w), 1) for (d, _), wi in zip(ranked, w)}
    rank_of = {d["material_code"]: r for r, (d, _) in enumerate(ranked, start=1)}
    out = [Material(**d, base_cases_per_week=base_of.get(d["material_code"], 0.0)) for d, _ in draft]
    _MATERIALS = out
    _RANK = {code: r / len(ranked) for code, r in rank_of.items()}
    return list(out)


# Promo groups — reusable sets of materials promoted together (a scope object, not an attribute). Built from the
# catalogue: our own standard packs only (the grocers promote their own label themselves).
def _group(pred) -> list[str]:
    return [m.material_code for m in build_materials() if m.branded == "own" and not m.parent_material and pred(m)]


PROMO_GROUPS = {
    "PG_VALLEY_410": ("Valley Gold 410 g range", _group(lambda m: m.brand == "Valley Gold" and m.format_code == "CAN_410")),
    "PG_CUPS_4PK":   ("Snack cups 4-packs",      _group(lambda m: m.brand == "Caldera Snacks" and m.format_code == "CUP_4x120")),
    "PG_REDGUM":     ("Redgum tomato range",     _group(lambda m: m.brand == "Redgum" and m.format_code == "CAN_400T")),
    "PG_BEANS_SPAG": ("Beans and spaghetti",     _group(lambda m: m.category_code == "BEANS_SPAG" and m.format_code in ("CAN_220", "CAN_410"))),
    "PG_ROSSO_JARS": ("Rosso Vale pasta sauces", _group(lambda m: m.category_code == "PASTA_SAUCE" and m.format_code == "JAR_500")),
    "PG_ORCHARD":    ("Orchard House jams",      _group(lambda m: m.category_code == "SPREADS" and m.format_code == "JAR_500")),
    "PG_VALLEY_825": ("Valley Gold 825 g range", _group(lambda m: m.brand == "Valley Gold" and m.format_code == "CAN_825")),
    "PG_FRUITSAL_825": ("Fruit salad 825 g",     _group(lambda m: m.material_code == "FRUIT_SAL-CAN_825")),
}

# ---------------------------------------------------------------------------------------------
# Non-finished materials and the abbreviated bill of materials (key materials only)
# ---------------------------------------------------------------------------------------------

# (code, name, material_type, base_uom, campaign_window, commodity_link, origin)
INPUT_MATERIALS = [
    ("PEACH",      "Peaches, clingstone, processing grade", "ingredient", "t",   "Jan-Mar", "", "AU"),
    ("PEAR",       "Pears, processing grade",               "ingredient", "t",   "Feb-Apr", "", "AU"),
    ("APRICOT",    "Apricots, processing grade",            "ingredient", "t",   "Dec-Jan", "", "AU"),
    ("TOMATO",     "Tomatoes, processing",                  "ingredient", "t",   "Feb-Apr", "", "AU"),
    ("SUGAR",      "Sugar, bulk",                           "ingredient", "t",   "",        "SUGAR_IDX", "AU"),
    ("BEANS_DRY",  "Navy beans, dried",                     "ingredient", "t",   "",        "", "AU"),
    ("PASTA_DRY",  "Pasta, dried",                          "ingredient", "t",   "",        "", "AU"),
    ("STRAW_FROZ", "Strawberries, frozen",                  "ingredient", "t",   "",        "", "IMPORT"),
    ("BERRY_FROZ", "Raspberries and mixed berries, frozen", "ingredient", "t",   "",        "", "IMPORT"),
    ("CITRUS",     "Oranges and peel, processed",           "ingredient", "t",   "",        "", "AU"),
    ("TROP_PULP",  "Tropical fruit, diced, aseptic",        "ingredient", "t",   "",        "", "IMPORT"),
    ("FRUIT_PULP", "Plums and figs, pulped",                "ingredient", "t",   "",        "", "AU"),
    ("SAUSAGE",    "Mini sausages, frozen",                 "ingredient", "t",   "",        "", "AU"),
    ("SEASONING",  "Herbs, spices, onion and garlic",       "ingredient", "t",   "",        "", "AU"),
    ("OLIVE_OIL",  "Olive oil",                             "ingredient", "t",   "",        "", "IMPORT"),
    ("TINPLATE",   "Tinplate coil",                         "packaging",  "t",   "",        "TINPLATE_IDX", "IMPORT"),
    ("CAN_130_E",  "130 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_220_E",  "220 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_400_E",  "400 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_410_E",  "410 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_800_E",  "800 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_825_E",  "825 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_3KG_E",  "3 kg can, ends",                        "packaging",  "each","",        "", "AU"),
    ("MP_SLEEVE",  "Multipack sleeves",                     "packaging",  "each","",        "", "AU"),
    ("CUP_120",    "120 g PP cup with lidding",             "packaging",  "each","",        "RESIN_IDX", "IMPORT"),
    ("CUP_170",    "170 g PP cup with lidding",             "packaging",  "each","",        "RESIN_IDX", "IMPORT"),
    ("JAR_250_U",  "250 g glass jar with cap",              "packaging",  "each","",        "", "AU"),
    ("JAR_500_U",  "500 g glass jar with cap",              "packaging",  "each","",        "", "AU"),
    ("BTL_700_U",  "700 g glass bottle with cap",           "packaging",  "each","",        "", "AU"),
    ("TUBE_140_U", "140 g laminate tube",                   "packaging",  "each","",        "", "IMPORT"),
    ("PORTION_U",  "14 g portion tub with lidding",         "packaging",  "each","",        "RESIN_IDX", "IMPORT"),
    ("POUCH_2KG_U","2 kg retort pouch",                     "packaging",  "each","",        "RESIN_IDX", "IMPORT"),
    ("LABEL",      "Labels",                                "packaging",  "each","",        "", "AU"),
    ("CARTON",     "Shipping cartons",                      "packaging",  "each","",        "", "AU"),
    ("ENERGY",     "Steam and electricity",                 "utility",    "GJ",  "",        "ENERGY_IDX", "AU"),
]

TINPLATE_KG = {130: 0.025, 220: 0.040, 400: 0.057, 410: 0.058, 800: 0.092, 825: 0.095, 3000: 0.300}   # per can
CAN_ENDS = {130: "CAN_130_E", 220: "CAN_220_E", 400: "CAN_400_E", 410: "CAN_410_E", 800: "CAN_800_E", 825: "CAN_825_E", 3000: "CAN_3KG_E"}
CONTAINER_UNIT = {"glass jar": {250: "JAR_250_U", 500: "JAR_500_U"}, "glass bottle": {700: "BTL_700_U"},
                  "laminate tube": {140: "TUBE_140_U"}, "portion tub": {14: "PORTION_U"}, "pouch": {2000: "POUCH_2KG_U"},
                  "plastic cup": {120: "CUP_120", 170: "CUP_170"}}
SPREAD_FRUIT = {"JAM_APR": "APRICOT", "SPREAD_LITE": "APRICOT", "JAM_STRAW": "STRAW_FROZ", "JAM_RASP": "BERRY_FROZ",
                "JAM_BERRY": "BERRY_FROZ", "JAM_PEACH": "PEACH", "MARMALADE": "CITRUS",
                "JAM_PLUM": "FRUIT_PULP", "JAM_FIG": "FRUIT_PULP", "JAM_BLACKBERRY": "BERRY_FROZ"}


def _components(m: Material) -> list[tuple[str, float, str]]:
    """Key components per case: the fruit or tomato at its pack-out yield, the other ingredients that cost, the
    container and its closure, the label, the carton, the energy."""
    _, container, _, upc, _, piece_g, pieces = FORMATS[m.format_code]
    netkg, n = m.case_net_kg, upc * pieces                          # n: pieces (cans, cups, jars) in the case
    t = lambda share, yld=1.0: round(netkg * share * yld / 1000, 5)
    comps: list[tuple[str, float, str]] = []
    cat, pc = m.category_code, m.product_code
    if cat in ("CANNED_FRUIT", "SNACK_CUPS"):
        share = 0.50 if m.branded == "private_label" else 0.55
        if pc in ("TROPICAL", "CUP_TROPICAL", "PEACH_MANGO", "CUP_MANGO"):
            comps.append(("TROP_PULP", t(0.25), "t")); share -= 0.25
        comps.append((m.campaign_input, t(share, 1.35), "t"))       # tonnes of fruit in per tonne of fruit out
        sugar = 0.0 if pc.startswith("LITE") or pc == "CUP_NAS" else 0.08 if "syrup" in m.material_name or pc.startswith("CUP_JELLY") else 0.02
        if sugar:
            comps.append(("SUGAR", t(sugar), "t"))
    elif cat == "TOMATOES":
        comps.append(("TOMATO", t(1.0, 6.0) if pc == "TOM_PASTE" else t(1.0, 2.5) if pc == "TOM_PUREE" else t(0.95, 1.15), "t"))
        if pc in ("TOM_BASIL", "TOM_ONION", "TOM_CHILLI", "TOM_ITALIAN", "TOM_OLIVE"):
            comps.append(("SEASONING", t(0.02), "t"))
    elif cat == "PASTA_SAUCE":
        passata = pc.startswith("PASSATA")
        comps.append(("TOMATO", t(0.90 if passata else 0.70, 1.4), "t"))
        if not passata:
            comps += [("SEASONING", t(0.04), "t"), ("OLIVE_OIL", t(0.02), "t"), ("SUGAR", t(0.02), "t")]
    elif cat == "BEANS_SPAG":
        comps.append(("BEANS_DRY" if m.segment == "Beans" else "PASTA_DRY", t(0.20 if m.segment == "Beans" else 0.15), "t"))
        comps.append(("TOMATO", t(0.25), "t"))
        if pc == "BEANS_SAUS":
            comps.append(("SAUSAGE", t(0.12), "t"))
        comps.append(("SUGAR", t(0.02 if pc == "BEANS_RS" else 0.04), "t"))
    elif cat == "SPREADS":
        comps.append((SPREAD_FRUIT[pc], t(0.45), "t"))
        comps.append(("SUGAR", t(0.30 if pc == "SPREAD_LITE" else 0.50), "t"))
    if container == "tinplate can":
        comps.append(("TINPLATE", round(n * TINPLATE_KG[piece_g] / 1000, 5), "t"))
        comps.append((CAN_ENDS[piece_g], float(n), "each"))
        if pieces > 1:
            comps.append(("MP_SLEEVE", float(upc), "each"))
    else:
        comps.append((CONTAINER_UNIT[container][piece_g], float(n), "each"))
    comps.append(("LABEL", float(n if container in ("tinplate can", "glass jar", "glass bottle") else upc), "each"))
    comps.append(("CARTON", 1.0, "each"))
    comps.append(("ENERGY", round(netkg * (0.0028 if container == "tinplate can" else 0.0015), 5), "GJ"))
    return comps


def build_bom(materials: list[Material]) -> list[dict]:
    """The abbreviated BOM, one set of rows per plant the material is routed at (canned fruit is routed at both)."""
    plants: dict[str, set[str]] = {}
    for r in build_routes(materials):
        plants.setdefault(r["material_code"], set()).add(r["plant_code"])
    rows: list[dict] = []
    for m in materials:
        for plant in sorted(plants[m.material_code]):
            for comp, qty, uom in _components(m):
                rows.append({"bom_version": "STD-FY2027", "plant_code": plant, "parent_material": m.material_code,
                             "component_material": comp, "quantity_per_case": qty, "uom": uom, "valid_from": "2026-06-29", "valid_to": ""})
    return rows


# ---------------------------------------------------------------------------------------------
# Customers — trading account → ship-to; channel, tier and terms as attributes
# ---------------------------------------------------------------------------------------------

# (account_code, name, channel, sub_channel, tier, route_to_market, state, price_list, payment_terms_days, settlement_disc_pct, collaborative, scan)
ACCOUNTS = [
    ("WES",   "Westbrook Supermarkets",   "grocery",     "major chains",  "key account", "direct",       "NSW", "PL_GROCERY",     45, 0.0, "Y", "Y"),
    ("CAR",   "Carters Supermarkets",        "grocery",     "major chains",  "key account", "direct",       "VIC", "PL_GROCERY",     45, 0.0, "Y", "Y"),
    ("MER",   "Merritt Independents",             "grocery",     "independents",  "national",    "via wholesaler","NSW", "PL_WHOLESALE",  30, 1.5, "N", "N"),
    ("ALS",   "Alders Stores",               "discount",    "",              "national",    "direct",       "NSW", "PL_CONTRACT",    30, 0.0, "N", "N"),
    ("CRS",   "Crestway Wholesale",          "wholesale",   "club",          "regional",    "direct",       "VIC", "PL_GROCERY",     30, 0.0, "N", "N"),
    ("BRD",   "Bradfield Foodservice",       "foodservice", "distributor",   "national",    "via distributor","VIC","PL_FOODSERVICE", 30, 0.0, "N", "N"),
    ("EXPJ",  "Nihon Foods Import Co.",    "export",      "importer",      "regional",    "via importer", "JP",  "PL_EXPORT",      60, 0.0, "N", "N"),
]

# where each account's promotions are mastered: the two majors negotiate their calendars in the trade promotion system,
# which sends them in its own codes; every other account's events are typed in the plan. One master per account, so
# no promotion can come in through both doors.
PROMOTIONS_MASTER = {"WES": "TPM", "CAR": "TPM"}          # every other account: "PLAN"

# where each account's statistical baseline comes from: the forecasting system for the three largest, calculated in the
# plan for every other account ("PLAN"). Not the same split as the promotions — the two are independent.
BASELINE_SOURCE = {"WES": "FORECAST", "CAR": "FORECAST", "MER": "FORECAST"}

# the day each account's promotional week starts: the grocers' and the discounter's catalogue week runs Wednesday to
# Tuesday; wholesale, foodservice and export run no weekly catalogue, so their events keep no week. The trading calendar
# does not change — Monday weeks, every week in one period — this is only where an event's window is expected to sit.
PROMO_WEEK_START = {"WES": "Wednesday", "CAR": "Wednesday", "MER": "Wednesday", "ALS": "Wednesday"}

# (ship_to_code, account_code, name, state, serving_node, stores_served)
# planning units: who plans the demand — a level between account and ALL on the customer structure. Export is not yet
# significant enough to need its own planner and mostly plans itself (it takes what the domestic plan does not); it sits
# with the other independents.
PLANNING_UNITS = [
    ("PU_WES", "Westbrook",          ["WES"]),
    ("PU_CAR", "Carters",            ["CAR"]),
    ("PU_MER", "Merritt",            ["MER"]),
    ("PU_IND", "Other independents", ["ALS", "CRS", "EXPJ"]),
    ("PU_HOR", "Horeca",             ["BRD"]),
]
UNIT_OF = {a: (u, n) for u, n, accts in PLANNING_UNITS for a in accts}

SHIP_TOS = [
    ("WES-NSW", "WES", "Westbrook DC Minchinbury",    "NSW", "SYD", 380),
    ("WES-VIC", "WES", "Westbrook DC Melbourne",      "VIC", "MEL", 300),
    ("WES-QLD", "WES", "Westbrook DC Brisbane",       "QLD", "BNE", 260),
    ("WES-WA",  "WES", "Westbrook DC Perth",          "WA",  "MEL", 120),
    ("CAR-NSW", "CAR", "Carters DC Eastern Creek",       "NSW", "SYD", 300),
    ("CAR-VIC", "CAR", "Carters DC Truganina",           "VIC", "MEL", 260),
    ("CAR-QLD", "CAR", "Carters DC Brisbane",            "QLD", "BNE", 200),
    ("MER-VIC", "MER", "Merritt DC Laverton",          "VIC", "MEL", 450),
    ("MER-NSW", "MER", "Merritt DC Huntingwood",       "NSW", "SYD", 500),
    ("ALS-VIC", "ALS", "Alders DC Derrimut",             "VIC", "MEL", 180),
    ("ALS-NSW", "ALS", "Alders DC Minchinbury",          "NSW", "SYD", 200),
    ("CRS-VIC", "CRS", "Crestway Docklands",             "VIC", "MEL", 4),
    ("BRD-VIC", "BRD", "Bradfield DC Melbourne",         "VIC", "MEL", 0),
    ("EXPJ-POR","EXPJ","Port of Yokohama (FOB Melbourne)", "JP", "MEL", 0),
]

# Ranging: which materials an account lists. Not every account ranges every material — the listing is part of the
# realism. Own label only at its owner; the discounter takes only its own label; the importer a short list of cups and
# fruit; foodservice its foodservice packs and the larger cans of the lines that sell; the club its club packs. The
# three grocery accounts range by the material's volume rank: the head of the catalogue at all three, the middle at
# two, the long tail at one — chosen deterministically per material.
GROCERY = ("WES", "CAR", "MER")
NOT_YET_LISTED = {("MER", "CUP_PEAR-CUP_4x120")}       # listings the plan gains: no history at the account yet


def account_ranges(acct: str, m: Material) -> bool:
    build_materials()                                   # the rank comes with the catalogue
    rank = _RANK.get(m.material_code, _RANK.get(m.parent_material, 1.0))
    if m.branded == "private_label":
        return m.material_code.endswith(f"-PL{acct}")
    if acct == "ALS":
        return False
    fs = m.format_code in FOODSERVICE_FORMATS
    if acct == "BRD":
        return fs or (m.format_code in ("CAN_825", "CAN_800T", "CAN_410", "CAN_400T", "JAR_500") and rank < 0.45)
    if fs:
        return False
    if acct == "EXPJ":
        return (m.category_code == "SNACK_CUPS" and m.format_code in ("CUP_4x120", "CUP_2x170") and rank < 0.6) or \
               (m.product_code in ("PEACH_SL", "FRUIT_SAL") and m.format_code == "CAN_410")
    if acct == "CRS":
        return m.format_code in CLUB_FORMATS and rank < 0.75
    if (acct, m.material_code) in NOT_YET_LISTED:
        return False
    # the grocery accounts
    breadth = 3 if rank < 0.30 else 2 if rank < 0.65 else 1
    order = sorted(GROCERY, key=lambda a: _h("range", m.material_code, a))
    return acct in order[:breadth]


# ---------------------------------------------------------------------------------------------
# Locations — nodes, plant hierarchy, lanes, sourcing
# ---------------------------------------------------------------------------------------------

NODES = [
    # code, name, kind, roles, ownership, state, status
    ("ECH", "Echuca plant",                "plant",      "make,store,ship", "owned", "VIC", "open"),
    ("LOX", "Loxton plant",                "plant",      "make,store,ship", "owned", "SA",  "open"),
    ("MEL", "Melbourne DC (3PL, Laverton)","3pl_dc",     "store,ship",      "3pl",   "VIC", "open"),
    ("SYD", "Sydney DC (3PL, Erskine Park)","3pl_dc",    "store,ship",      "3pl",   "NSW", "open"),
    ("BNE", "Brisbane DC (3PL, Larapinta)","3pl_dc",     "store,ship",      "3pl",   "QLD", "open"),
]
PLANTS = ("ECH", "LOX")
DCS = ("MEL", "SYD", "BNE")

# plant → area → line. Area codes carry the plant: each hall is a member of the location structure in its own right.
PLANT_AREAS = [
    ("ECH", "ECH_FRUIT",  "Echuca fruit hall"),
    ("ECH", "ECH_TOMATO", "Echuca tomato hall"),
    ("ECH", "ECH_BEANS",  "Echuca beans and spaghetti"),
    ("ECH", "ECH_SPREAD", "Echuca spreads"),
    ("ECH", "ECH_WHSE",   "Echuca warehouse"),
    ("ECH", "ECH_MAINT",  "Echuca engineering and maintenance"),
    ("LOX", "LOX_FRUIT",  "Loxton fruit hall"),
    ("LOX", "LOX_CUPS",   "Loxton snack cup hall"),
    ("LOX", "LOX_WHSE",   "Loxton warehouse"),
    ("LOX", "LOX_MAINT",  "Loxton engineering and maintenance"),
]
# line_code, plant, area, name, rate_uom, pieces per hour at the design size, base shifts outside the campaign
LINES = [
    ("L_ECH_FRUIT",   "ECH", "ECH_FRUIT",  "Echuca fruit canning line",          "cases/hour",  8_000, 2),
    ("L_ECH_TOM",     "ECH", "ECH_TOMATO", "Echuca tomato canning line",         "cases/hour",  8_800, 2),
    ("L_ECH_PASTE",   "ECH", "ECH_TOMATO", "Echuca paste tube filler",           "cases/hour",  3_600, 1),
    ("L_ECH_SAUCE",   "ECH", "ECH_TOMATO", "Echuca sauce and passata jar line",  "cases/hour",  4_800, 2),
    ("L_ECH_BEANS",   "ECH", "ECH_BEANS",  "Echuca beans and spaghetti line",    "cases/hour", 15_600, 2),
    ("L_ECH_JAR",     "ECH", "ECH_SPREAD", "Echuca jam jar filler",              "cases/hour",  2_400, 1),
    ("L_ECH_PORTION", "ECH", "ECH_SPREAD", "Echuca portion filler",              "cases/hour",  6_000, 1),
    ("L_LOX_FRUIT",   "LOX", "LOX_FRUIT",  "Loxton fruit canning line",          "cases/hour",  9_000, 2),
    ("L_LOX_CUP_1",   "LOX", "LOX_CUPS",   "Loxton cup filler 1",                "cases/hour", 20_400, 2),
    ("L_LOX_CUP_2",   "LOX", "LOX_CUPS",   "Loxton cup filler 2",                "cases/hour", 12_600, 1),
]
LINE_PLANT = {l[0]: l[1] for l in LINES}

# lanes: from node → to node or ship-to; mode; transit days; cost per pallet. Both plants reach every DC; the cost per
# pallet follows the distance (about $25 a pallet plus 4.5 cents a pallet-kilometre), so the further plant is a dearer
# source and the choice is a trade-off. Each DC serves the customers' DCs in its region — never a plant direct.
_KM = {("ECH", "MEL"): 220, ("ECH", "SYD"): 860, ("ECH", "BNE"): 1_600,
       ("LOX", "MEL"): 530, ("LOX", "SYD"): 1_150, ("LOX", "BNE"): 1_720}
LANES = [
    *[(f, t, "node", "road linehaul", 1 if km < 600 else 2 if km < 1_200 else 3, round(25 + 0.045 * km, 1))
      for (f, t), km in _KM.items()],
    ("MEL", "WES-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "CAR-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "MER-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "ALS-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "CRS-VIC", "ship_to", "road local",    1, 24.0),
    ("MEL", "BRD-VIC", "ship_to", "road local",    1, 24.0),
    ("MEL", "WES-WA",  "ship_to", "rail interstate", 6, 110.0),
    ("MEL", "EXPJ-POR","ship_to", "sea container",   18, 60.0),
    ("SYD", "WES-NSW", "ship_to", "road local",    1, 22.0),
    ("SYD", "CAR-NSW", "ship_to", "road local",    1, 22.0),
    ("SYD", "MER-NSW", "ship_to", "road local",    1, 22.0),
    ("SYD", "ALS-NSW", "ship_to", "road local",    1, 22.0),
    ("BNE", "WES-QLD", "ship_to", "road local",    1, 24.0),
    ("BNE", "CAR-QLD", "ship_to", "road local",    1, 24.0),
]

# ---------------------------------------------------------------------------------------------
# Organisation — cost centres
# ---------------------------------------------------------------------------------------------

# code, name, parent, kind. One company: each plant's halls are cost centres under operations, not an entity.
COST_CENTRES = [
    ("CAL",        "Caldera Foods",                   "",        "company"),
    ("OPS",        "Operations",                      "CAL",     "function"),
    ("CC_E_FRUIT", "Echuca fruit hall",               "OPS",     "factory"),
    ("CC_E_TOM",   "Echuca tomato hall",              "OPS",     "factory"),
    ("CC_E_BEANS", "Echuca beans and spaghetti",      "OPS",     "factory"),
    ("CC_E_SPRD",  "Echuca spreads",                  "OPS",     "factory"),
    ("CC_E_MAINT", "Echuca engineering and maintenance", "OPS",  "factory"),
    ("CC_E_WHSE",  "Echuca warehouse",                "OPS",     "factory"),
    ("CC_L_FRUIT", "Loxton fruit hall",               "OPS",     "factory"),
    ("CC_L_CUPS",  "Loxton snack cup hall",           "OPS",     "factory"),
    ("CC_L_MAINT", "Loxton engineering and maintenance", "OPS",  "factory"),
    ("CC_L_WHSE",  "Loxton warehouse",                "OPS",     "factory"),
    ("CC_LOG",     "Logistics",                       "OPS",     "factory"),
    ("CC_QA",      "Quality and technical",           "OPS",     "factory"),
    ("SC",         "Supply chain and planning",       "CAL",     "function"),
    ("CC_PROC",    "Procurement and grower intake",   "SC",      "overhead"),
    ("CC_PLAN",    "Planning",                        "SC",      "overhead"),
    ("COM",        "Commercial",                      "CAL",     "function"),
    ("CC_SALES",   "Sales and key accounts",          "COM",     "overhead"),
    ("CC_MKT",     "Marketing",                       "COM",     "overhead"),
    ("CC_TM",      "Trade marketing",                 "COM",     "overhead"),
    ("FIN",        "Finance and administration",      "CAL",     "function"),
    ("CC_FIN",     "Finance",                         "FIN",     "overhead"),
    ("CC_HR",      "People and culture",              "FIN",     "overhead"),
    ("CC_IT",      "IT",                              "FIN",     "overhead"),
    ("CC_EXEC",    "Executive",                       "FIN",     "overhead"),
]

# ---------------------------------------------------------------------------------------------
# Routes — which plant's line makes each material, and the rate at the rate-limiting step
# ---------------------------------------------------------------------------------------------

# Canned fruit is made at both plants: stone fruit and the tropical lines lead at Loxton, pears and the mixed lines at
# Echuca, and each runs at the other plant as a costed alternative at that plant's own rate.
FRUIT_LEAD_ECH = {"PEAR_HV", "PEAR_DICED", "PEAR_QTR", "LITE_PEAR", "FRUIT_SAL", "TWO_FRUITS", "FRUIT_COCKTAIL"}


def _line(m: Material, plant: str) -> str:
    fc, cat = m.format_code, m.category_code
    if cat == "CANNED_FRUIT":
        return f"L_{plant}_FRUIT"
    if cat == "SNACK_CUPS":
        return "L_LOX_CUP_1" if fc == "CUP_4x120" else "L_LOX_CUP_2"
    if cat == "TOMATOES":
        return "L_ECH_PASTE" if fc == "TUBE_140" else "L_ECH_TOM"
    if cat == "PASTA_SAUCE":
        return "L_ECH_SAUCE"
    if cat == "BEANS_SPAG":
        return "L_ECH_BEANS"
    return "L_ECH_PORTION" if fc == "PORT_FS" else "L_ECH_JAR"


# a line's speed for a piece size, against its design size (a 410 g can, a 500 g jar, a 120 g cup)
SIZE_SPEED = {130: 1.15, 220: 1.10, 400: 1.0, 410: 1.0, 800: 0.62, 825: 0.60, 3000: 0.18,
              250: 1.20, 500: 1.0, 700: 0.90, 2000: 0.25, 120: 1.0, 170: 0.80, 140: 1.0, 14: 1.0}


def _rate(m: Material, line: str) -> float:
    """Cases per hour at the rate-limiting step: the line's pieces per hour at this piece size, over the pieces in a case."""
    _, _, _, upc, _, piece_g, pieces = FORMATS[m.format_code]
    speed = next(l[5] for l in LINES if l[0] == line) * SIZE_SPEED[piece_g]
    return round(speed / (upc * pieces), 1)


def build_routes(materials: list[Material]) -> list[dict]:
    rows: list[dict] = []
    for m in materials:
        if m.category_code == "CANNED_FRUIT":
            lead = "ECH" if m.product_code in FRUIT_LEAD_ECH else "LOX"
            plants = [(lead, "Y"), ("LOX" if lead == "ECH" else "ECH", "N")]
        else:
            plants = [(LINE_PLANT[_line(m, "")], "Y")]
        for plant, primary in plants:
            line = _line(m, plant)
            rows.append({"route_code": f"R-{m.material_code}" + ("" if primary == "Y" else f"-{plant}"), "plant_code": plant,
                         "material_code": m.material_code, "line_code": line, "is_rate_limiting": "Y",
                         "rate_cases_per_hour": _rate(m, line), "changeover_hours": 1.5 if primary == "Y" else 2.5,
                         "is_primary": primary, "valid_from": "2026-06-29", "valid_to": ""})
    return rows
