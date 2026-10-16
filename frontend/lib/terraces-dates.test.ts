import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { formatMatchDate, formatPublicationDate } from "./terraces-dates.ts";

test("unknown or invalid match dates are not invented", () => {
  for (const value of [null, undefined, "", "unknown", "2026-02-30", "2026-13-01"]) assert.equal(formatMatchDate(value), null);
  assert.equal(formatMatchDate("2026-10-01T00:30:00+02:00", "en-GB"), "1 Oct 2026");
  assert.equal(formatPublicationDate(null), null);
  assert.equal(formatPublicationDate("2026-10-01"), null);
});

test("calendar dates survive timezones, DST and year boundaries; publication uses viewer zone", () => {
  const source = `import {formatMatchDate,formatPublicationDate} from './lib/terraces-dates.ts';
    console.log(JSON.stringify({matches:['2026-10-01','2026-01-01','2026-03-08','2026-11-01','2024-02-29'].map(x=>formatMatchDate(x,'en-GB')),published:formatPublicationDate('2026-10-01T00:30:00Z','en-GB')}));`;
  for (const [zone, published] of [["America/New_York", "30 Sept 2026"], ["America/Los_Angeles", "30 Sept 2026"], ["Europe/London", "1 Oct 2026"], ["Asia/Tokyo", "1 Oct 2026"], ["Pacific/Kiritimati", "1 Oct 2026"]]) {
    const result = spawnSync(process.execPath, ["--experimental-strip-types", "--input-type=module", "-e", source], { env: { ...process.env, TZ: zone }, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout), { matches: ["1 Oct 2026", "1 Jan 2026", "8 Mar 2026", "1 Nov 2026", "29 Feb 2024"], published }, zone);
  }
});
