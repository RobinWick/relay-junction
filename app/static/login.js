document.getElementById("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("err");
  err.textContent = "";
  const res = await fetch("/api/login", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({passcode: document.getElementById("pc").value}),
  });
  if (res.ok) { location.href = "/" + (location.hash === "#demo" ? "#demo" : ""); return; }
  const body = await res.json().catch(() => ({}));
  err.textContent = body.detail || "Could not sign in.";
});
