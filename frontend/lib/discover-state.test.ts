import test from "node:test";
import assert from "node:assert/strict";
import { readDiscoverState, writeDiscoverState, DISCOVER_FRESH_MS, type DiscoverState } from "./discover-state.ts";
const appliedSearch = { latitude: 51.5, longitude: -0.1, locationName: "London", radius: 25,
 startDate: "2026-10-28", endDate: "2026-11-10", leagueIds: [39], showAllStadiums: false,
 mode: "radius" as const, totalMatches: 1, resultsLimited: false };
const state: DiscoverState = { appliedSearch, fixtures: [], venues: [], locationQuery: "London",
 draftCoordinates: {latitude:51.5,longitude:-0.1},radius:25,startDate:"2026-10-28",endDate:"2026-11-10",
 leagueIds:[39],showAllStadiums:false,editingSearch:false,mapPosition:{latitude:51.6,longitude:-0.2,zoom:12},
 selectedFixtureId:42,searchArea:{center:{latitude:51.5,longitude:-0.1},north:52,south:51,east:0,west:-1},resultsAt:123,scrollY:456 };
let raw="";
const store={setItem:(_key:string,value:string)=>{raw=value},getItem:()=>raw};
test("memory preserves public results and selection without expiry sliding",()=>{
 writeDiscoverState(state,store);assert.equal(readDiscoverState(),state);assert.equal(readDiscoverState()?.resultsAt,123);
 assert.equal(DISCOVER_FRESH_MS,300000);
});
test("restart retains explicit search settings and position but requires fresh results",()=>{
 writeDiscoverState({...state,secret:"do-not-persist",user_id:830} as DiscoverState,store);
 assert.equal(raw.includes("do-not-persist"),false);assert.equal(raw.includes("user_id"),false);
 for(const key of ["fixtures","venues","selectedFixtureId","resultsAt","access_token","going"])assert.equal(key in JSON.parse(raw),false);
 const restored=readDiscoverState(store)!;assert.deepEqual(restored.appliedSearch,appliedSearch);
 assert.deepEqual(restored.mapPosition,state.mapPosition);assert.equal(restored.scrollY,456);
 assert.deepEqual(restored.fixtures,[]);assert.equal(restored.resultsAt,0);assert.equal(restored.selectedFixtureId,null);
});
test("blocked storage retains current-session memory without throwing",()=>{
 writeDiscoverState(state,{setItem:()=>{throw Error("blocked")}});assert.equal(readDiscoverState(),state);
 assert.equal(readDiscoverState({getItem:()=>{throw Error("blocked")}}),null);
});
test("invalid and incompatible persisted state fails closed",()=>{
 for(const value of ["bad","null",JSON.stringify({...state,version:2}),JSON.stringify({...state,version:1,mapPosition:{latitude:99,longitude:0,zoom:12}}),JSON.stringify({...state,version:1,searchArea:null}),JSON.stringify({...state,version:1,leagueIds:[-1]})])assert.equal(readDiscoverState({getItem:()=>value}),null);
});
