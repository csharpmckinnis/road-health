console.log("JavaScript Loaded");

// CONSTANTS

// // WEBSOCKET-RELATED CONSTANTS
const wsUrl = (window.location.protocol === "https:" ? "wss" : "ws") + "://" + window.location.host + "/ws";


// // BUTTONS
const btnStartMonitoring = document.getElementById("btn-start-monitoring");
const btnStopMonitoring = document.getElementById("btn-stop-monitoring");
const btnCheckForChanges = document.getElementById("btn-check-for-changes");
const btnSaveNewAiInstructions = document.getElementById("btn-save-new-ai-instructions");

// // TEXT INPUTS
const inputAiInstructions = document.getElementById("input-ai-instructions");

// // STATUS SECTIONS
// // // PROGRAM
const valueProgramStatus = document.getElementById("badge-program-status");
// // // VIDEO PROCESSING CARD SECTION
const valueVideoStatus = document.getElementById("value-video-status");
const videoSection = document.getElementById("subsection-video-cards");
// // // STATUS UPDATE FEED
const subsectionStatusFeed = document.getElementById("subsection-status-feed")
// // // WORK ORDER CARD SECTION
const woSection = document.getElementById("subsection-wo-cards");


// UTILITY FUNCTIONS
// // HTTP FUNCTIONS
// // // SEND HTTP REQUEST
async function sendHttpRequest(endpoint, method = "POST", body = null) {
    try {
        const response = await fetch(endpoint, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: body ? JSON.stringify(body) : null
        });

        const data = await response.json();
        console.log(`Response from ${endpoint}:`, data);
    } catch (error) {
        console.error(`Error sending request to ${endpoint}:`, error);
    }
}

// // WEBSOCKET FUNCTIONS

// // // DISPLAY TEMP BADGE FOR 1 SECOND
function showTempBadge(message) {
    const badge = document.getElementById("badge-box-check");
    
    // Wait to show badge for 1 second (until actual 0)
    
    badge.hidden = false;
    
    
    // Hide badge after 1 second
    setTimeout(() => {
        badge.hidden = true;
    }, 1000);
}

// // // UPDATE PROGRAM STATUS
function updateProgramStatus(updateData) {
    if (updateData.status === "Active") {
        valueProgramStatus.classList.remove("bg-warning");
        valueProgramStatus.classList.add("bg-primary");
        countdown = `(${updateData.details.countdown || null})`;
        valueProgramStatus.textContent = `${updateData.status} ${countdown}`;
    } else if (updateData.status === "Processing") {
        valueProgramStatus.classList.remove("bg-primary");
        valueProgramStatus.classList.add("bg-success");
        valueProgramStatus.textContent = "Processing (Monitoring Paused)";
    } else {
        valueProgramStatus.classList.remove("bg-primary");
        valueProgramStatus.classList.add("bg-warning");
        valueProgramStatus.textContent = updateData.status;
    }
}

// // // ADD STATUS UPDATE CARD TO FEED
function addStatusUpdateCard(updateData) {
    
    // Create a new card
    const entry = document.createElement("div");
    entry.className = "card feed condensed";  // Add CSS later to make it look nice

    // Fill in the details from JSON
    entry.innerHTML = `
        <div class="card-body">
            <p class="card-text small">
                <span class="text-secondary">${new Date().toLocaleTimeString()}</span> | 
                <span class="text-muted">${updateData.source}</span><br>
                ${updateData.message}
            </p>
        </div>
    `;

    // Append the new status update
    subsectionStatusFeed.prepend(entry);

    // Auto-scroll to the latest update
    subsectionStatusFeed.scrollTop = 0;
}

// // // UPDATE OR ADD VIDEO PROCESSING CARD
function updateVideoProcessingCard(updateData) {
    videoSection.hidden = false;
    
    if (!updateData.details || !updateData.details.video_file) {
        console.warn("Invalid video update data:", updateData);
        return;
    }

    // Extract video filename
    const videoFile = updateData.details.video_file;
    const progress = updateData.details.progress || "N/A";
    const stage = updateData.details.stage || "Unknown";
    const status = updateData.status || "Pending";

    let activeModifiers = "";
    let badgeModifiers = "";

    if (updateData.status == "In Progress") {
        activeModifiers = "progress-bar-striped progress-bar-animated";
        badgeModifiers = "bg-primary";
    } else if (updateData.status === "Complete") {
        activeModifiers = "bg-success";
        badgeModifiers = "bg-success";
    } else {
        activeModifiers = "bg-secondary";
        badgeModifiers = "bg-secondary";
    }



    // Check if a card for this video already exists
    let existingCard = document.getElementById(`video-${videoFile}`);

    if (existingCard) {
        // ✅ Update existing card content
        existingCard.innerHTML = `
            <h4 class="card-header">${videoFile}</h4>
            <div class="card-body">
                <h2 class="card-title"><em>${status}</em></h2>
                <p class="card-text badge ${badgeModifiers}">${stage}</p>
                    <div id="video-progress-bar class="progress progress-bar ${activeModifiers}" role="progressbar" style="width: ${progress};">
                        ${progress}
                    </div>
            </div>
        `;
    } else {
        // ✅ Create a new card if it doesn't exist
        const newCard = document.createElement("div");
        newCard.className = "card col-md-6";
        newCard.id = `video-${videoFile}`;


        newCard.innerHTML = `
            <h4 class="card-header">${videoFile}</h4>
            <div class="card-body">
                <h2 class="card-title"><em>${status}</em></h2>
                <p class="card-text badge ${badgeModifiers}">${stage}</p>
                    <div id="video-progress-bar class="progress progress-bar ${activeModifiers}" role="progressbar" style="width: ${progress};">
                        ${progress}
                    </div>
            </div>
        `;

        videoSection.appendChild(newCard);
    }
}

// // // UPDATE OR ADD WORK ORDER PROCESSING CARD
function updateWorkOrderProcessingCard(updateData) {
    woSection.hidden = false;
    
    const existingCard = document.getElementById(`wo-${updateData.details.work_order_id}`);
    let imageHTML = "";
    if (updateData.details.image_base64) {
        imageHTML = `<img src="data:image/jpeg;base64,${updateData.details.image_base64}" 
        alt="Image of the detected issue"
        class="card-img-top"
        style="width: 300px; height: 130px;"
        >`;
    }

    if (existingCard) {
        // Update existing card
        existingCard.innerHTML = `
            <h4 class="card-header">Work Order Created</h4>
            <div class="card-body">
                <h2 class="card-title"><em>${updateData.message}</em></h2>
                ${imageHTML}
                <p class="card-text"><em>Id: ${updateData.details.work_order_id}</em></p>
                <p class="card-text">${updateData.details.ai_analysis}</p>
            </div>
        `;

    } else {
        // Create a new card
        const newCard = document.createElement("div");
        newCard.className = "card col-md-6";
        newCard.id = `wo-${updateData.details.video_file}`;

        newCard.innerHTML = `
            <h4 class="card-header">Work Order Created</h4>
            <div class="card-body">
                <h2 class="card-title"><em>${updateData.message}</em></h2>
                ${imageHTML}
                <p class="card-text"><em>Id: ${updateData.details.work_order_id}</em></p>
                <p class="card-text">${updateData.details.ai_analysis}</p>
            </div>
        `;

        woSection.appendChild(newCard);
    }
}


// // // GET WEBSOCKET URL
function getWebSocketUrl(endpoint) {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    return `${protocol}://${host}${endpoint}`;
}


// WEBSOCKET CONNECTIONS
const statusFeedSocket = new WebSocket(wsUrl + "/status-updates");
statusFeedSocket.onopen = () => {
    console.log("Status Feed WebSocket Connected");
};
statusFeedSocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("Status Feed WebSocket Message:", data);

    // Route to html elements depending on the data.type
    if (data.type === "Feed") {
        addStatusUpdateCard(data);
    } else if (data.type === "Temp") {
        showTempBadge(data.message);
    } else if (data.type === "Video") {
        if (data.level === "Section") {
            valueVideoStatus.textContent = data.message;
        } else {
            updateVideoProcessingCard(data);
        }
    } else if (data.type == "WorkOrder") {
        updateWorkOrderProcessingCard(data);
    } else if (data.type === "Program") {
        updateProgramStatus(data);
    } else {
        console.warn("Received unknown update type:", data);
    }

};

// EVENT LISTENERS FOR BUTTONS
btnStartMonitoring.addEventListener("click", () => {
    console.log("Start Monitoring Button Clicked");
    sendHttpRequest("/start-monitoring");
    updateData = {"message": "Monitoring Started", "source": "Web UI button click: 'btnStartMonitoring'"};
    addStatusUpdateCard(updateData);
});

btnStopMonitoring.addEventListener("click", () => {
    console.log("Stop Monitoring Button Clicked");
    sendHttpRequest("/stop-monitoring");
    updateData = {"message": "Monitoring Stopped", "source": "Web UI button click: 'btnStopMonitoring'"};
    addStatusUpdateCard(updateData);
});

btnCheckForChanges.addEventListener("click", () => {
    console.log("Check for Changes Button Clicked");
    sendHttpRequest("/video-check");
    updateData = {"message": "Video Check Requested", "source": "Web UI button click: 'btnCheckForChanges'"};
    addStatusUpdateCard(updateData);
});

btnSaveNewAiInstructions.addEventListener("click", () => {
    console.log("Save New AI Instructions Button Clicked");
    sendHttpRequest("/save-ai-instructions", "POST", { instructions: inputAiInstructions.value });
    updateData = {"message": "AI Instructions Updated", "source": "Web UI button click: 'btnSaveNewAiInstructions'"};
    addStatusUpdateCard(updateData);
});

// // TEST BUTTON EVENT LISTENERS
const btnProgramTest = document.getElementById("btn-test-program-status");
const btnVideoTest = document.getElementById("btn-test-video-status");
const btnWOTest = document.getElementById("btn-test-wo-status");
const btnFeedTest = document.getElementById("btn-test-feed-status");

btnProgramTest.addEventListener("click", () => {
    console.log("Test Program Status Button Clicked");
    sendHttpRequest("/test-program-status");
});

btnVideoTest.addEventListener("click", () => {
    console.log("Test Video Status Button Clicked");
    sendHttpRequest("/test-video-status");
});

btnWOTest.addEventListener("click", () => {
    console.log("Test Work Order Status Button Clicked");
    sendHttpRequest("/test-wo-status");
});

btnFeedTest.addEventListener("click", () => {
    console.log("Test Feed Status Button Clicked");
    sendHttpRequest("/test-feed-status");
});