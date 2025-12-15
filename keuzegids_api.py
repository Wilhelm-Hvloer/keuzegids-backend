from flask import Flask, request, jsonify
import json

app = Flask(__name__)

# ============================================================
# BESTANDEN
# ============================================================
PRIJSBESTAND = "Prijstabellen coatingsystemen.json"
KEUZEBESTAND = "keuzeboom.json"
SCHRAPLAAG_TOESLAG = 5.00


# ============================================================
# PRIJSBESTAND LADEN
# ============================================================
with open(PRIJSBESTAND, "r", encoding="utf-8") as f:
    _raw = json.load(f)

prijzen_data = _raw.get("Blad1", _raw)  # fallback voor Excel-export


# ============================================================
# PRIJSBEREKENING (ongewijzigd)
# ============================================================
def bepaal_staffel_index(staffels, oppervlakte):
    for i, s in enumerate(staffels):
        parts = s.replace("+", "").split("-")
        try:
            onder = float(parts[0])
            boven = float(parts[1]) if len(parts) > 1 else 999999
        except ValueError:
            continue

        if onder <= oppervlakte <= boven:
            return i

    return len(staffels) - 1


def bereken(sys, oppervlakte, ruimtes, belasting=3):
    systeem_data = prijzen_data.get(sys)

    if not systeem_data:
        return {
            "ok": False,
            "error": f"Geen prijstabel gevonden voor systeem '{sys}'.",
            "beschikbaar": list(prijzen_data.keys())
        }

    staffels = systeem_data.get("staffel", [])
    prijzen = systeem_data.get("prijzen", {})
    prijzenlijst = prijzen.get(str(belasting))

    if not prijzenlijst or not staffels:
        return {
            "ok": False,
            "error": f"Ongeldige structuur voor systeem '{sys}'"
        }

    index = bepaal_staffel_index(staffels, oppervlakte)
    prijs_m2 = prijzenlijst[index]

    toeslag = SCHRAPLAAG_TOESLAG if "schraplaag" in sys.lower() else 0
    totaal_m2 = prijs_m2 + toeslag
    totaalprijs = totaal_m2 * oppervlakte

    return {
        "ok": True,
        "systeem": sys,
        "belasting_niveau": belasting,
        "staffel": staffels[index],
        "prijs_m2_zonder_toeslag": prijs_m2,
        "toeslag_schraplaag_m2": toeslag,
        "totaalprijs_m2": totaal_m2,
        "oppervlakte_m2": oppervlakte,
        "ruimtes": ruimtes,
        "totaalprijs": round(totaalprijs, 2)
    }


# ============================================================
# KEUZEBOM LADEN (als lijst!)
# ============================================================
with open(KEUZEBESTAND, "r", encoding="utf-8") as f:
    keuzeboom = json.load(f)


def find_node(node_id):
    """Zoekt een node op id in de keuzeboom-lijst."""
    return next((n for n in keuzeboom if str(n.get("id")) == str(node_id)), None)


def extract_answer_value(node):
    """Converteert antwoordtekst:
       'Antw: nee' → 'nee'
       'J/N: ja'  → 'ja'
       'A/B: droog' → 'droog'
    """
    txt = node.get("text", "").strip()
    if ":" in txt:
        return txt.split(":", 1)[1].strip()
    return txt


def extract_system_name(node):
    """Haalt systeemnaam uit:
       'Sys: DOS Basic' → 'DOS Basic'
    """
    raw = node.get("text", "").strip()
    if ":" in raw:
        return raw.split(":", 1)[1].strip()
    return raw


# ============================================================
# HEALTH ENDPOINT
# ============================================================
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


# ============================================================
# GET_NODE: Vraag, Antwoord of Systeem ophalen
# ============================================================
@app.route("/get_node", methods=["GET"])
def api_get_node():
    node_id = request.args.get("node_id")

    node = find_node(node_id)
    if not node:
        return jsonify({"ok": False, "error": f"Node '{node_id}' niet gevonden"}), 404

    ntype = node.get("type")

    # --------------------------------------------------------
    # VRAAGNODE
    # --------------------------------------------------------
    if ntype == "vraag":
        vraagtekst = node.get("text", "")
        next_ids = node.get("next", [])

        keuzes = []
        for nxt in next_ids:
            ans_node = find_node(nxt)
            if ans_node and ans_node.get("type") == "antwoord":
                keuzes.append(extract_answer_value(ans_node))
            else:
                keuzes.append("Onbekend")

        return jsonify({
            "ok": True,
            "type": "vraag",
            "node_id": node_id,
            "vraag": vraagtekst,
            "keuzes": keuzes,
            "volgende_ids": next_ids
        })

    # --------------------------------------------------------
    # ANTWOORDNODE (bijna altijd een tussenstap)
    # --------------------------------------------------------
    if ntype == "antwoord":
        antwoordtekst = extract_answer_value(node)
        volgende = node.get("next", [])

        return jsonify({
            "ok": True,
            "type": "antwoord",
            "node_id": node_id,
            "antwoord": antwoordtekst,
            "volgende_ids": volgende
        })

    # --------------------------------------------------------
    # SYSTEEMNODE — dit is het eindpunt
    # --------------------------------------------------------
    if ntype == "systeem":
        systeemnaam = extract_system_name(node)
        return jsonify({
            "ok": True,
            "type": "systeem",
            "node_id": node_id,
            "systeem": systeemnaam
        })

    return jsonify({"ok": False, "error": "Onbekend node-type"}), 400


# ============================================================
# NEXT_NODE — gebruiker kiest een optie bij een vraag
# ============================================================
@app.route("/next_node", methods=["POST"])
def api_next_node():
    data = request.get_json()

    node_id = data.get("node_id")
    choice = int(data.get("choice")) - 1  # 1-indexed → 0-indexed

    node = find_node(node_id)
    if not node:
        return jsonify({"ok": False, "error": "Node niet gevonden"}), 404

    next_ids = node.get("next", [])

    try:
        next_node_id = next_ids[choice]
    except:
        return jsonify({"ok": False, "error": "Ongeldige keuze"}), 400

    next_node = find_node(next_node_id)

    # --------------------------------------------------------
    # Direct een systeemnode? → einde keuzeboom
    # --------------------------------------------------------
    if next_node.get("type") == "systeem":
        return jsonify({
            "ok": True,
            "type": "systeem",
            "node_id": next_node_id,
            "systeem": extract_system_name(next_node)
        })

    # --------------------------------------------------------
    # Anders de volgende node ophalen
    # --------------------------------------------------------
    with app.test_request_context(f"/get_node?node_id={next_node_id}"):
        return api_get_node()


# ============================================================
# PRIJSBEREKENING
# ============================================================
@app.route("/bereken", methods=["POST"])
def api_bereken():
    data = request.get_json()

    systeem = data.get("systeem")
    belasting = int(data.get("belasting", 3))
    opp = float(str(data.get("oppervlakte", "0")).replace(",", "."))
    ruimtes = int(data.get("ruimtes", 1))

    return jsonify(bereken(systeem, opp, ruimtes, belasting))


# ============================================================
# START SERVER
# ============================================================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
