const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/app.js','utf8');
const helper=source.slice(source.indexOf('function formatIST('),source.indexOf('const num='));
const loader=source.slice(source.indexOf('async function loadStudents()'),source.indexOf('\nfunction modal('));
const nodes={'#student-q':{value:''},'#student-filter':{value:'all'},'#students-count':{},'#students-tbody':{querySelectorAll:()=>[]}};
const rows=[{name:'Collected Student',reg_no:'REG1',redeemed:true,redeemed_at:'2026-11-15T20:45:09+00:00',redeemed_counter:'Counter 1',attendance:'present',pass_status:'active'}, {name:'Pending Student',reg_no:'REG2',redeemed:false,attendance:'present',pass_status:'active'}];
const c={Intl,Date,Number,state:{page:'students'},$:s=>nodes[s],api:async()=>({students:rows,total:2}),num:String,escapeHtml:v=>String(v??''),mealBadge:()=>'',badge:v=>v};vm.createContext(c);vm.runInContext(helper+loader,c);
(async()=>{
 const value=vm.runInContext("formatIST('2026-11-15T20:45:09+00:00')",c);
 assert.match(value,/16 Nov 2026/);assert.match(value,/02:15:09 am IST/i);
 assert.equal(vm.runInContext('formatIST(null)',c),'—');
 assert.equal(vm.runInContext("formatIST('invalid')",c),'Time unavailable');
 await vm.runInContext('loadStudents()',c);
 assert.match(nodes['#students-tbody'].innerHTML,/16 Nov 2026/);
 assert.match(nodes['#students-tbody'].innerHTML,/Counter 1/);
 assert.match(nodes['#students-tbody'].innerHTML,/<td>—<\/td>/);
 console.log('PASS: UTC-to-IST midnight rollover, collection date/time and counter, uncollected rows.');
})().catch(e=>{console.error(e);process.exitCode=1});
