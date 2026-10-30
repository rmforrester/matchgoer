import test from "node:test";
import assert from "node:assert/strict";
import { recordDiscoverActivity, expireDiscoverIfInactive, discoverCacheRevision, DISCOVER_IDLE_MS, readDiscoverState, writeDiscoverState, DISCOVER_FRESH_MS, type DiscoverState } from "./discover-state.ts";
const appliedSearch = { latitude: 51.5, longitude: -0.1, locationName: "London", radius: 25,
 startDate: "2026-10-28", endDate: "2026-11-10", leagueIds: [39], showAllStadiums: false,
 mode: "radius" as const, totalMatches: 1, resultsLimited: false };
const state: DiscoverState = { appliedSearch, fixtures: [], venues: [], locationQuery: "London",
 draftCoordinates: {latitude:51.5,longitude:-0.1},radius:25,startDate:"2026-10-28",endDate:"2026-11-10",
 leagueIds:[39],showAllStadiums:false,editingSearch:false,mapPosition:{latitude:51.6,longitude:-0.2,zoom:12},
 selectedFixtureId:42,searchArea:{center:{latitude:51.5,longitude:-0.1},north:52,south:51,east:0,west:-1},resultsAt:123,scrollY:456 };
let raw="";
const values = new Map<string, string>();
const store={setItem:(key:string,value:string)=>{values.set(key,value);if(key==="matchgoer.discover-search.v1")raw=value;},getItem:(key:string)=>values.get(key)??null,removeItem:(key:string)=>{values.delete(key);}};
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


test("list expansion survives navigation/restart without persisting supporter state", () => {
  writeDiscoverState({...state, whatsOnExpanded:true, shortlistExpanded:true},store);
  assert.equal(readDiscoverState()?.whatsOnExpanded,true);
  assert.equal(readDiscoverState(store)?.shortlistExpanded,true);
  writeDiscoverState(state,store);
  assert.equal(readDiscoverState(store)?.whatsOnExpanded,false);
  const invalid = {...JSON.parse(raw), whatsOnExpanded:"true"};
  assert.equal(readDiscoverState({getItem:()=>JSON.stringify(invalid)}),null);
});


test("30-minute boundary expires only Discover; active use extends inactivity but refresh writes do not", () => {
 const now=Date.now(); recordDiscoverActivity(now,store); writeDiscoverState(state,store);
 store.setItem("saved-guest-history","keep"); store.setItem("supabase-session","keep");
 assert.equal(expireDiscoverIfInactive(now+DISCOVER_IDLE_MS-1,store),false);
 const before=store.getItem("matchgoer.discover-activity.v1"); writeDiscoverState(state,store);
 assert.equal(store.getItem("matchgoer.discover-activity.v1"),before);
 assert.equal(expireDiscoverIfInactive(now+DISCOVER_IDLE_MS,store),true);
 assert.equal(store.getItem("matchgoer.discover-search.v1"),null);
 assert.equal(store.getItem("saved-guest-history"),"keep");assert.equal(store.getItem("supabase-session"),"keep");
 recordDiscoverActivity(now,store);writeDiscoverState(state,store);
 recordDiscoverActivity(now+20*60_000,store);
 assert.equal(expireDiscoverIfInactive(now+40*60_000,store),false);
 assert.equal(expireDiscoverIfInactive(now+50*60_000,store),true);
});

test("expired screen cleanup cannot resurrect a cleared search", () => {
 const now=Date.now();recordDiscoverActivity(now,store);const old=discoverCacheRevision();writeDiscoverState(state,store,old);
 assert.equal(expireDiscoverIfInactive(now+DISCOVER_IDLE_MS,store),true);
 recordDiscoverActivity(now+DISCOVER_IDLE_MS,store);writeDiscoverState(state,store,old);
 assert.equal(store.getItem("matchgoer.discover-search.v1"),null);
});
