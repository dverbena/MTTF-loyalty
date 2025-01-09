function setCookie(name, value, days) {
    const d = new Date();
    d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
    document.cookie = `${name}=${value};expires=${d.toUTCString()};path=/`;
}

// Function to get a cookie by name
function getCookie(name) {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.startsWith(`${name}=`)) {
            return cookie.substring(name.length + 1);
        }
    }
    return null;
}

// Initialize Camera (Lazy Load)
const initializeCamera = () => {
    if (!AppState.cameraInitialized) {
        // Lazy load the Html5Qrcode library
        const script = document.createElement('script');
        script.src = "https://unpkg.com/html5-qrcode";
        document.body.appendChild(script);

        script.onload = () => {
            Html5Qrcode.getCameras()
                .then((devices) => {
                    const dropdown = document.getElementById('cameraDropdown');
                    
                    if (devices && devices.length) {                        
                        // Get saved camera ID from cookie
                        const savedCameraId = getCookie('selectedCamera');
    
                        // Populate dropdown and set default selection
                        devices.forEach((device, index) => {
                            const option = document.createElement('option');
                            option.value = device.id;
                            option.textContent = device.label || `Camera ${index + 1}`;
                            dropdown.appendChild(option);
                        });
    
                        // Set dropdown to saved camera or first option
                        if (savedCameraId && devices.some(d => d.id === savedCameraId)) {
                            dropdown.value = savedCameraId;
                            AppState.deviceId = savedCameraId;
                        } else {
                            dropdown.value = devices[0].id;
                            AppState.deviceId = devices[0].id;
                        }
    
                        // Save initial selection to cookie
                        setCookie('selectedCamera', cameraId, 30);
    
                        // Handle dropdown change event
                        dropdown.addEventListener('change', (event) => {
                            AppState.deviceId = event.target.value;
                            setCookie('selectedCamera', cameraId, 30); // Save selected camera to cookie
                        });
                        
                        AppState.html5QrcodeScanner = new Html5Qrcode("qr-reader");
                        AppState.cameraInitialized = true;

                        startScan();
                    }
                })
                .catch((err) => alert(`Camera initialization error: ${err}`));
        };

        script.onerror = () => { alert("Failed to load QR scanner library. Please try again later."); };
    }
    else
        startScan();
};

// Handle QR Code Scan
const handleScan = (decodedText) => {
    console.log("Scanned QR Code:", decodedText);

    AppState.html5QrcodeScanner.stop().then(() => {        
        $.ajax({
            type: 'GET',
            url: `accesses/reward_due_qr/${decodedText}`,
            success: function (responseReward) {//sendRewardMessageToCustomersPage
                $.ajax({
                    type: 'POST',
                    url: 'accesses/add',
                    contentType: 'application/json',
                    data: JSON.stringify({ qr_code: decodedText }),
                    success: function (responseAdd) {
                        if(responseReward.reward_due) sendRewardMessageToCustomersPage();
                        sendMessageToCustomersPage(`$Check in di {responseAdd.customer.name} ${responseAdd.customer.last_name} riuscito!`);

                        navigateTo('customers');
                    },
                    error: function (xhr) {
                        const errorMessage = xhr.responseJSON?.details || xhr.responseText || "Errore generico";
                        $('#error-message').text(errorMessage).show();
        
                        setTimeout(() => {
                            $('#error-message').fadeOut();
                            startScan(); // Restart scanning
                        }, 1000);
                    },
                });
            },
            error: function (xhr) {
                const errorMessage = xhr.responseJSON?.details || xhr.responseText || "Errore generico";
                $('#error-message').text(errorMessage).show();

                setTimeout(() => {
                    $('#error-message').fadeOut();
                    startScan(); // Restart scanning
                }, 1000);
            },
        });        
    }).catch((err) => alert(`Failed to stop scanner: ${err}`));
};