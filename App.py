from flask import Flask, request, jsonify
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    supports_credentials=True
)



# =========================
# DATA LADEN
# =========================
with open("keuzeboom.json", encoding="utf-8") as f:
    KEUZEBOOM = json.load(f)

with open("Prijstabellen coatingsystemen.json", encoding="utf-8") as f:
    PRIJS_DATA = json.load(f)


# =========================
# HULPFUNCTIE: NODE OPHALEN
# =========================
def get_node(node_id):
    for node in KEUZEBOOM:
        if node.get("id") == node_id:
            return node
    return None


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

    # extras uit keuzeboom + forced extras
    gekozen_extras = data.get("extras", []) or []
    forced_extras = data.get("forced_extras", []) or []

    # =========================
    # ZORG DAT FORCED EXTRAS ALTIJD MEEGENOMEN WORDEN
    # =========================
    for fx in forced_extras:
        if fx not in gekozen_extras:
            gekozen_extras.append(fx)

    # =========================
    # XTR – MEERWERK COATING VERWIJDEREN (UREN)
    # =========================
    xtr_uren = data.get("xtr_coating_verwijderen_uren", 0)
    XTR_TARIEF = 120

    # =========================
    # ALGEMEEN MEERWERK (UREN + TOELICHTING)
    # =========================
    meerwerk_uren = data.get("meerwerk_bedrag", 0)
    meerwerk_toelichting = data.get("meerwerk_toelichting", "")
    MEERWERK_TARIEF = 120

    # =========================
    # EXTRA MATERIAAL
    # =========================
    materiaal_bedrag = data.get("materiaal_bedrag", 0)
    materiaal_toelichting = data.get("materiaal_toelichting", "")

    # =========================
    # VALIDATIE
    # =========================
    if not systeem:
        return jsonify({"error": "geen systeem opgegeven"}), 400

    if oppervlakte is None or ruimtes is None:
        return jsonify({"error": "oppervlakte en ruimtes verplicht"}), 400

    try:
        oppervlakte = float(oppervlakte)
        ruimtes = str(int(ruimtes))
    except (ValueError, TypeError):
        return jsonify({"error": "ongeldige invoer"}), 400

    # =========================
    # SYSTEEM OPHALEN
    # =========================
    systeem_key = systeem.replace("Sys:", "").strip()

    prijs_systeem = PRIJS_DATA.get("systemen", {}).get(systeem_key)
    if not prijs_systeem:
        return jsonify({
            "error": f"prijssysteem '{systeem_key}' niet gevonden"
        }), 404

    # =========================
    # BASISPRIJS BEREKENEN
    # =========================
    staffels = prijs_systeem.get("staffel", [])
    prijzen = prijs_systeem.get("prijzen", {}).get(ruimtes)

    if not prijzen:
        return jsonify({
            "error": "geen prijzen voor dit aantal ruimtes"
        }), 400

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
        return jsonify({"error": "geen passende staffel gevonden"}), 400

    basisprijs = round(prijs_per_m2 * oppervlakte)

    # =========================
    # EXTRA OPTIES (KEUZEBOOM + FORCED + VARIABLE SURFACE)
    # =========================
    extras_prijslijst = PRIJS_DATA.get("extras", {})
    extra_details = []
    extra_totaal = 0

    for extra_item in gekozen_extras:

        # 1️⃣ NORMALE EXTRA (STRING)
        if isinstance(extra_item, str):

            extra = extras_prijslijst.get(extra_item)
            if not extra:
                continue

            prijs = float(extra.get("prijs", 0))
            prijs_extra = prijs * oppervlakte if extra.get("type") == "per_m2" else prijs
            prijs_extra = round(prijs_extra)

            extra_totaal += prijs_extra

            extra_details.append({
                "key": extra_item,
                "naam": extra.get("naam", extra_item),
                "totaal": prijs_extra,
                "forced": extra_item in forced_extras
            })

        # 2️⃣ VARIABLE SURFACE EXTRA (OBJECT MET m2)
        elif isinstance(extra_item, dict):

            extra_key = extra_item.get("key")
            m2 = float(extra_item.get("m2", 0))

            if not extra_key or m2 <= 0:
                continue

            extra = extras_prijslijst.get(extra_key)
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

    # =========================
    # TOTAALPRIJS (START)
    # =========================
    totaalprijs = basisprijs + extra_totaal

    # =========================
    # XTR – MEERWERK COATING VERWIJDEREN
    # =========================
    if xtr_uren and float(xtr_uren) > 0:
        uren = float(xtr_uren)
        bedrag = round(uren * XTR_TARIEF)

        totaalprijs += bedrag

        extra_details.append({
            "key": "xtr_coating_verwijderen",
            "naam": "Meerwerk – coating verwijderen",
            "uren": uren,
            "tarief": XTR_TARIEF,
            "totaal": bedrag,
            "forced": False
        })

    # =========================
    # ALGEMEEN MEERWERK
    # =========================
    if meerwerk_uren and float(meerwerk_uren) > 0:
        uren = float(meerwerk_uren)
        bedrag = round(uren * MEERWERK_TARIEF)

        totaalprijs += bedrag

        extra_details.append({
            "key": "algemeen_meerwerk",
            "naam": "Meerwerk (handmatig)",
            "uren": uren,
            "tarief": MEERWERK_TARIEF,
            "toelichting": meerwerk_toelichting,
            "totaal": bedrag,
            "forced": False
        })

    # =========================
    # EXTRA MATERIAAL
    # =========================
    if materiaal_bedrag and float(materiaal_bedrag) > 0:
        bedrag = round(float(materiaal_bedrag))
        totaalprijs += bedrag

        extra_details.append({
            "key": "extra_materiaal",
            "naam": "Extra materiaal",
            "toelichting": materiaal_toelichting,
            "totaal": bedrag,
            "forced": False
        })

    # =========================
    # RESULTAAT
    # =========================
    return jsonify({
        "systeem": systeem_key,
        "oppervlakte": oppervlakte,
        "ruimtes": int(ruimtes),
        "prijs_per_m2": round(prijs_per_m2, 2),
        "basisprijs": basisprijs,
        "extras": extra_details,
        "totaalprijs": totaalprijs
    })



# =========================
# HEALTHCHECK
# =========================
@app.route("/")
def health():
    return "Keuzegids backend OK"
