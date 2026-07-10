async function apiRequest(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
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
    return data.user;
  } catch (error) {
    window.location.href = "/auth/sign-in.html";
    return null;
  }
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
