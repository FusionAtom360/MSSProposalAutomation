const token = localStorage.getItem("access_token");


chrome.runtime.sendMessage({
    type: "SOLARGRAF_STATUS",
    data: {
        active: true,
        page: window.location.href,
        tokenFound: !!token
    }
});


if (token) {

    chrome.runtime.sendMessage({
        type: "SOLARGRAF_TOKEN",
        token: token
    });

}
