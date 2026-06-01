const snapshotButton = document.getElementById("snapshot");
const status = document.getElementById("status");

function showStatus(text) {
  status.textContent = text;
  setTimeout(() => {
    if (status.textContent === text) {
      status.textContent = "";
    }
  }, 2500);
}

snapshotButton.addEventListener("click", async () => {
  chrome.runtime.sendMessage({ type: "record_current_tab" }, (response) => {
    if (chrome.runtime.lastError || !response || response.ok !== true) {
      showStatus("Snapshot failed. Check native host install.");
      return;
    }
    showStatus("Snapshot recorded.");
  });
});
