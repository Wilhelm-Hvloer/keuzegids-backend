from flask import Flask, request, jsonify
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)


# =========================
# DATA LADEN (BESTAAND + PRIJS)
# =========================
with open("keuzeboom.json", encoding="utf-8") as f:
    KEUZEBOOM = json.load(f)

with open("Prijstabellen coatingsystemen.json", encoding="utf-8") as f:
    PRIJS_DATA = json.load(f)

# =========================
# HULPFUNCTIES (BESTAAND)
# =========================
def get_node(node_id):
    for node in KEUZEBOOM:
        if node.get("id") == node_id:
            return node
    return None


def expand_node(node):
    expanded = dict(node)
    expanded_next = []

    for nid in node.get("next", []):
        n = get_node(nid)
        if n:
            expanded_next.append({
                "id": n["id"],
                "type": n["type"],
                "text": n.get("text", "")
            })

    expanded["next"] = expanded_next
    return expanded


# =========================
# API: START (BESTAAND)
# =========================
@app.route("/api/start", methods=["GET"])
def start():
    start_node = get_node("BFC")
    if not start_node:
        return jsonify({"error": "start-node niet gevonden"}), 500
    return jsonify(expand_node(start_node))



# =========================
# API: NEXT (BESTAAND)
# =========================
@app.route("/api/next", methods=["POST"])
def next_node():
    data = request.json
    node_id = data.get("node_id")
    choice_index = data.get("choice")

    if node_id is None or choice_index is None:
        return jsonify({"error": "node_id en choice verplicht"}), 400

    node = get_node(node_id)
    if not node:
        return jsonify({"error": "node niet gevonden"}), 404

    try:
        next_id = node["next"][choice_index]
    except (IndexError, KeyError, TypeError):
        return jsonify({"error": "ongeldige keuze"}), 400

    next_node_obj = get_node(next_id)
    if not next_node_obj:
        return jsonify({"error": "volgende node niet gevonden"}), 404



    # === SYSTEEM NODE → SYSTEEM GESELECTEERD (frontend bepaalt vervolg) ===

    if next_node_obj.get("type") == "systeem":
      response = expand_node(next_node_obj)
      response["system_selected"] = True
      response["system"] = next_node_obj.get("text")
      return jsonify(response)



    return jsonify(expand_node(next_node_obj))


# =========================
# 🆕 API: PRIJSBEREKENING
# =========================
@app.route("/api/price", methods=["POST"])
def calculate_price():
    data = request.json

    oppervlakte = data.get("oppervlakte")
    ruimtes = str(data.get("ruimtes"))
    systeem = data.get("systeem") 

    if not systeem:
        return jsonify({"error": "geen systeem opgegeven"}), 400

    if oppervlakte is None or ruimtes is None:
        return jsonify({"error": "oppervlakte en ruimtes verplicht"}), 400

    try:
        oppervlakte = float(oppervlakte)
    except (ValueError, TypeError):
        return jsonify({"error": "ongeldige oppervlakte"}), 400

    # Systeemnaam opschonen
    systeem_key = systeem.replace("Sys:", "").strip()

    # ===== SYSTEEM OPHALEN (NIEUWE JSON-STRUCTUUR) =====
    systemen = PRIJS_DATA.get("systemen", {})
    prijs_systeem = systemen.get(systeem_key)

    if not prijs_systeem:
        return jsonify({"error": f"prijssysteem '{systeem_key}' niet gevonden"}), 404


    # ===== BASISPRIJS =====
    staffels = prijs_systeem.get("staffel", [])
    prijzen = prijs_systeem.get("prijzen", {}).get(ruimtes)

    if not prijzen:
        return jsonify({"error": "geen prijzen voor dit aantal ruimtes"}), 400

    prijs_per_m2 = None

    for index, bereik in enumerate(staffels):
        if bereik.endswith("+"):
            min_m2 = float(bereik.replace("+", ""))
            if oppervlakte >= min_m2:
                prijs_per_m2 = prijzen[index]
                break
        else:
            min_m2, max_m2 = map(float, bereik.split("-"))
            if min_m2 <= oppervlakte <= max_m2:
                prijs_per_m2 = prijzen[index]
                break

    if prijs_per_m2 is None:
        return jsonify({"error": "geen passende staffel gevonden"}), 400

    basisprijs = prijs_per_m2 * oppervlakte


    # ===== EXTRA OPTIES (NIEUWE JSON-STRUCTUUR) =====
    gekozen_extras = data.get("extras", [])
    extras_prijslijst = PRIJS_DATA.get("extras", {})

    extra_totaal = 0
    extra_details = []

    for extra_key in gekozen_extras:
        extra = extras_prijslijst.get(extra_key)
        if not extra:
            continue

        if extra.get("type") == "per_m2":
            prijs_extra = extra["prijs"] * oppervlakte
        else:
            prijs_extra = extra["prijs"]

        extra_totaal += prijs_extra

        extra_details.append({
            "naam": extra["naam"],
            "prijs_per_m2": extra["prijs"],
            "totaal": round(prijs_extra)
        })




    totaalprijs = round(basisprijs + extra_totaal)

    return jsonify({
        "systeem": systeem_key,
        "oppervlakte": oppervlakte,
        "ruimtes": int(ruimtes),
        "basisprijs": round(basisprijs),
        "prijs_per_m2": round(prijs_per_m2, 2),
        "extras": extra_details,
        "totaalprijs": totaalprijs
    })



# =========================
# HEALTHCHECK
# =========================
@app.route("/")
def health():
    return "Keuzegids backend OK"
