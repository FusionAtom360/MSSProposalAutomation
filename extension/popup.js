function updateStatus() {

    chrome.storage.local.get(
        "status",
        result => {

            const s = result.status || {};

            document.getElementById("status").innerHTML = `

                <p>
                <b>Extension:</b>
                ${s.active ? "Running" : "Waiting"}
                </p>

                <p>
                <b>Solargraf Page:</b>
                <br>
                ${s.page || "Not detected"}
                </p>

                <p>
                <b>Token:</b>
                ${s.tokenFound ? "Found" : "Missing"}
                </p>

                <p>
                <b>Python Connection:</b>
                ${s.pythonConnected ? "Connected" : "Unknown"}
                </p>

                <p>
                <b>Last Sent:</b>
                ${s.lastSent || "Never"}
                </p>

            `;
        }
    );
}


document
    .getElementById("refresh")
    .addEventListener(
        "click",
        updateStatus
    );


updateStatus();
