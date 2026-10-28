import assert from "node:assert/strict";
import test from "node:test";
import { emptyGuestHistory, historyLoadError } from "./api-error.ts";
test("only explicit successful empty anonymous session skips history reads",()=>{
 assert.equal(emptyGuestHistory({anonymous:true,anonymous_activity:false},false,null),true);
 for(const session of [null,{}, {anonymous:true}, {anonymous:true,anonymous_activity:true}, {anonymous:false,anonymous_activity:false}]) assert.equal(emptyGuestHistory(session,false,null),false);
 assert.equal(emptyGuestHistory({anonymous:true,anonymous_activity:false},true,null),false);
 assert.equal(emptyGuestHistory({anonymous:true,anonymous_activity:false},false,"expired"),false);
});
test("missing identity stays a visible, nontechnical recoverable error",()=>assert.equal(historyLoadError({isAxiosError:true,response:{status:401,data:{detail:{code:"NO_ACTIVE_IDENTITY",message:"No active Matchgoer identity"}}}},"fallback"),"We couldn't access your saved history. Please try again."));
test("network, forbidden and session errors are not empty states",()=>{
 assert.match(historyLoadError({isAxiosError:true},"fallback"),/connection/);
 assert.equal(historyLoadError({isAxiosError:true,response:{status:403,data:{detail:{message:"Account inactive"}}}},"fallback"),"Account inactive");
 assert.equal(historyLoadError(new Error("failure"),"Please try again"),"Please try again");
});
