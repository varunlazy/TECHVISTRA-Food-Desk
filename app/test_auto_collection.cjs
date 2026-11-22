const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js','utf8');
const scan = source.slice(source.indexOf('async function checkToken(raw)'), source.indexOf('\nasync function redeem()'));
async function scenario(check, result, error) {
 const calls = [], rendered = [];
 const context = {state:{scanBusy:false},stopLive(){},toast(){},buildVerification(x){rendered.push(x)},async api(path){calls.push(path);if(path==='/api/check')return check;if(error)throw error;return result}};
 vm.createContext(context);vm.runInContext(scan,context);
 await vm.runInContext("checkToken('pass')",context);
 return {calls,rendered,context};
}
(async()=>{
 let r=await scenario({status:'valid',student:{name:'Student'}},{status:'served'});
 assert.deepEqual(r.calls,['/api/check','/api/redeem']);assert.equal(r.rendered[0].status,'served');
 for(const status of ['used','invalid','blocked','closed']){
  r=await scenario({status});assert.deepEqual(r.calls,['/api/check']);assert.equal(r.rendered[0].status,status);
 }
 r=await scenario({status:'valid',student:{demo:true}});assert.deepEqual(r.calls,['/api/check']);
 r=await scenario({status:'valid',student:{}},null,Object.assign(new Error('Collected earlier'),{data:{status:'used',student:{redeemed_at:'saved-time'}}}));
 assert.equal(r.rendered[0].status,'used');assert.equal(r.rendered[0].student.redeemed_at,'saved-time');
 r=await scenario({status:'valid',student:{}},null,new Error('Network failed'));
 assert.equal(r.rendered[0].status,'unavailable');assert.equal(r.context.state.scanBusy,false);
 console.log('PASS: automatic first collection; duplicate, invalid, blocked and closed scans; demos; race and network failure.');
})().catch(e=>{console.error(e);process.exitCode=1});
