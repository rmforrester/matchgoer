import { test } from "node:test";
import assert from "node:assert/strict";
import { eligibleAttendanceFixture, isFutureAttendanceDate } from "./attendance-eligibility.ts";
const now = new Date("2026-10-20T15:00:00Z");
test("only completed past fixtures qualify, never elapsed scheduled/cancelled/live matches", () => {
 for (const status of ["FT", "AET", "PEN"]) assert.equal(eligibleAttendanceFixture({status,fixture_date:"2026-08-01T14:00:00Z"},11,now),true);
 for (const status of ["NS","TBD","PST","CANC","ABD","AWD","WO","HT","SUSP",null]) assert.equal(eligibleAttendanceFixture({status,fixture_date:"2026-08-01T14:00:00Z"},11,now),false);
 assert.equal(eligibleAttendanceFixture({status:"FT",fixture_date:"2026-10-25T14:00:00Z"},11,now),false);
 assert.equal(eligibleAttendanceFixture({status:"FT",fixture_date:"unknown"},11,now),false);
});
test("future date guard follows the server UTC day, preserving today/past/undated history", () => {
 assert.equal(isFutureAttendanceDate("2026-10-21",now),true);
 for(const date of ["2026-10-20","1999-01-01",""]) assert.equal(isFutureAttendanceDate(date,now),false);
 assert.equal(isFutureAttendanceDate("2026-10-21",new Date("2026-10-20T23:30:00-04:00")),false);
});
