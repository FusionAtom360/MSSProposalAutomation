let status = {
    active: false,
    tokenFound: false,
    lastSent: null,
    page: null
};


chrome.runtime.onMessage.addListener(
    async (message) => {

        if (message.type === "SOLARGRAF_STATUS") {

            status = {
                ...status,
                ...message.data
            };

            await chrome.storage.local.set({
                status
            });
        }


        if (message.type === "SOLARGRAF_TOKEN") {

            status.tokenFound = true;
            status.lastSent = new Date().toLocaleString();
            status.active = true;

            await chrome.storage.local.set({
                status
            });


            fetch(
                "http://127.0.0.1:8765/token",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        token: message.token
                    })
                }
            )
            .then(() => {
                status.pythonConnected = true;
                chrome.storage.local.set({status});
            })
            .catch(() => {
                status.pythonConnected = false;
                chrome.storage.local.set({status});
            });
        }
    }
);
