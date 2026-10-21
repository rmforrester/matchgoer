import { test } from "node:test";
import assert from "node:assert/strict";
import { eligibleAttendanceFixture, isFutureAttendanceDate, localAttendanceToday } from "./attendance-eligibility.ts";
const now = new Date("2026-10-20T15:00:00Z");
test("only completed past fixtures qualify, never elapsed scheduled/cancelled/live matches", () => {
 for (const status of ["FT", "AET", "PEN"]) assert.equal(eligibleAttendanceFixture({status,fixture_date:"2026-08-01T14:00:00Z"},11,now),true);
 for (const status of ["NS","TBD","PST","CANC","ABD","AWD","WO","HT","SUSP",null]) assert.equal(eligibleAttendanceFixture({status,fixture_date:"2026-08-01T14:00:00Z"},11,now),false);
 assert.equal(eligibleAttendanceFixture({status:"FT",fixture_date:"2026-10-25T14:00:00Z"},11,now),false);
 assert.equal(eligibleAttendanceFixture({status:"FT",fixture_date:"unknown"},11,now),false);
});
test("native date maximum and manual guard follow the local day, including UTC boundaries", () => {
 const previous = process.env.TZ;
 try {
  for (const [zone, instant, today] of [["America/New_York","2026-10-21T01:30:00Z","2026-10-20"],["Pacific/Auckland","2026-10-20T15:30:00Z","2026-10-21"],["UTC","2026-10-20T23:59:00Z","2026-10-20"]]) {
   process.env.TZ=zone;
   const clock=new Date(instant);
   assert.equal(localAttendanceToday(clock),today);
   assert.equal(isFutureAttendanceDate(today,clock),false);
   assert.equal(isFutureAttendanceDate("2099-01-01",clock),true);
   assert.equal(isFutureAttendanceDate("",clock),false);
   assert.equal(isFutureAttendanceDate("1999-01-01",clock),false);
  }
 } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ=previous; }
});
