import traceback
import sys

print("=== APP BOOT START ===")

try:
    print("Current working dir:", __file__)
except Exception:
    pass

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    supports_credentials=True
)

# =========================
# DATA LADEN (ROBUSTE PADEN)
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    with open(os.path.join(BASE_DIR, "keuzeboom.json"), encoding="utf-8") as f:
        KEUZEBOOM = json.load(f)

    with open(os.path.join(BASE_DIR, "Prijstabellen coatingsystemen.json"), encoding="utf-8") as f:
        PRIJS_DATA = json.load(f)

    with open(os.path.join(BASE_DIR, "Prijstabellen polijsten.json"), encoding="utf-8") as f:
        POLIJST_DATA = json.load(f)

    # 🔥 NIEUW: planning JSON
    with open(os.path.join(BASE_DIR, "tabellen_planning.json"), encoding="utf-8") as f:
        PLANNING_DATA = json.load(f)

    print("✅ JSON bestanden succesvol geladen (incl. planning)")

except Exception as e:
    print("❌ FOUT bij laden JSON:", e)
    raise

# =========================
# HULPFUNCTIE: NODE OPHALEN
# =========================
def get_node(node_id):
    for node in KEUZEBOOM:
        if node.get("id") == node_id:
            return node
    return None

# =========================
# PLANNING HELPERS
# =========================

import math

def resolve_systeem_naam(systemen, naam):
    naam_lower = naam.lower()

    for systeem in systemen:
        # directe naam
        if systeem["naam"].lower() == naam_lower:
            return systeem["naam"]

        # 🔥 aliases check
        if "aliases" in systeem:
            for alias in systeem["aliases"]:
                if alias.lower() == naam_lower:
                    return systeem["naam"]

    return None


def get_planning_systeem(systemen, naam):
    # 🔥 eerst naam resolven (incl. aliases)
    resolved_naam = resolve_systeem_naam(systemen, naam)

    if not resolved_naam:
        raise ValueError(f"Systeem niet gevonden: {naam}")

    systeem = next((s for s in systemen if s["naam"] == resolved_naam), None)

    # 🔥 planning_ref volgen
    while systeem.get("planning_ref"):
        ref = systeem["planning_ref"]

        # ook hier weer alias-safe
        resolved_ref = resolve_systeem_naam(systemen, ref)

        if not resolved_ref:
            raise ValueError(f"planning_ref niet gevonden: {ref}")

        systeem = next((s for s in systemen if s["naam"] == resolved_ref), None)

    return systeem


def get_regel(bewerking, m2):
    gekozen = None

    for regel in bewerking["regels"]:
        if m2 >= regel["max_m2"]:
            gekozen = regel
        else:
            break

    return gekozen if gekozen else bewerking["regels"][0]


def afronden_halve_uren(uren):
    return math.ceil(uren * 2) / 2


# =========================
# HULPFUNCTIE: NODE EXPANDEN (BACKEND-LEIDEND)
# =========================
def expand_node(node):

    expanded = {
        "id": node.get("id"),
        "type": node.get("type"),
        "text": node.get("text", ""),
        "next": []
    }

    # 🔑 chosen_extra doorgeven (antwoord-nodes)
    if node.get("chosen_extra"):
        expanded["chosen_extra"] = node.get("chosen_extra")

    # =========================
    # SYSTEEM-NODE = PRIJSFASE
    # =========================
    if node.get("type") == "systeem":
        expanded["ui_mode"] = "prijs"
        expanded["system"] = node.get("text")
        expanded["requires_price"] = True
        expanded["forced_extras"] = node.get("forced_extras", [])

    # =========================
    # CHILD NODES EXPANDEN (ALTIJD VOLLEDIGE OBJECTEN)
    # =========================
    for child in node.get("next", []):

        # Als child al een object is (bijv. bij afweging)
        if isinstance(child, dict):
            expanded["next"].append(child)
            continue

        # Anders is het een ID → ophalen en volledig expanden
        child_node = get_node(child)
        if not child_node:
            continue

        expanded["next"].append(expand_node(child_node))

    return expanded



# =========================
# BESLISLOGICA: VOLGENDE NODE BEPALEN
# =========================
def resolve_next_node(current_node, choice_index):
    """
    Backend-brein:
    - bepaalt uitsluitend de expliciete volgende node
    - GEEN auto-doorloop meer (frontend handelt dat af)
    """

    # 1️⃣ Bepaal expliciet de volgende node-id
    try:
        next_id = current_node["next"][choice_index]
    except (IndexError, KeyError, TypeError):
        return None

    # 2️⃣ Haal node op
    next_node = get_node(next_id)
    if not next_node:
        return None

    # 3️⃣ Geen automatische doorsprong meer
    return next_node





# =========================
# PLANNING BEREKENING
# =========================

def bereken_planning(systemen, systeem_naam, m2, reistijd_min, ruimtes=1, meerwerk=None):

    if meerwerk is None:
        meerwerk = []

    systeem = get_planning_systeem(systemen, systeem_naam)

    reistijd_uren = (reistijd_min * 2) / 60
    max_werk_per_persoon = 10 - reistijd_uren

    if max_werk_per_persoon <= 0:
        raise ValueError("Reistijd te hoog t.o.v. werkdag")

    dagen = {}

    # =========================
    # BASIS BEWERKINGEN
    # =========================
    for b in systeem["bewerkingen"]:
        regel = get_regel(b, m2)
        uren = regel["uur_per_m2"] * m2

        # ruimtes toeslag
        if ruimtes == 2:
            uren *= 1.2
        elif ruimtes == 3:
            uren *= 1.4

        dag = b["dag"]

        if dag not in dagen:
            dagen[dag] = []

        dagen[dag].append({
            "naam": b["naam"],
            "uren": round(uren, 1),
            "type": "standaard"
        })

    # =========================
    # 🔥 MEERWERK TOEVOEGEN
    # =========================
    for mw in meerwerk:
        dag = mw.get("dag")

        if dag is None:
            continue

        if dag not in dagen:
            dagen[dag] = []

        dagen[dag].append({
            "naam": mw.get("naam", "meerwerk"),
            "uren": float(mw.get("uren", 0)),
            "type": "meerwerk"
        })



    # =========================
    # PLANNING OPBOUWEN
    # =========================
    planning = []

    for dag in sorted(dagen.keys()):
        taken = dagen[dag]

        totaal_uren = sum(t["uren"] for t in taken)

        man = max(1, math.ceil(totaal_uren / max_werk_per_persoon))

        # werkuren per persoon
        uren_per_persoon = afronden_halve_uren(totaal_uren / man)

        # reistijd optellen
        totaal_per_persoon = afronden_halve_uren(
            uren_per_persoon + reistijd_uren
        )

        planning.append({
            "dag": dag,
            "man": man,
            "uren_per_persoon": totaal_per_persoon,
            "werk_uren_per_persoon": uren_per_persoon,
            "reistijd_per_persoon": reistijd_uren,
            "totaal_werk": round(totaal_uren, 2),
            "totaal_incl_reistijd": round(totaal_uren + (man * reistijd_uren), 2),
            "werkzaamheden": taken
        })

    return planning





# =========================
# API: START
# =========================
@app.route("/api/start", methods=["GET"])
def start():
    try:
        start_node = get_node("BFC")
        if not start_node:
            return jsonify({"error": "start-node niet gevonden"}), 500

        response = expand_node(start_node)
        response["ui_mode"] = "keuzegids"
        response["paused"] = False

        return jsonify(response), 200

    except Exception as e:
        print("❌ API /start error:", e)
        return jsonify({
            "error": "interne serverfout bij start",
            "details": str(e)
        }), 500


# =========================
# API: NEXT
# =========================
@app.route("/api/next", methods=["POST"])
def next_node():
    data = request.json
    node_id = data.get("node_id")
    choice_index = data.get("choice")

    if node_id is None or choice_index is None:
        return jsonify({"error": "node_id en choice verplicht"}), 400

    current_node = get_node(node_id)
    if not current_node:
        return jsonify({"error": "node niet gevonden"}), 404

    # 🔑 BACKEND IS BREIN
    next_node_obj = resolve_next_node(current_node, choice_index)

    if not next_node_obj:
        return jsonify({"error": "volgende node niet gevonden"}), 404

    return jsonify(expand_node(next_node_obj)), 200

# =========================
# API: PRIJSBEREKENING
# =========================
@app.route("/api/price", methods=["POST"])
def calculate_price():
    data = request.json or {}

    oppervlakte = data.get("oppervlakte")
    ruimtes = data.get("ruimtes")
    systeem = data.get("systeem")

    gekozen_extras = data.get("extras", []) or []
    forced_extras = data.get("forced_extras", []) or []

    for fx in forced_extras:
        if fx not in gekozen_extras:
            gekozen_extras.append(fx)

    xtr_uren = float(data.get("xtr_coating_verwijderen_uren", 0) or 0)
    XTR_TARIEF = 120

    meerwerk_uren = float(data.get("meerwerk_uren", 0) or 0)
    meerwerk_toelichting = data.get("meerwerk_toelichting", "")
    MEERWERK_TARIEF = 120

    materiaal_bedrag = float(data.get("materiaal_bedrag", 0) or 0)
    materiaal_toelichting = data.get("materiaal_toelichting", "")

    if not systeem:
        return jsonify({"error": "geen systeem opgegeven"}), 400

    if oppervlakte is None or ruimtes is None:
        return jsonify({"error": "oppervlakte en ruimtes verplicht"}), 400

    try:
        oppervlakte = float(oppervlakte)
        ruimtes = str(int(ruimtes))
    except (ValueError, TypeError):
        return jsonify({"error": "ongeldige invoer"}), 400

    systeem_key = systeem.replace("Sys:", "").strip()

    prijs_systeem = PRIJS_DATA.get("systemen", {}).get(systeem_key)
    if not prijs_systeem:
        return jsonify({"error": f"prijssysteem '{systeem_key}' niet gevonden"}), 404

    staffels = prijs_systeem.get("staffel", [])
    prijzen = prijs_systeem.get("prijzen", {}).get(ruimtes)
    omschrijving = prijs_systeem.get("omschrijving", [])

    if not prijzen:
        return jsonify({"error": "geen prijzen voor dit aantal ruimtes"}), 400

    # =========================
    # MINIMALE OPPERVLAKTE CHECK
    # =========================
    if oppervlakte < 30:
        return jsonify({
            "error": "m2_te_klein",
            "message": "Minimale oppervlakte is 30 m²"
        }), 200

    prijs_per_m2 = None

    for index, bereik in enumerate(staffels):
        if bereik.endswith("+"):
            if oppervlakte >= float(bereik.replace("+", "")):
                prijs_per_m2 = prijzen[index]
                break
        else:
            min_m2, max_m2 = map(float, bereik.split("-"))
            if min_m2 <= oppervlakte <= max_m2:
                prijs_per_m2 = prijzen[index]
                break

    if prijs_per_m2 is None:
        return jsonify({
            "error": "geen passende staffel gevonden"
        }), 200

    basisprijs = round(prijs_per_m2 * oppervlakte)

    extras_prijslijst = PRIJS_DATA.get("extras", {})
    extra_systemen = PRIJS_DATA.get("extra_systemen", {})

    normalized_extra_systemen = {
        key.strip().lower(): key
        for key in extra_systemen.keys()
    }

    normalized_forced = [fx.strip().lower() for fx in forced_extras]

    extra_details = []
    extra_totaal = 0

    for extra_item in gekozen_extras:

        if isinstance(extra_item, dict):

            extra_key = extra_item.get("key")
            m2 = float(extra_item.get("m2", 0) or 0)

            if not extra_key or m2 <= 0:
                continue

            extra = extras_prijslijst.get(extra_key.strip())
            if not extra:
                continue

            prijs = float(extra.get("prijs", 0))
            prijs_extra = round(prijs * m2)

            extra_totaal += prijs_extra

            extra_details.append({
                "key": extra_key,
                "naam": extra.get("naam", extra_key),
                "m2": m2,
                "prijs_per_m2": prijs,
                "totaal": prijs_extra,
                "forced": False
            })

            continue

        if not isinstance(extra_item, str):
            continue

        extra_key_clean = extra_item.strip()
        normalized_key = extra_key_clean.lower()

        if normalized_key in normalized_extra_systemen:

            echte_key = normalized_extra_systemen[normalized_key]
            addon = extra_systemen.get(echte_key)

            staffels_addon = addon.get("staffel", [])
            prijzen_addon = addon.get("prijzen", {}).get(ruimtes)

            if not prijzen_addon:
                continue

            prijs_per_m2_addon = None

            for index, bereik in enumerate(staffels_addon):
                if bereik.endswith("+"):
                    if oppervlakte >= float(bereik.replace("+", "")):
                        prijs_per_m2_addon = prijzen_addon[index]
                        break
                else:
                    min_m2, max_m2 = map(float, bereik.split("-"))
                    if min_m2 <= oppervlakte <= max_m2:
                        prijs_per_m2_addon = prijzen_addon[index]
                        break

            if prijs_per_m2_addon is None:
                continue

            totaal_addon = round(prijs_per_m2_addon * oppervlakte)
            extra_totaal += totaal_addon

            extra_details.append({
                "key": echte_key,
                "naam": echte_key,
                "prijs_per_m2": prijs_per_m2_addon,
                "totaal": totaal_addon,
                "forced": normalized_key in normalized_forced
            })

            continue

        extra = extras_prijslijst.get(extra_key_clean)
        if not extra:
            continue

        prijs = float(extra.get("prijs", 0))
        prijs_extra = prijs * oppervlakte if extra.get("type") == "per_m2" else prijs
        prijs_extra = round(prijs_extra)

        extra_totaal += prijs_extra

        extra_details.append({
            "key": extra_key_clean,
            "naam": extra.get("naam", extra_key_clean),
            "totaal": prijs_extra,
            "forced": normalized_key in normalized_forced
        })

    totaalprijs = basisprijs + extra_totaal

    if xtr_uren > 0:
        bedrag = round(xtr_uren * XTR_TARIEF)
        totaalprijs += bedrag

        extra_details.append({
            "key": "xtr_coating_verwijderen",
            "naam": "Meerwerk – coating verwijderen",
            "uren": xtr_uren,
            "tarief": XTR_TARIEF,
            "totaal": bedrag,
            "forced": False
        })

    if meerwerk_uren > 0:
        bedrag = round(meerwerk_uren * MEERWERK_TARIEF)
        totaalprijs += bedrag

        extra_details.append({
            "key": "algemeen_meerwerk",
            "naam": "Meerwerk (handmatig)",
            "uren": meerwerk_uren,
            "tarief": MEERWERK_TARIEF,
            "toelichting": meerwerk_toelichting,
            "totaal": bedrag,
            "forced": False
        })

    if materiaal_bedrag > 0:
        bedrag = round(materiaal_bedrag)
        totaalprijs += bedrag

        extra_details.append({
            "key": "extra_materiaal",
            "naam": "Extra materiaal",
            "toelichting": materiaal_toelichting,
            "totaal": bedrag,
            "forced": False
        })

    return jsonify({
        "systeem": systeem_key,
        "oppervlakte": oppervlakte,
        "ruimtes": int(ruimtes),
        "prijs_per_m2": round(prijs_per_m2, 2),
        "basisprijs": basisprijs,
        "omschrijving": omschrijving,
        "extras": extra_details,
        "totaalprijs": totaalprijs
    })


# =========================
# API: POLIJST PRIJS (GECORRIGEERD)
# =========================
@app.route("/api/polijst-price", methods=["POST"])
def calculate_polijst_price():

    data = request.json or {}

    systeem = data.get("systeem")
    klanttype = data.get("klanttype")
    oppervlakte = data.get("oppervlakte")

    curing = data.get("curing", False)

    # 🔥 NIEUW
    meerwerk_uren = float(data.get("meerwerk_uren", 0) or 0)
    meerwerk_toelichting = data.get("meerwerk_toelichting", "")

    materiaal_bedrag = float(data.get("materiaal_bedrag", 0) or 0)
    materiaal_toelichting = data.get("materiaal_toelichting", "")

    UURTARIEF = 120
    CURING_PRIJS_PER_M2 = 10

    if not systeem or not klanttype or oppervlakte is None:
        return jsonify({"error": "systeem, klanttype en oppervlakte verplicht"}), 400

    try:
        oppervlakte = float(oppervlakte)
    except (ValueError, TypeError):
        return jsonify({"error": "ongeldige oppervlakte"}), 400

    systeem_data = POLIJST_DATA.get("systemen", {}).get(systeem)
    if not systeem_data:
        return jsonify({"error": "systeem niet gevonden"}), 404

    prijzen = systeem_data.get("prijzen", {}).get(klanttype)
    staffels = systeem_data.get("staffel", [])
    vast_index = systeem_data.get("vast_tot_index", -1)

    if not prijzen:
        return jsonify({"error": "klanttype niet gevonden"}), 404

    prijs = None
    gekozen_index = None

    for index, bereik in enumerate(staffels):

        if bereik.endswith("+"):
            grens = float(bereik.replace("+", ""))
            if oppervlakte >= grens:
                prijs = prijzen[index]
                gekozen_index = index
                break
        else:
            min_m2, max_m2 = map(float, bereik.split("-"))
            if min_m2 <= oppervlakte <= max_m2:
                prijs = prijzen[index]
                gekozen_index = index
                break

    if prijs is None:
        return jsonify({"error": "geen passende staffel"}), 400

    # =========================
    # BASISPRIJS
    # =========================
    if gekozen_index <= vast_index:
        basis_totaal = prijs
        prijs_per_m2 = None
    else:
        basis_totaal = round(prijs * oppervlakte)
        prijs_per_m2 = prijs

    totaalprijs = basis_totaal
    extra_details = []

    # =========================
    # EXTRA: CURING VERWIJDEREN
    # =========================
    if curing:
        bedrag = round(oppervlakte * CURING_PRIJS_PER_M2)
        totaalprijs += bedrag

        extra_details.append({
            "key": "curing_verwijderen",
            "naam": "Curing compound verwijderen",
            "totaal": bedrag,
            "forced": False
        })

    # =========================
    # EXTRA: MEERWERK
    # =========================
    if meerwerk_uren > 0:
        bedrag = round(meerwerk_uren * UURTARIEF)
        totaalprijs += bedrag

        extra_details.append({
            "key": "algemeen_meerwerk",  # 🔥 GELIJK AAN COATING
            "naam": f"Meerwerk ({int(meerwerk_uren)} uur)",
            "uren": meerwerk_uren,
            "tarief": UURTARIEF,
            "totaal": bedrag,
            "toelichting": meerwerk_toelichting,
            "forced": False
        })

    # =========================
    # EXTRA: MATERIAAL
    # =========================
    if materiaal_bedrag > 0:
        totaalprijs += materiaal_bedrag

        extra_details.append({
            "key": "extra_materiaal",
            "naam": "Extra materiaal",
            "totaal": materiaal_bedrag,
            "toelichting": materiaal_toelichting,
            "forced": False
        })

    # =========================
    # RESPONSE
    # =========================
    return jsonify({
        "systeem": systeem,
        "klanttype": klanttype,
        "oppervlakte": oppervlakte,
        "prijs_per_m2": prijs_per_m2,
        "basis_totaal": basis_totaal,
        "totaalprijs": totaalprijs,
        "omschrijving": systeem_data.get("omschrijving", []),
        "extras": extra_details
    })


# =========================
# API: PLANNING
# =========================
@app.route("/api/planning", methods=["POST"])
def planning_endpoint():

    data = request.json or {}

    systeem = data.get("systeem")
    m2 = data.get("m2")
    reistijd = data.get("reistijd", 0)
    ruimtes = data.get("ruimtes", 1)

    # 🔥 NIEUW
    meerwerk = data.get("meerwerk", [])

    if not systeem or m2 is None:
        return jsonify({"error": "systeem en m2 verplicht"}), 400

    try:
        planning = bereken_planning(
            systemen=PLANNING_DATA["systemen"],
            systeem_naam=systeem,
            m2=float(m2),
            reistijd_min=float(reistijd),
            ruimtes=int(ruimtes),
            meerwerk=meerwerk  # 🔥 DOORGEVEN
        )

        return jsonify({"planning": planning}), 200

    except Exception as e:
        print("❌ planning error:", e)
        return jsonify({"error": str(e)}), 500




# =========================
# API: MATERIALEN (BESTELLIJST)
# =========================
@app.route("/api/materialen", methods=["POST"])
def bereken_materialen():

    data = request.json or {}
    fases = data.get("fases", [])

    materialen = {}

    for fase in fases:

        systeem = fase.get("gekozenSysteem")
        oppervlakte = fase.get("gekozenOppervlakte")
        kleur = fase.get("kleur")  # 🔥 NIEUW

        if not systeem or not oppervlakte:
            continue

        try:
            oppervlakte = float(oppervlakte)
        except (ValueError, TypeError):
            continue

        # 🔑 Systeemnaam normaliseren
        systeem_key = str(systeem).replace("Sys:", "").strip()

        systeem_data = PRIJS_DATA.get("systemen", {}).get(systeem_key)
        if not systeem_data:
            continue

        for mat in systeem_data.get("materialen", []):

            kg = (mat.get("kg_m2", 0) or 0) * oppervlakte
            product = mat.get("product")

            if not product:
                continue

            # 🔥 PRODUCT DATA UIT JSON
            product_data = PRIJS_DATA.get("producten", {}).get(product, {})
            verpakkingen = product_data.get("verpakkingen", [])
            kleur_verplicht = product_data.get("kleur_verplicht", False)

            if product not in materialen:
                materialen[product] = {
                    "kg": 0,
                    "verpakkingen": verpakkingen,
                    "kleur_verplicht": kleur_verplicht,
                    "kleur": kleur  # 🔥 NIEUW
                }

            materialen[product]["kg"] += kg

    return jsonify({
        "materialen": materialen
    }), 200




# =========================
# HEALTHCHECK
# =========================
@app.route("/")
def health():
    return "Keuzegids backend OK"
