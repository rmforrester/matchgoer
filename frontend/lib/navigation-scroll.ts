// Explicit navigation/expansion only: never called by data refreshes.
let pendingFrame = 0;
function afterLayout(action: () => void) {
  window.cancelAnimationFrame(pendingFrame);
  pendingFrame = window.requestAnimationFrame(() => {
    pendingFrame = window.requestAnimationFrame(() => { pendingFrame = 0; action(); });
  });
  return () => window.cancelAnimationFrame(pendingFrame);
}
export function scrollPageToTop() {
  return afterLayout(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }));
}
export function scrollExpandedHeading(heading: HTMLElement) {
  afterLayout(() => {
    if (!heading.isConnected || heading.getAttribute("aria-expanded") === "false" ||
      (heading.tagName === "SUMMARY" && !(heading.parentElement as HTMLDetailsElement)?.open)) return;
    // Body padding resolves the native safe-area inset. Only pinned/sticky headers
    // currently covering the top obstruct content; ordinary web headers scroll away.
    let top = parseFloat(getComputedStyle(document.body).paddingTop) || 0;
    for (const header of document.querySelectorAll("header")) {
      const style = getComputedStyle(header), rect = header.getBoundingClientRect();
      if (["fixed", "sticky"].includes(style.position) && rect.top <= top && rect.bottom > top) top = rect.bottom;
    }
    const gap = (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16) / 2;
    window.scrollTo({ top: Math.max(0, window.scrollY + heading.getBoundingClientRect().top - top - gap), behavior: "instant" });
  });
}
