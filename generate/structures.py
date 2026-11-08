"""Caldera's structures: what it makes, who it sells to, where it operates, how it is organised.

Caldera is a fruit and vegetable processor in regional Victoria: canned fruit, fruit snack cups,
canned tomatoes, baked beans and spaghetti, spreads — its own brands and private label for the
major retailers, with an export importer and a foodservice distributor. One plant that makes and
stores, a third-party DC near the capital that stores and ships, a cross-dock in the north.

Everything here is deterministic and legible: round numbers, few members, each attribute the
plan actually uses. Figures are order-of-magnitude, not the real company's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------
# Materials — category → segment → brand → product → format → material
# ---------------------------------------------------------------------------------------------

CATEGORIES = {
    "CANNED_FRUIT":  ("Canned fruit", "declining"),
    "SNACK_CUPS":    ("Fruit snack cups", "growing"),
    "TOMATOES":      ("Canned tomatoes", "flat"),
    "BEANS_SPAG":    ("Baked beans and spaghetti", "flat"),
    "SPREADS":       ("Jams and spreads", "flat"),
}

# (product_code, product name, category, segment, brand, sub_brand, price_tier, branded, seasonal, campaign_input)
PRODUCTS = [
    ("PEACH_SL",   "Peach slices in juice",        "CANNED_FRUIT", "Stone fruit",  "Valley Gold", "",        "mainstream", "own",           "year-round", "PEACH"),
    ("PEAR_HV",    "Pear halves in juice",         "CANNED_FRUIT", "Pears",        "Valley Gold", "",        "mainstream", "own",           "year-round", "PEAR"),
    ("APRICOT_HV", "Apricot halves in syrup",      "CANNED_FRUIT", "Stone fruit",  "Valley Gold", "Classic", "premium",    "own",           "year-round", "APRICOT"),
    ("FRUIT_SAL",  "Fruit salad in juice",         "CANNED_FRUIT", "Mixed",        "Valley Gold", "",        "mainstream", "own",           "year-round", "PEACH"),
    ("PL_PEACH",   "Private label peach slices",   "CANNED_FRUIT", "Stone fruit",  "Private label", "",      "value",      "private_label", "year-round", "PEACH"),
    ("PL_PEAR",    "Private label pear halves",    "CANNED_FRUIT", "Pears",        "Private label", "",      "value",      "private_label", "year-round", "PEAR"),
    ("CUP_PEACH",  "Peach cups in juice",          "SNACK_CUPS",   "Kids",         "Caldera Snacks", "",     "mainstream", "own",           "year-round", "PEACH"),
    ("CUP_PEAR",   "Pear cups in juice",           "SNACK_CUPS",   "Kids",         "Caldera Snacks", "",     "mainstream", "own",           "year-round", "PEAR"),
    ("CUP_MIXED",  "Mixed fruit cups",             "SNACK_CUPS",   "Kids",         "Caldera Snacks", "",     "mainstream", "own",           "year-round", "PEACH"),
    ("CUP_ADULT",  "Fruit and chia cups",          "SNACK_CUPS",   "Adult",        "Caldera Snacks", "Plus", "premium",    "own",           "year-round", "PEAR"),
    ("PL_CUP",     "Private label fruit cups",     "SNACK_CUPS",   "Kids",         "Private label", "",      "value",      "private_label", "year-round", "PEACH"),
    ("TOM_DICED",  "Diced tomatoes",               "TOMATOES",     "Diced",        "Redgum",      "",        "mainstream", "own",           "year-round", "TOMATO"),
    ("TOM_WHOLE",  "Whole peeled tomatoes",        "TOMATOES",     "Whole",        "Redgum",      "",        "mainstream", "own",           "year-round", "TOMATO"),
    ("TOM_PASTE",  "Tomato paste",                 "TOMATOES",     "Paste",        "Redgum",      "",        "mainstream", "own",           "year-round", "TOMATO"),
    ("PL_TOM",     "Private label diced tomatoes", "TOMATOES",     "Diced",        "Private label", "",      "value",      "private_label", "year-round", "TOMATO"),
    ("BEANS",      "Baked beans in tomato sauce",  "BEANS_SPAG",   "Beans",        "Caldera",     "",        "mainstream", "own",           "year-round", ""),
    ("SPAG",       "Spaghetti in tomato sauce",    "BEANS_SPAG",   "Spaghetti",    "Caldera",     "",        "mainstream", "own",           "year-round", ""),
    ("JAM_APR",    "Apricot jam",                  "SPREADS",      "Jam",          "Orchard House", "",      "mainstream", "own",           "year-round", "APRICOT"),
    ("JAM_STRAW",  "Strawberry jam",               "SPREADS",      "Jam",          "Orchard House", "",      "mainstream", "own",           "year-round", ""),
]

# (format_code, format name, container, size_g, units_per_case, case_net_kg)
FORMATS = {
    "CAN_410":  ("410 g can",                 "tinplate can",  410, 12, 4.92),
    "CAN_825":  ("825 g can",                 "tinplate can",  825, 12, 9.90),
    "CAN_400T": ("400 g tomato can",          "tinplate can",  400, 12, 4.80),
    "CAN_220":  ("220 g snack can",           "tinplate can",  220, 24, 5.28),
    "CUP_4x120":("4 x 120 g cups",            "plastic cup",   480, 6,  2.88),
    "CUP_12x120":("12 x 120 g cups club pack","plastic cup",  1440, 4,  5.76),
    "CUP_2x170":("2 x 170 g cups",            "plastic cup",   340, 8,  2.72),
    "JAR_500":  ("500 g jar",                 "glass jar",     500, 6,  3.00),
    "TUBE_140": ("140 g paste tube",          "laminate tube", 140, 24, 3.36),
}

# product → formats it is made in
PRODUCT_FORMATS = {
    "PEACH_SL":   ["CAN_410", "CAN_825"],
    "PEAR_HV":    ["CAN_410", "CAN_825"],
    "APRICOT_HV": ["CAN_410"],
    "FRUIT_SAL":  ["CAN_410", "CAN_825"],
    "PL_PEACH":   ["CAN_410", "CAN_825"],
    "PL_PEAR":    ["CAN_410"],
    "CUP_PEACH":  ["CUP_4x120", "CUP_12x120"],
    "CUP_PEAR":   ["CUP_4x120"],
    "CUP_MIXED":  ["CUP_4x120", "CUP_12x120"],
    "CUP_ADULT":  ["CUP_2x170"],
    "PL_CUP":     ["CUP_4x120", "CUP_12x120"],
    "TOM_DICED":  ["CAN_400T"],
    "TOM_WHOLE":  ["CAN_400T"],
    "TOM_PASTE":  ["TUBE_140"],
    "PL_TOM":     ["CAN_400T"],
    "BEANS":      ["CAN_220", "CAN_410"],
    "SPAG":       ["CAN_220", "CAN_410"],
    "JAM_APR":    ["JAR_500"],
    "JAM_STRAW":  ["JAR_500"],
}


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


def build_materials() -> list[Material]:
    out: list[Material] = []
    scale = {"CANNED_FRUIT": 900, "SNACK_CUPS": 1100, "TOMATOES": 1400, "BEANS_SPAG": 700, "SPREADS": 350}
    for (pc, pname, cat, seg, brand, sub, tier, branded, seasonal, cinput) in PRODUCTS:
        for i, fc in enumerate(PRODUCT_FORMATS[pc]):
            fname, container, size, upc, netkg = FORMATS[fc]
            code = f"{pc}-{fc}"
            base = scale[cat] * (1.0 if i == 0 else 0.45) * (0.6 if branded == "private_label" else 1.0)
            status = "active"
            if pc == "CUP_ADULT":
                status = "launching"          # layer 7 has somewhere to land
            if pc == "APRICOT_HV":
                status = "delisting"          # layer 8 has somewhere to land
            out.append(Material(code, f"{pname}, {fname}", pc, fc, cat, seg, brand, sub, tier, branded,
                                seasonal, status, "", upc, netkg, cinput, base))
    # one physically distinct variant: a bonus pack that rolls to its parent
    parent = next(m for m in out if m.material_code == "PEACH_SL-CAN_410")
    out.append(Material("PEACH_SL-CAN_410-BONUS", "Peach slices in juice, 410 g can, bonus 10% pack", "PEACH_SL",
                        "CAN_410", "CANNED_FRUIT", "Stone fruit", "Valley Gold", "", "mainstream", "own",
                        "year-round", "active", parent.material_code, 12, 5.40, "PEACH", 60))
    return out


# Promo groups — reusable sets of materials promoted together (a scope object, not an attribute)
PROMO_GROUPS = {
    "PG_VALLEY_410":  ("Valley Gold 410 g range", ["PEACH_SL-CAN_410", "PEAR_HV-CAN_410", "APRICOT_HV-CAN_410", "FRUIT_SAL-CAN_410"]),
    "PG_CUPS_4PK":    ("Snack cups 4-packs",      ["CUP_PEACH-CUP_4x120", "CUP_PEAR-CUP_4x120", "CUP_MIXED-CUP_4x120"]),
    "PG_REDGUM":      ("Redgum tomato range",     ["TOM_DICED-CAN_400T", "TOM_WHOLE-CAN_400T"]),
    "PG_BEANS_SPAG":  ("Beans and spaghetti",     ["BEANS-CAN_220", "BEANS-CAN_410", "SPAG-CAN_220", "SPAG-CAN_410"]),
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
    ("STRAW_FROZ", "Strawberries, frozen",                  "ingredient", "t",   "",        "", "IMPORT"),
    ("TINPLATE",   "Tinplate coil",                         "packaging",  "t",   "",        "TINPLATE_IDX", "IMPORT"),
    ("CAN_410_E",  "410 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_400_E",  "400 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_825_E",  "825 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CAN_220_E",  "220 g can, ends",                       "packaging",  "each","",        "", "AU"),
    ("CUP_120",    "120 g PP cup with lidding",             "packaging",  "each","",        "RESIN_IDX", "IMPORT"),
    ("CUP_170",    "170 g PP cup with lidding",             "packaging",  "each","",        "RESIN_IDX", "IMPORT"),
    ("JAR_500_U",  "500 g glass jar with cap",              "packaging",  "each","",        "", "AU"),
    ("TUBE_140_U", "140 g laminate tube",                   "packaging",  "each","",        "", "IMPORT"),
    ("LABEL",      "Labels",                                "packaging",  "each","",        "", "AU"),
    ("CARTON",     "Shipping cartons",                      "packaging",  "each","",        "", "AU"),
    ("ENERGY",     "Steam and electricity",                 "utility",    "GJ",  "",        "ENERGY_IDX", "AU"),
]

# (parent material pattern by product, component, quantity per case, uom) — the abbreviated BOM
def build_bom(materials: list[Material]) -> list[dict]:
    rows: list[dict] = []
    for m in materials:
        upc, netkg = m.units_per_case, m.case_net_kg
        fruit_share = 0.55 if m.category_code in ("CANNED_FRUIT", "SNACK_CUPS") else 0.0
        if m.product_code in ("PL_PEACH", "PL_PEAR", "PL_CUP"):
            fruit_share = 0.50
        comps: list[tuple[str, float, str]] = []
        if m.campaign_input and m.category_code != "SPREADS":
            yield_factor = 1.35                      # tonnes of fruit in per tonne of fruit out, pack-out yield
            comps.append((m.campaign_input, round(netkg * fruit_share * yield_factor / 1000, 5), "t"))
        if m.category_code in ("CANNED_FRUIT", "SNACK_CUPS", "SPREADS"):
            sugar = 0.08 if "syrup" in m.material_name or m.category_code == "SPREADS" else 0.02
            comps.append(("SUGAR", round(netkg * sugar / 1000, 5), "t"))
        if m.category_code == "SPREADS":
            comps.append((m.campaign_input or "STRAW_FROZ", round(netkg * 0.45 / 1000, 5), "t"))
        if m.category_code == "BEANS_SPAG":
            comps.append(("BEANS_DRY", round(netkg * 0.20 / 1000, 5), "t"))
            comps.append(("TOMATO", round(netkg * 0.25 / 1000, 5), "t"))
        container = FORMATS[m.format_code][1]
        if container == "tinplate can":
            comps.append(("TINPLATE", round(upc * {410: 0.058, 400: 0.057, 825: 0.095, 220: 0.040}[FORMATS[m.format_code][2]] / 1000, 5), "t"))
            comps.append(({"CAN_410": "CAN_410_E", "CAN_400T": "CAN_400_E", "CAN_825": "CAN_825_E", "CAN_220": "CAN_220_E"}[m.format_code], float(upc), "each"))
        elif container == "plastic cup":
            cups_per_case = upc * (4 if "4x" in m.format_code else 12 if "12x" in m.format_code else 2)
            comps.append(("CUP_170" if "170" in m.format_code else "CUP_120", float(cups_per_case), "each"))
        elif container == "glass jar":
            comps.append(("JAR_500_U", float(upc), "each"))
        elif container == "laminate tube":
            comps.append(("TUBE_140_U", float(upc), "each"))
        comps.append(("LABEL", float(upc), "each"))
        comps.append(("CARTON", 1.0, "each"))
        comps.append(("ENERGY", round(netkg * (0.0028 if container == "tinplate can" else 0.0015), 5), "GJ"))
        for comp, qty, uom in comps:
            rows.append({"bom_version": "STD-FY2027", "plant_code": "SHP", "parent_material": m.material_code,
                         "component_material": comp, "quantity_per_case": qty, "uom": uom, "valid_from": "2026-06-29", "valid_to": ""})
    return rows


# ---------------------------------------------------------------------------------------------
# Customers — trading account → ship-to; channel, tier and terms as attributes
# ---------------------------------------------------------------------------------------------

# (account_code, name, channel, sub_channel, tier, route_to_market, state, price_list, payment_terms_days, settlement_disc_pct, collaborative, scan)
ACCOUNTS = [
    ("WAR",   "Warners Supermarkets",   "grocery",     "major chains",  "key account", "direct",       "NSW", "PL_GROCERY",     45, 0.0, "Y", "Y"),
    ("CAR",   "Carters Supermarkets",        "grocery",     "major chains",  "key account", "direct",       "VIC", "PL_GROCERY",     45, 0.0, "Y", "Y"),
    ("MER",   "Merritt Independents",             "grocery",     "independents",  "national",    "via wholesaler","NSW", "PL_WHOLESALE",  30, 1.5, "N", "N"),
    ("ALS",   "Alders Stores",               "discount",    "",              "national",    "direct",       "NSW", "PL_CONTRACT",    30, 0.0, "N", "N"),
    ("CRS",   "Crestway Wholesale",          "wholesale",   "club",          "regional",    "direct",       "VIC", "PL_GROCERY",     30, 0.0, "N", "N"),
    ("BRD",   "Bradfield Foodservice",       "foodservice", "distributor",   "national",    "via distributor","VIC","PL_FOODSERVICE", 30, 0.0, "N", "N"),
    ("EXPJ",  "Nihon Foods Import Co.",    "export",      "importer",      "regional",    "via importer", "JP",  "PL_EXPORT",      60, 0.0, "N", "N"),
]

# (ship_to_code, account_code, name, state, serving_node, stores_served)
SHIP_TOS = [
    ("WAR-NSW", "WAR", "Warners DC Minchinbury",    "NSW", "MEL", 380),
    ("WAR-VIC", "WAR", "Warners DC Melbourne",      "VIC", "MEL", 300),
    ("WAR-QLD", "WAR", "Warners DC Brisbane",       "QLD", "BNE", 260),
    ("WAR-WA",  "WAR", "Warners DC Perth",          "WA",  "MEL", 120),
    ("CAR-NSW", "CAR", "Carters DC Eastern Creek",       "NSW", "MEL", 300),
    ("CAR-VIC", "CAR", "Carters DC Truganina",           "VIC", "MEL", 260),
    ("CAR-QLD", "CAR", "Carters DC Brisbane",            "QLD", "BNE", 200),
    ("MER-VIC", "MER", "Merritt DC Laverton",          "VIC", "MEL", 450),
    ("MER-NSW", "MER", "Merritt DC Huntingwood",       "NSW", "MEL", 500),
    ("ALS-VIC", "ALS", "Alders DC Derrimut",             "VIC", "MEL", 180),
    ("ALS-NSW", "ALS", "Alders DC Minchinbury",          "NSW", "MEL", 200),
    ("CRS-VIC", "CRS", "Crestway Docklands",             "VIC", "MEL", 4),
    ("BRD-VIC", "BRD", "Bradfield DC Melbourne",         "VIC", "MEL", 0),
    ("EXPJ-POR","EXPJ","Port of Yokohama (FOB Melbourne)", "JP", "MEL", 0),
]

# which products an account ranges (private label only to its owner; export a short list)
def account_ranges(acct: str, m: Material) -> bool:
    if m.branded == "private_label":
        return {"PL_PEACH": "WAR", "PL_PEAR": "CAR", "PL_CUP": "ALS", "PL_TOM": "ALS"}.get(m.product_code) == acct or \
               (m.product_code in ("PL_PEACH", "PL_TOM") and acct == "CAR")
    if acct == "ALS":
        return False
    if acct == "EXPJ":
        return m.category_code == "SNACK_CUPS" or m.product_code == "PEACH_SL"
    if acct == "BRD":
        return m.format_code in ("CAN_825", "CAN_410", "CAN_400T") and m.category_code != "SPREADS"
    if acct == "CRS":
        return "12x" in m.format_code or m.format_code == "CAN_825"
    return True


# ---------------------------------------------------------------------------------------------
# Locations — nodes, plant hierarchy, lanes, sourcing
# ---------------------------------------------------------------------------------------------

NODES = [
    # code, name, kind, roles, ownership, state, status
    ("SHP", "Shepparton plant",            "plant",      "make,store,ship", "owned", "VIC", "open"),
    ("MEL", "Melbourne DC (3PL, Laverton)","3pl_dc",     "store,ship",      "3pl",   "VIC", "open"),
    ("BNE", "Brisbane cross-dock",         "cross_dock", "ship",            "3pl",   "QLD", "open"),
]

# plant → area → line
PLANT_AREAS = [
    ("SHP", "FRUIT",  "Fruit hall"),
    ("SHP", "TOMATO", "Tomato hall"),
    ("SHP", "CUPS",   "Snack cup hall"),
    ("SHP", "BEANS",  "Beans and spaghetti"),
    ("SHP", "SPREAD", "Spreads"),
    ("SHP", "WHSE",   "Warehouse"),
    ("SHP", "MAINT",  "Engineering and maintenance"),
]
# line_code, area, name, rate_uom
LINES = [
    ("L_FRUIT_410", "FRUIT",  "Fruit canning line 410 g",   "cases/hour"),
    ("L_FRUIT_825", "FRUIT",  "Fruit canning line 825 g",   "cases/hour"),
    ("L_TOM_400",   "TOMATO", "Tomato canning line",        "cases/hour"),
    ("L_PASTE",     "TOMATO", "Paste tube filler",          "cases/hour"),
    ("L_CUP_1",     "CUPS",   "Cup filler 1",               "cases/hour"),
    ("L_CUP_2",     "CUPS",   "Cup filler 2",               "cases/hour"),
    ("L_BEANS",     "BEANS",  "Beans and spaghetti line",   "cases/hour"),
    ("L_JAR",       "SPREAD", "Jar filler",                 "cases/hour"),
]

# lanes: from node → to node or ship-to; mode; transit days; cost per pallet
LANES = [
    ("SHP", "MEL",     "node",    "road linehaul", 1, 38.0),
    ("SHP", "BNE",     "node",    "road linehaul", 3, 95.0),
    ("MEL", "WAR-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "CAR-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "MER-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "ALS-VIC", "ship_to", "road local",    1, 22.0),
    ("MEL", "CRS-VIC", "ship_to", "road local",    1, 24.0),
    ("MEL", "BRD-VIC", "ship_to", "road local",    1, 24.0),
    ("MEL", "WAR-NSW", "ship_to", "road interstate", 2, 48.0),
    ("MEL", "CAR-NSW", "ship_to", "road interstate", 2, 48.0),
    ("MEL", "MER-NSW", "ship_to", "road interstate", 2, 48.0),
    ("MEL", "ALS-NSW", "ship_to", "road interstate", 2, 48.0),
    ("MEL", "WAR-WA",  "ship_to", "rail interstate", 6, 110.0),
    ("MEL", "EXPJ-POR","ship_to", "sea container",   18, 60.0),
    ("BNE", "WAR-QLD", "ship_to", "road local",    1, 24.0),
    ("BNE", "CAR-QLD", "ship_to", "road local",    1, 24.0),
]

# ---------------------------------------------------------------------------------------------
# Organisation — cost centres
# ---------------------------------------------------------------------------------------------

# code, name, parent, kind
COST_CENTRES = [
    ("CAL",      "Caldera Foods",                 "",        "company"),
    ("OPS",      "Operations",                    "CAL",     "function"),
    ("CC_FRUIT", "Fruit hall",                    "OPS",     "factory"),
    ("CC_TOM",   "Tomato hall",                   "OPS",     "factory"),
    ("CC_CUPS",  "Snack cup hall",                "OPS",     "factory"),
    ("CC_BEANS", "Beans and spaghetti",           "OPS",     "factory"),
    ("CC_SPRD",  "Spreads",                       "OPS",     "factory"),
    ("CC_MAINT", "Engineering and maintenance",   "OPS",     "factory"),
    ("CC_WHSE",  "Warehouse and logistics",       "OPS",     "factory"),
    ("CC_QA",    "Quality and technical",         "OPS",     "factory"),
    ("SC",       "Supply chain and planning",     "CAL",     "function"),
    ("CC_PROC",  "Procurement and grower intake", "SC",      "overhead"),
    ("CC_PLAN",  "Planning",                      "SC",      "overhead"),
    ("COM",      "Commercial",                    "CAL",     "function"),
    ("CC_SALES", "Sales and key accounts",        "COM",     "overhead"),
    ("CC_MKT",   "Marketing",                     "COM",     "overhead"),
    ("CC_TM",    "Trade marketing",               "COM",     "overhead"),
    ("FIN",      "Finance and administration",    "CAL",     "function"),
    ("CC_FIN",   "Finance",                       "FIN",     "overhead"),
    ("CC_HR",    "People and culture",            "FIN",     "overhead"),
    ("CC_IT",    "IT",                            "FIN",     "overhead"),
    ("CC_EXEC",  "Executive",                     "FIN",     "overhead"),
]

# ---------------------------------------------------------------------------------------------
# Routes — which line a product family runs on, and the rate at the rate-limiting step
# ---------------------------------------------------------------------------------------------

def build_routes(materials: list[Material]) -> list[dict]:
    rows: list[dict] = []
    for m in materials:
        if m.category_code == "CANNED_FRUIT":
            line = "L_FRUIT_825" if m.format_code == "CAN_825" else "L_FRUIT_410"
            rate = 900 if m.format_code == "CAN_825" else 1500
        elif m.category_code == "SNACK_CUPS":
            line, rate = ("L_CUP_2", 1100) if m.format_code == "CUP_2x170" else ("L_CUP_1", 1600)
        elif m.category_code == "TOMATOES":
            line, rate = ("L_PASTE", 700) if m.format_code == "TUBE_140" else ("L_TOM_400", 1800)
        elif m.category_code == "BEANS_SPAG":
            line, rate = "L_BEANS", 1700
        else:
            line, rate = "L_JAR", 800
        rows.append({"route_code": f"R-{m.material_code}", "plant_code": "SHP", "material_code": m.material_code,
                     "line_code": line, "is_rate_limiting": "Y", "rate_cases_per_hour": rate, "changeover_hours": 1.5,
                     "is_primary": "Y", "valid_from": "2026-06-29", "valid_to": ""})
    # one costed alternative: 410 g fruit can also run on the 825 line at a worse rate
    for m in materials:
        if m.category_code == "CANNED_FRUIT" and m.format_code == "CAN_410":
            rows.append({"route_code": f"R-{m.material_code}-ALT", "plant_code": "SHP", "material_code": m.material_code,
                         "line_code": "L_FRUIT_825", "is_rate_limiting": "Y", "rate_cases_per_hour": 700, "changeover_hours": 3.0,
                         "is_primary": "N", "valid_from": "2026-06-29", "valid_to": ""})
    return rows
