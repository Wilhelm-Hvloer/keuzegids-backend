const API = "https://jouw-render-url.onrender.com";  // <-- pas dit later aan

let currentNode = null;

// Start de keuzegids
window.onload = () => {
    fetch(API + "/api/start")
        .then(r => r.json())
        .then(showNode);
};

function showNode(node) {
    currentNode = node;
    document.getElementById("input-box").classList.add("hidden");
    document.getElementById("system-list").classList.add("hidden");

    document.getElementById("question-text").innerText = node.text;

    let answersDiv = document.getElementById("answers");
    answersDiv.innerHTML = "";

    if (node.answers && node.answers.length > 0) {
        node.answers.forEach((a, i) => {
            let btn = document.createElement("button");
            btn.innerText = a;
            btn.onclick = () => submitAnswer(i);
            answersDiv.appendChild(btn);
        });
    }
}

function submitAnswer(i) {
    fetch(API + "/api/next", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            node_id: currentNode.node_id,
            choice: i
        })
    })
    .then(r => r.json())
    .then(handleNext);
}

function handleNext(node) {
    // systeemnode → prijs berekenen
    if (node.type === "systeem") {
        askForSurface(node.system);
        return;
    }

    // afweging → meerdere systemen
    if (node.type === "afw") {
        showSystemChoices(node);
        return;
    }

    showNode(node);
}

function askForSurface(system) {
    currentNode = { system };
    document.getElementById("question-text").innerText =
        "Voer oppervlakte in (m²):";

    let box = document.getElementById("input-box");
    box.classList.remove("hidden");
    box.querySelector("input").value = "";
    box.querySelector("input").placeholder = "Bijv. 120";

    document.getElementById("answers").innerHTML = "";
}

function submitInput() {
    let val = document.getElementById("input-field").value;

    if (!currentNode.ruimtes) {
        currentNode.oppervlakte = parseFloat(val);
        askRooms();
        return;
    }

    currentNode.ruimtes = parseInt(val);
    calculatePrice();
}

function askRooms() {
    document.getElementById("question-text").innerText =
        "Aantal ruimtes?";
    document.getElementById("input-field").value = "";
    document.getElementById("input-field").placeholder = "1, 2 of 3";
}

function calculatePrice() {
    fetch(API + "/api/price", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            system: currentNode.system,
            oppervlakte: currentNode.oppervlakte,
            ruimtes: currentNode.ruimtes
        })
    })
    .then(r => r.json())
    .then(showPrice);
}

function showPrice(data) {
    let p = document.getElementById("price-box");

    document.getElementById("p-system").innerText = data.systeem;
    document.getElementById("p-opp").innerText = data.oppervlakte;
    document.getElementById("p-r").innerText = data.ruimtes;
    document.getElementById("p-staffel").innerText = data.staffle;
    document.getElementById("p-m2").innerText = data.prijs_m2;
    document.getElementById("p-totaal").innerText = data.basis;

    p.classList.remove("hidden");
}
