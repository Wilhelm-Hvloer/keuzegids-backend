import json
import re

# -------------------------------------------------------
# BESTANDEN LADEN
# -------------------------------------------------------
KEUZEBESTAND = "keuzeboom.json"
PRIJSBESTAND = "Prijstabellen coatingsystemen.json"

with open(KEUZEBESTAND, "r", encoding="utf-8") as f:
    boom = json.load(f)

with open(PRIJSBESTAND, "r", encoding="utf-8") as f:
    pdata = json.load(f)

prijzen = pdata.get("Blad1", pdata)

# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def clean_answer(txt):
    """Verwijder 'Antw:' of 'Sys:' of 'Xtr:'."""
    return re.sub(r"^(Antw:|Sys:|Xtr:)\s*", "", txt).strip()

def find_node(node_id):
    """Vind node in keuzeboom."""
    if node_id == "END":
        return {"id": "END", "type": "end", "text": "Einde", "next": []}
    return next((n for n in boom if n["id"] == node_id), None)

def staffel_index(staffels, opp):
    """Correcte staffel bepalen."""
    if opp < 30:
        return 0
    for i, s in enumerate(staffels):
        clean = s.replace("+", "")
        parts = clean.split("-")
        try:
            low = float(parts[0])
            high = float(parts[1]) if len(parts) > 1 else 999999
        except:
            continue
        if low <= opp <= high:
            return i
    return len(staffels) - 1

def bereken_prijs(system, opp, ruimtes):
    sd = prijzen[system]
    staffels = sd["staffel"]
    prijzen_m2 = sd["prijzen"][str(ruimtes)]
    idx = staffel_index(staffels, opp)
    pm2 = prijzen_m2[idx]
    totaal = pm2 * opp

    return {
        "systeem": system,
        "oppervlakte": opp,
        "ruimtes": ruimtes,
        "prijs_m2": pm2,
        "basis": round(totaal, 2),
        "staffel": staffels[idx],
    }

# -------------------------------------------------------
# HOOFDPROGRAMMA
# -------------------------------------------------------
def main():
    print("\n=== KEUZEGIDS HARDEMAN ===\n")

    node_id = "BFC"
    gekozen = {"geisoleerd": "", "ondergrond": "", "belasting": ""}
    extra_opties = []
    basisprijs = None
    opp = None
    ruimtes = None

    while True:
        node = find_node(node_id)
        if not node:
            print(f"FOUT: node '{node_id}' niet gevonden.")
            break

        t = node["type"]

        # ---------------------------------------------------
        # 1. VRAAG
        # ---------------------------------------------------
        if t == "vraag":
            print("\n" + node["text"])
            keuzes = [clean_answer(find_node(k)["text"]) for k in node["next"]]

            for i, k in enumerate(keuzes, 1):
                print(f"{i}.   {k}")

            antwoord = int(input("Maak een keuze: ")) - 1
            gekozen_txt = keuzes[antwoord]
            next_id = node["next"][antwoord]

            lt = node["text"].lower()
            if "vloer" in lt and "geïsoleerd" in lt:
                gekozen["geisoleerd"] = gekozen_txt
            if "ondergrond" in lt:
                gekozen["ondergrond"] = gekozen_txt
            if "belasting" in lt:
                gekozen["belasting"] = gekozen_txt

            node_id = next_id
            continue

        # ---------------------------------------------------
        # 2. ANTWOORD (incl. ADD250 & DecoFlakes)
        # ---------------------------------------------------
        if t == "antwoord":
            naam = clean_answer(node["text"])
            p_m2_raw = node.get("price_per_m2", 0)
            p_m2 = float(p_m2_raw) if isinstance(p_m2_raw, str) else p_m2_raw
            vaste = float(node.get("price", 0))

            # ---- SPECIAL CASE: DURAKORREL ----
            if "durakorrel" in naam.lower():
                print("\nDurakorrel wordt plaatselijk toegepast.")
                try:
                    dk_m2 = float(input("Op hoeveel m² moet Durakorrel worden toegevoegd? "))
                except:
                    dk_m2 = 0

                meerprijs = round(dk_m2 * p_m2, 2)

                extra_opties.append({
                    "type": "durakorrel",
                    "naam": "Durakorrel",
                    "oppervlakte": dk_m2,
                    "p_m2": p_m2,
                    "prijs": meerprijs
                })

                node_id = node["next"][0]
                continue

            extra_opties.append({
                "type": "extra",
                "naam": naam,
                "prijs": vaste,
                "p_m2": p_m2
            })

            node_id = node["next"][0]
            continue

        # ---------------------------------------------------
        # 3. MEERWERK (XTR)
        # ---------------------------------------------------
        if t == "xtr":
            melding = clean_answer(node["text"])
            print(f"\nLET OP: {melding}")

            try:
                uren = float(input("Hoeveel uur meerwerk moet gerekend worden? "))
            except:
                uren = 0

            prijs = round(uren * 120, 2)

            extra_opties.append({
                "type": "meerwerk",
                "naam": melding,
                "uren": uren,
                "prijs": prijs
            })

            node_id = node["next"][0]
            continue

        # ---------------------------------------------------
        # 4. SYSTEEM
        # ---------------------------------------------------
        if t == "systeem":
            systeem = clean_answer(node["text"])
            print(f"\nGekozen systeem: {systeem}")

            if opp is None:
                opp = float(input("\nOppervlakte (m²): "))
            if ruimtes is None:
                ruimtes = int(input("Aantal ruimtes (1–3): "))

            basisprijs = bereken_prijs(systeem, opp, ruimtes)

            print("\n--- BASISPRIJS ---")
            print(f"Staffel: {basisprijs['staffel']}")
            print(f"Prijs per m²: €{basisprijs['prijs_m2']}")
            print(f"Basisprijs: €{basisprijs['basis']}")

            node_id = node["next"][0]
            continue

        # ---------------------------------------------------
        # 5. AFWEGING
        # ---------------------------------------------------
        if t == "afw":
            opties = node["next"]
            print("\n=== AFWEGING ===")
            print(clean_answer(node["text"]))

            if opp is None:
                opp = float(input("\nOppervlakte (m²): "))
            if ruimtes is None:
                ruimtes = int(input("Aantal ruimtes (1–3): "))

            systemen = []
            for sid in opties:
                n = find_node(sid)
                sys = clean_answer(n["text"])
                pr = bereken_prijs(sys, opp, ruimtes)
                systemen.append((sid, sys, pr))

            print("\nBeschikbare systemen:\n")
            for i, (_, nm, pr) in enumerate(systemen, 1):
                print(f"{i}) {nm}")
                print(f"    Staffel: {pr['staffel']}")
                print(f"    Prijs/m²: €{pr['prijs_m2']}")
                print(f"    Totaalprijs: €{pr['basis']}\n")

            keuze = int(input("Welk systeem kies je? ")) - 1
            sid, sys, pr = systemen[keuze]

            basisprijs = pr

            print(f"\nGekozen systeem: {sys}")

            node_id = find_node(sid)["next"][0]
            continue

        # ---------------------------------------------------
        # 6. EINDE
        # ---------------------------------------------------
        if t == "end" or not node["next"]:
            break

    # -------------------------------------------------------
    # SAMENVATTING
    # -------------------------------------------------------
    print("\n================ SAMENVATTING ================\n")
    print(f"Vloer geïsoleerd:  {gekozen['geisoleerd']}")
    print(f"Ondergrond:  {gekozen['ondergrond']}")
    print(f"Belasting:  {gekozen['belasting']}\n")

    print(f"Gekozen systeem: {basisprijs['systeem']}")
    print(f"Oppervlakte (m²): {basisprijs['oppervlakte']}")
    print(f"Aantal ruimtes: {basisprijs['ruimtes']}")
    print(f"Basisprijs: €{basisprijs['basis']}\n")

    print("Extra’s:\n")

    totaal_extra = 0

    for e in extra_opties:
        if e["type"] == "meerwerk":
            print(f" * {e['naam']} — {e['uren']} uur → €{e['prijs']}")
            totaal_extra += e["prijs"]
            continue

        if e["type"] == "durakorrel":
            print(f" * Durakorrel (+{e['p_m2']}/m² → €{e['prijs']} op {e['oppervlakte']} m²)")
            totaal_extra += e["prijs"]
            continue

        if e.get("p_m2", 0) > 0:
            toeslag = round(e["p_m2"] * basisprijs["oppervlakte"], 2)
            totaal_extra += toeslag
            print(f" * {e['naam']} (+{e['p_m2']}/m² → €{toeslag})")
            continue

        if e.get("prijs", 0) > 0:
            print(f" * {e['naam']} (+€{e['prijs']})")
            totaal_extra += e["prijs"]
            continue

    totaal = basisprijs["basis"] + totaal_extra

    print(f"\nTotaalprijs: €{totaal}")
    print("\n==============================================")
    input("\nDruk op Enter om af te sluiten...")


# -------------------------------------------------------
# START
# -------------------------------------------------------
if __name__ == "__main__":
    main()
