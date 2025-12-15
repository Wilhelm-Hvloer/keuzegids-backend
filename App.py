from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
from typing import Any, Dict, List

app = FastAPI()

# =======================
# CORS
# =======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =======================
# KEUZEBOOM LADEN
# =======================
with open("keuzeboom.json", "r", encoding="utf-8") as f:
    KEUZEBOOM: List[Dict[str, Any]] = json.load(f)

# =======================
# HULPFUNCTIES
# =======================
def find_node(node_id: str) -> Dict[str, Any] | None:
    for node in KEUZEBOOM:
        if node.get("id") == node_id:
            return node
    return None


def extract_label(node: Dict[str, Any]) -> str:
    """
    Bepaalt het knop-label op basis van de next-node.
    """
    if node.get("label"):
        return node["label"]

    if node.get("answer"):
        return node["answer"]

    text = node.get("text", "")
    for prefix in ("Antw:", "Vrg:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    return text or node.get("id")


def normalize_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zorgt dat frontend altijd:
    - id
    - type
    - text
    - answers (afgeleid uit next-nodes)
    - next
    krijgt
    """
    answers: List[str] = []

    if node.get("type") == "vraag" and "next" in node:
        for next_id in node["next"]:
            next_node = find_node(next_id)
            if next_node:
                answers.append(extract_label(next_node))
            else:
                answers.append(next_id)

    return {
        "id": node.get("id"),
        "type": node.get("type"),
        "text": node.get("text"),
        "answers": answers,
        "next": node.get("next", []),
        # extra info voor vervolg
        "answer": node.get("answer"),
        "system": node.get("system"),
        "systems": node.get("systems"),
    }

# =======================
# START
# =======================
@app.get("/api/start")
def start():
    if not KEUZEBOOM:
        raise HTTPException(status_code=500, detail="Keuzeboom is leeg")

    return normalize_node(KEUZEBOOM[0])

# =======================
# NEXT
# =======================
class NextRequest(BaseModel):
    node_id: str
    choice: int


@app.post("/api/next")
def next_node(req: NextRequest):
    current_node = find_node(req.node_id)

    if not current_node:
        raise HTTPException(status_code=400, detail="Huidige node niet gevonden")

    if "next" not in current_node:
        raise HTTPException(status_code=400, detail="Node heeft geen vervolgstappen")

    if req.choice < 0 or req.choice >= len(current_node["next"]):
        raise HTTPException(status_code=400, detail="Ongeldige keuze-index")

    next_node_id = current_node["next"][req.choice]
    next_node = find_node(next_node_id)

    if not next_node:
        raise HTTPException(status_code=400, detail="Volgende node niet gevonden")

    return normalize_node(next_node)
