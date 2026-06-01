const HOST_NAME = "com.attentiondebugger.host";

let lastUrlByTab = new Map();

function nowIso() {
  return new Date().toISOString();
}

function domainFromUrl(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

function sendNative(message) {
  chrome.runtime.sendNativeMessage(HOST_NAME, message, (response) => {
    if (chrome.runtime.lastError) {
      console.warn("Attention Debugger native host error:", chrome.runtime.lastError.message);
      return;
    }
    if (!response || response.ok !== true) {
      console.warn("Attention Debugger native host rejected event:", response);
    }
  });
}

async function recordTabEvent(eventType, tab) {
  if (!tab || !tab.url || tab.url.startsWith("chrome://")) {
    return;
  }

  const event = {
    source: "chrome-extension",
    event_type: eventType,
    occurred_at: nowIso(),
    url: tab.url,
    domain: domainFromUrl(tab.url),
    title: tab.title || "",
    tab_id: tab.id,
    window_id: tab.windowId
  };

  sendNative({ type: "event", event });
}

async function recordActiveTab(eventType = "tab_activated") {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (tabs.length > 0) {
    await recordTabEvent(eventType, tabs[0]);
  }
}

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId);
  await recordTabEvent("tab_activated", tab);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!tab.active || !changeInfo.url) {
    return;
  }

  const previousUrl = lastUrlByTab.get(tabId);
  lastUrlByTab.set(tabId, changeInfo.url);

  if (previousUrl !== changeInfo.url) {
    await recordTabEvent("tab_url_changed", tab);
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    return;
  }
  await recordActiveTab("window_focused");
});

chrome.idle.setDetectionInterval(60);
chrome.idle.onStateChanged.addListener((state) => {
  sendNative({
    type: "event",
    event: {
      source: "chrome-extension",
      event_type: "idle_state_changed",
      occurred_at: nowIso(),
      idle_state: state
    }
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "record_current_tab") {
    recordActiveTab("manual_snapshot")
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }
});
