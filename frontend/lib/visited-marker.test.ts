import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as design from "./mapMarkerDesign.ts";

const compiled = { exports: {} };
const code = ts.transpileModule(readFileSync(new URL("../app/components/groundMarkerIcon.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText;
vm.runInNewContext(code, { module: compiled, exports: compiled.exports, require: (name: string) => name === "leaflet" ? { divIcon: (options: unknown) => options } : design });
const { createGroundMarkerIcon } = compiled.exports as { createGroundMarkerIcon: (visited: boolean, selected: boolean, signal: string) => { html: string; iconSize: number[] } };
test("rendered visited check survives selection and independent editorial gold", () => {
  for (const signal of ["standard", "classic", "scenic", "rivalry", "cup", "international"]) {
    for (const selected of [false, true]) {
      const plain = createGroundMarkerIcon(false, selected, signal);
      const visited = createGroundMarkerIcon(true, selected, signal);
      assert.doesNotMatch(plain.html, /data-visited-check/);
      assert.match(visited.html, /data-visited-check="true"/);
      assert.match(visited.html, new RegExp(`fill="${signal === "standard" ? "#174A32" : "#D6AA18"}"`));
      assert.equal(visited.iconSize.join(","), "44,44");
    }
  }
});
