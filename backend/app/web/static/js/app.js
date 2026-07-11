/* FamilySafety — frontend utility bundle
 * Toast (P5), mobile sidebar, client-side form validation (P3),
 * keyboard a11y (K), skeleton loader (S). Plain ES2017. */
(function () {
  "use strict";

  // ==== Toast ============================================================
  let stack = null;
  function ensureStack() {
    stack = stack || document.getElementById("toastStack");
    return stack;
  }
  function showToast(kind, msg, ms) {
    const host = ensureStack();
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast toast-" + (kind || "info");
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.textContent = msg;
    // Click to dismiss (K3).
    el.style.cursor = "pointer";
    el.title = "点击关闭";
    el.addEventListener("click", () => dismiss(el));
    host.appendChild(el);
    const ttl = ms || (kind === "error" ? 5000 : 3000);
    const timer = setTimeout(() => dismiss(el), ttl);
    el.dataset.timer = String(timer);
  }
  function dismiss(el) {
    clearTimeout(Number(el.dataset.timer));
    if (el.classList.contains("is-leaving")) return;
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 220);
  }
  window.showToast = showToast;
  window.dismissToast = dismiss;

  // Parse a flash via cookie / htmx header.
  document.addEventListener("htmx:afterRequest", function (e) {
    const xhr = e.detail && e.detail.xhr;
    if (!xhr) return;
    const toastHeader = xhr.getResponseHeader("X-Flash-Toast");
    if (toastHeader) {
      try {
        const parts = toastHeader.split("|");
        showToast(parts[0] || "info", decodeURIComponent(parts.slice(1).join("|") || ""));
      } catch (_) { /* ignore */ }
    }
  });

  // ==== Sidebar toggle (mobile) =========================================
  document.addEventListener("click", function (e) {
    const t = e.target.closest("[data-sidebar-toggle]");
    if (!t) return;
    const sb = document.getElementById("sidebar");
    if (sb) sb.classList.toggle("is-open");
  });

  // ==== Form validation (P3) =============================================
  function validateField(field) {
    const input = field.querySelector("input, select, textarea");
    if (!input) return true;
    input.setCustomValidity?.("");
    const v = (input.value || "").trim();
    const required = input.hasAttribute("required");
    const min = input.getAttribute("minlength");
    const max = input.getAttribute("maxlength");
    const minVal = input.getAttribute("min");
    const maxVal = input.getAttribute("max");
    let err = "";
    if (required && !v) err = "此项必填";
    else if (min && v.length < +min) err = "至少 " + min + " 个字符";
    else if (max && v.length > +max) err = "最多 " + max + " 个字符";
    else if (minVal !== null && v !== "" && Number(v) < +minVal) err = "不能小于 " + minVal;
    else if (maxVal !== null && v !== "" && Number(v) > +maxVal) err = "不能大于 " + maxVal;
    else if (input.pattern && v && !new RegExp("^" + input.pattern + "$").test(v)) err = "格式不正确";
    // Cross-field check: confirm_password must match new_password.
    if (!err && input.name === "confirm_password") {
      const root = input.form || field.closest("form");
      const other = root && root.querySelector('input[name="new_password"]');
      if (other && other.value && v !== other.value) err = "两次密码不一致";
    }
    const errEl = field.querySelector(".field-error");
    if (errEl && !errEl.id) errEl.id = "err-" + Math.random().toString(36).slice(2, 9);
    if (err) {
      field.classList.add("is-invalid");
      input.setAttribute("aria-invalid", "true");
      if (errEl) {
        input.setAttribute("aria-describedby", errEl.id);
        errEl.textContent = err;
      }
      return false;
    }
    field.classList.remove("is-invalid");
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
    if (errEl) errEl.textContent = "";
    return true;
  }

  document.addEventListener("input", function (e) {
    const field = e.target.closest(".field");
    if (field) validateField(field);
    // Re-validate the confirm-password field when the user types in new_password.
    if (e.target.name === "new_password") {
      const cp = e.target.form && e.target.form.querySelector('input[name="confirm_password"]');
      if (cp) {
        const cf = cp.closest(".field");
        if (cf) validateField(cf);
      }
    }
  }, true);

  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form || !form.matches("form")) return;
    let ok = true;
    form.querySelectorAll(".field").forEach((f) => {
      if (!validateField(f)) ok = false;
    });
    if (!ok) {
      e.preventDefault();
      showToast("error", "请检查表单中标红的字段");
      const firstBad = form.querySelector(".field.is-invalid input, .field.is-invalid select, .field.is-invalid textarea");
      if (firstBad) firstBad.focus();
    } else {
      const btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        const orig = btn.textContent;
        btn.textContent = "处理中…";
        setTimeout(() => { btn.disabled = false; btn.textContent = orig; }, 8000);
      }
    }
  }, true);

  // ==== Delete confirmation (members) ===================================
  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-confirm]");
    if (!btn) return;
    const msg = btn.getAttribute("data-confirm") || "确认操作?";
    if (!window.confirm(msg)) {
      e.preventDefault();
      e.stopImmediatePropagation();
    }
  }, true);

  // ==== Keyboard a11y (K) ================================================
  // Esc: close mobile sidebar / dismiss all toasts.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      const sb = document.getElementById("sidebar");
      if (sb && sb.classList.contains("is-open")) sb.classList.remove("is-open");
      if (stack) {
        stack.querySelectorAll(".toast").forEach((el) => dismiss(el));
      }
      // Close inline confirm dialogs are browser-handled; nothing more.
    }
    // Slash focuses first search-like input.
    if (e.key === "/" && !e.target.matches("input, select, textarea, [contenteditable]")) {
      const first = document.querySelector('input[type="search"], input[name="q"], input[name="query"]');
      if (first) {
        e.preventDefault();
        first.focus();
        first.select && first.select();
      }
    }
  }, true);

  // ==== Skeleton loader (S) ==============================================
  // Expose helper for templates that want to show a shimmer while a
  // htmx swap is in flight.
  window.fsShowSkeleton = function (target, label) {
    if (!target) return;
    target.classList.add("is-skeleton");
    if (!target.querySelector(".skeleton-shimmer")) {
      const sh = document.createElement("div");
      sh.className = "skeleton-shimmer";
      sh.setAttribute("aria-hidden", "true");
      sh.textContent = label || "";
      target.appendChild(sh);
    }
  };
  window.fsHideSkeleton = function (target) {
    if (!target) return;
    target.classList.remove("is-skeleton");
    const sh = target.querySelector(".skeleton-shimmer");
    if (sh) sh.remove();
  };

  // After every successful htmx swap, strip skeleton flags.
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail && e.detail.target) {
      e.detail.target.classList.remove("is-skeleton");
      e.detail.target.querySelectorAll && e.detail.target.querySelectorAll(".skeleton-shimmer")
        .forEach((n) => n.remove());
    }
  });
})();
