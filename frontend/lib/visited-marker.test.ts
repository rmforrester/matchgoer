import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as design from "./mapMarkerDesign.ts";

const compiled = { exports: {} };
const code = ts.transpileModule(readFileSync(new URL("../app/components/groundMarkerIcon.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText;
vm.runInNewContext(code, { module: compiled, exports: compiled.exports, require: (name: string) => name === "leaflet" ? { divIcon: (options: unknown) => options } : design });
const { createGroundMarkerIcon, markerSignalSvg, markerKeyIconHtml } = compiled.exports as { markerSignalSvg: (signal: string, stroke: string) => string; markerKeyIconHtml: (signal: string) => string; createGroundMarkerIcon: (visited: boolean, selected: boolean, signal: string, highlighted: boolean) => { html: string; iconSize: number[] } };
test("rendered visited check survives selection and independent editorial gold", () => {
  for (const signal of ["standard", "classic", "scenic", "rivalry", "cup", "international"]) {
    for (const selected of [false, true]) {
    for (const highlighted of [false, true]) {
      const plain = createGroundMarkerIcon(false, selected, signal, highlighted);
      const visited = createGroundMarkerIcon(true, selected, signal, highlighted);
      assert.doesNotMatch(plain.html, /data-visited-check/);
      assert.match(visited.html, /data-visited-check="true"/);
      assert.match(visited.html, new RegExp(`fill="${highlighted ? "#D6AA18" : "#174A32"}"`));
      assert.match(visited.html, /stroke="#FFFFFF"/);
      assert.doesNotMatch(visited.html, /<g /);
      if (signal !== "standard") {
        assert.ok(plain.html.includes(markerSignalSvg(signal, highlighted ? "#171717" : "#FCFAF5")));
        assert.ok(!visited.html.includes(markerSignalSvg(signal, highlighted ? "#171717" : "#FCFAF5")));
        assert.match(markerKeyIconHtml(signal), /fill="#174A32"/);
        assert.ok(markerKeyIconHtml(signal).includes(markerSignalSvg(signal, "#FCFAF5")));
      }
      assert.equal(visited.iconSize.join(","), "44,44");
    }
    }
  }
});
