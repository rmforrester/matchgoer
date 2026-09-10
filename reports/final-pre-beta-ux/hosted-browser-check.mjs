const endpoint = await fetch("http://127.0.0.1:9223/json").then((r) => r.json());
const target = endpoint.find((item) => item.type === "page");
if (!target) throw new Error("No Chrome page target available");
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let id = 0;
const pending = new Map();
ws.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id); pending.delete(message.id);
    return message.error ? reject(new Error(message.error.message)) : resolve(message.result);
  }
};
const call = (method, params = {}) => new Promise((resolve, reject) => {
  const callId = ++id; pending.set(callId, { resolve, reject });
  ws.send(JSON.stringify({ id: callId, method, params }));
});
await call("Page.enable");
await call("Runtime.enable");
const checks = [];
for (const width of [320, 375, 390, 430]) {
  await call("Emulation.setDeviceMetricsOverride", { width, height: 1400, screenWidth: width, screenHeight: 1400, deviceScaleFactor: 1, mobile: true });
  for (const [name, url] of [
    ["fixture", "https://beta.matchgoer.com/fixture/1550123"],
    ["venue", "https://beta.matchgoer.com/venue/23102?teamId=492"],
    ["my-grounds-empty", "https://beta.matchgoer.com/my-football?tab=visited"],
    ["my-matchdays", "https://beta.matchgoer.com/my-football?tab=interested"],
  ]) {
    await call("Page.navigate", { url });
    await new Promise((resolve) => setTimeout(resolve, 2500));
    const result = await call("Runtime.evaluate", { returnByValue: true, expression: `(() => {
      const text = document.body.innerText;
      return {title: document.title, viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
        overflow: document.documentElement.scrollWidth > innerWidth,
        fixture: {why: text.includes('WHY THIS MATCH'), know: text.includes('KNOW THE MATCHDAY'), ground: text.includes('GROUND ESSENTIALS'), rollCall: text.includes('TERRACE ROLL CALL'), boardCopy: text.includes('Ask other supporters about the match, pubs, travel or the ground.')},
        venue: {whyGo: text.includes('WHY GO?'), wrappers: text.includes('KNOW BEFORE YOU GO') || text.includes('THE ESSENTIALS'), before: text.includes('BEFORE THE MATCH'), tickets: text.includes('TICKETS & ENTRY'), add: text.includes('ADD TO MY GROUNDS')},
        grounds: {empty: text.includes('NO GROUNDS RECORDED YET.'), direct: text.includes("Add somewhere you've been."), optionalReview: text.includes('A review is optional.')},
        matchdays: {empty: text.includes('YOUR MATCHDAY HISTORY STARTS HERE'), didYouGo: text.includes('DID YOU GO?'), past: text.includes('PAST MATCHDAYS')}
      };
    })()` });
    checks.push({ width, name, ...result.result.value });
  }
}
console.log(JSON.stringify(checks, null, 2));
ws.close();
