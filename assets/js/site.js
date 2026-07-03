function fallbackCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  fallbackCopyText(text);
}

document.addEventListener("DOMContentLoaded", () => {
  const copyButtons = document.querySelectorAll("[data-copy-text]");

  copyButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy-text");
      const defaultLabel = button.getAttribute("data-default-label") || "Copy";
      const copiedLabel = button.getAttribute("data-copied-label") || "Copied";

      if (!text) {
        return;
      }

      try {
        await copyTextToClipboard(text);
        button.textContent = copiedLabel;
        button.classList.add("is-copied");
      } catch (error) {
        button.textContent = "Copy failed";
        console.error(error);
      }

      window.setTimeout(() => {
        button.textContent = defaultLabel;
        button.classList.remove("is-copied");
      }, 1800);
    });
  });
});
