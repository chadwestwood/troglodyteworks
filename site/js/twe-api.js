async function apiRequest(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const csrfHeaders = method === "GET" || method === "HEAD" ? {} : { "X-TWE-CSRF": "1" };
  const response = await fetch(`/api/v1${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaders,
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = data.error || { code: "INTERNAL_ERROR", message: "Request failed." };
    throw Object.assign(new Error(error.message), { code: error.code, status: response.status });
  }
  return data;
}

async function requireCurrentUser() {
  try {
    const data = await apiRequest("/auth/me");
    document.querySelectorAll("[data-current-user]").forEach((node) => {
      node.textContent = data.user.display_name;
    });
    revealAdminLinks().catch(() => {});
    return data.user;
  } catch (error) {
    window.location.href = "/auth/sign-in.html";
    return null;
  }
}

async function revealAdminLinks() {
  const links = document.querySelectorAll("[data-admin-link]");
  if (!links.length) {
    return;
  }
  const data = await apiRequest("/account/identities");
  links.forEach((link) => {
    link.hidden = !data.admin?.available;
  });
}

function setText(selector, value) {
  const node = document.querySelector(selector);
  if (node) {
    node.textContent = value ?? "";
  }
}

function showError(message) {
  const node = document.querySelector("[data-error]");
  if (node) {
    node.textContent = message;
    node.hidden = false;
  }
}

function clearNode(node) {
  if (node) {
    node.replaceChildren();
  }
}

function createTextElement(tagName, text, className) {
  const node = document.createElement(tagName);
  if (className) {
    node.className = className;
  }
  node.textContent = text ?? "";
  return node;
}

function createResourceRow(title, detail, trailingText, options = {}) {
  const row = document.createElement(options.href ? "a" : "div");
  row.className = "resource-row";
  if (options.href) {
    row.href = options.href;
  }

  const content = document.createElement("span");
  content.appendChild(createTextElement("strong", title));
  if (detail) {
    content.appendChild(createTextElement("small", detail));
  }
  row.appendChild(content);

  if (trailingText) {
    row.appendChild(createTextElement("span", trailingText));
  }
  return row;
}

function remember(key, value) {
  if (value) {
    window.localStorage.setItem(key, value);
  }
}

function recall(key) {
  return window.localStorage.getItem(key);
}

async function signOut() {
  await apiRequest("/auth/logout", { method: "POST" });
  window.location.href = "/auth/sign-in.html";
}

document.querySelectorAll("[data-sign-out]").forEach((button) => {
  button.addEventListener("click", () => signOut().catch(() => {
    window.location.href = "/auth/sign-in.html";
  }));
});
