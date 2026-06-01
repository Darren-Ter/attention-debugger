const taskInput = document.getElementById("current-task");
const saveButton = document.getElementById("save");
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

async function loadTask() {
  const stored = await chrome.storage.local.get(["currentTask"]);
  taskInput.value = stored.currentTask || "";
}

saveButton.addEventListener("click", async () => {
  await chrome.storage.local.set({ currentTask: taskInput.value.trim() });
  chrome.runtime.sendMessage({ type: "record_current_tab" });
  showStatus("Task saved.");
});

snapshotButton.addEventListener("click", async () => {
  chrome.runtime.sendMessage({ type: "record_current_tab" }, (response) => {
    if (chrome.runtime.lastError || !response || response.ok !== true) {
      showStatus("Snapshot failed. Check native host install.");
      return;
    }
    showStatus("Snapshot recorded.");
  });
});

loadTask();
