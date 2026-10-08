import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
let account = { authenticated: false, loading: true, profile: null as { username: string } | null, signOut: async () => {} };
const source = readFileSync(new URL("../app/components/Navigation.tsx", import.meta.url), "utf8");
const compiled = { exports: {} };
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
const dependencies: Record<string, unknown> = {
  "next/link": (props: Record<string, unknown>) => React.createElement("a", props),
  "next/image": (props: Record<string, unknown>) => React.createElement("img", props),
  "next/navigation": { usePathname: () => "/fixture/1", useRouter: () => ({}), useSearchParams: () => new URLSearchParams() },
  "./AuthProvider": { useAuth: () => account },
};
vm.runInNewContext(code, { module: compiled, exports: compiled.exports, require: (name: string) => dependencies[name] ?? require(name) });
const Navigation = (compiled.exports as { default: React.ComponentType }).default;

test("server navigation has a stable account placeholder across auth initialization states", () => {
  const states = [
    { authenticated: false, loading: true, profile: null },
    { authenticated: false, loading: false, profile: null },
    { authenticated: true, loading: false, profile: { username: "supporter" } },
  ];
  const outputs = states.map(state => {
    account = { ...account, ...state };
    const html = renderToStaticMarkup(React.createElement(Navigation));
    assert.match(html, />Account<\/span>/);
    assert.doesNotMatch(html, /Create account|Log out|@supporter/);
    assert.match(html, /href="\/my-football\?tab=interested"/);
    return html;
  });
  assert.equal(outputs[0], outputs[1]);
  assert.equal(outputs[1], outputs[2]);
});
