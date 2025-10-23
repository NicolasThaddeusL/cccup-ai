(() => {
  // ======== Config ========
  const API_BASE = (window.API_BASE || "").trim(); // if "", same-origin
  const INPUT_LIMIT = Number(window.INPUT_LIMIT || 350);

  // ======== DOM ========
  const elMessages = document.getElementById("messages");
  const elInput = document.getElementById("chat-input");
  const elSend = document.getElementById("btn-send");
  const elCounter = document.getElementById("char-counter");
  const btnTheme = document.getElementById("toggle-theme");
  const root = document.body;

  // ======== State ========
  const state = {
    messages: [
      { role: "assistant", content: "Halo! Saya **CCCC.AI**. Tanyakan apa pun tentang CC Cup XL (cccup.id)." }
    ],
    loading: false
  };

  // ======== Rendering ========
  function bubble(role, html) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "right" : "left");
    const b = document.createElement("div");
    b.className = "bubble " + (role === "user" ? "bubble-user" : "bubble-bot");
    b.innerHTML = html;
    wrap.appendChild(b);
    return wrap;
  }

  function escapeHTML(s) {
    return (s || "").replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  }

  // very small markdown (bold + bullets)
  function liteMarkdown(s) {
    let out = escapeHTML(s || "");
    out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // bullets: lines starting with - or *
    out = out.replace(/(^|\n)[*-]\s+(.+)/g, (_m, p1, p2) => `${p1}• ${p2}`);
    out = out.replace(/\n/g, "<br>");
    return out;
  }

  function render() {
    elMessages.innerHTML = "";
    state.messages.forEach(m => elMessages.appendChild(bubble(m.role, liteMarkdown(m.content))));
    if (state.loading) {
      const t = document.createElement("div");
      t.className = "typing bubble bubble-bot";
      t.textContent = "CCCC.AI sedang mengetik…";
      elMessages.appendChild(t);
    }
    elMessages.scrollTo({ top: elMessages.scrollHeight, behavior: "smooth" });
  }

  // ======== Char counter ========
  function updateCounter() {
    if (!elInput) return;
    if (elInput.value.length > INPUT_LIMIT) elInput.value = elInput.value.slice(0, INPUT_LIMIT);
    elCounter.textContent = `${elInput.value.length} / ${INPUT_LIMIT} characters`;
    autoGrow();
  }

  // ======== Auto-resize textarea (nice UX) ========
  function autoGrow() {
    elInput.style.height = "auto";
    elInput.style.height = Math.min(160, elInput.scrollHeight) + "px";
  }

  // ======== Send ========
  async function send() {
    const text = (elInput.value || "").trim();
    if (!text || state.loading) return;

    state.messages.push({ role: "user", content: text });
    elInput.value = "";
    updateCounter();
    state.loading = true;
    render();

    try {
      const url = (API_BASE || "") + "/v1/chat/completions";

      // Keep only the last 12 messages to reduce payload
      const history = state.messages.slice(1); // omit initial bot greeting
      const last12 = history.slice(-12);

      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: last12 })
      });
      if (!resp.ok) throw new Error(`API ${resp.status}: ${await resp.text()}`);
      const data = await resp.json();
      const answer = data?.content
        || data?.choices?.[0]?.message?.content
        || "Maaf, respons kosong.";
      state.messages.push({ role: "assistant", content: answer });
    } catch (err) {
      console.error(err);
      state.messages.push({
        role: "assistant",
        content: "Maaf, terjadi kesalahan saat menghubungi server."
      });
    } finally {
      state.loading = false;
      render();
    }
  }

  // ======== Events ========
  elInput.addEventListener("input", updateCounter);
  elInput.addEventListener("keydown", (e) => {
    // Don’t send while composing IME text
    if (e.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  elSend.addEventListener("click", send);
  updateCounter();
  render();

  // ======== Theme toggle ========
  if (localStorage.getItem("theme") === "dark") {
    root.classList.add("theme-dark");
    btnTheme.textContent = "☀️";
  }
  btnTheme.addEventListener("click", () => {
    root.classList.toggle("theme-dark");
    const dark = root.classList.contains("theme-dark");
    btnTheme.textContent = dark ? "☀️" : "🌙";
    localStorage.setItem("theme", dark ? "dark" : "light");
  });
})();
