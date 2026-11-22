const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('static/app.js','utf8');
const fn=source.slice(source.indexOf('async function changePass('),source.indexOf('\nasync function importPage()'));
let html='',closed=false,calls=[],failure=true;
const nodes={'#pass-pin':{value:'',focus(){}},'#pass-pin-error':{textContent:''},'#pass-pin-form':{},'#confirm-pass':{disabled:false}};
const context={$:s=>nodes[s],escapeHtml:String,modal:s=>{html=s},toast(){},closeModal(){closed=true},loadStudents:async()=>{},api:async(path,body)=>{calls.push({path,body});if(failure)throw new Error('Incorrect administrator PIN.');return {message:'QR restored'}}};
vm.createContext(context);vm.runInContext(fn,context);
(async()=>{
 await vm.runInContext("changePass('REG1','Restore QR',7)",context);
 assert.match(html,/type="password"/);assert.match(html,/one more collection/);
 nodes['#pass-pin'].value='wrong';await nodes['#pass-pin-form'].onsubmit({preventDefault(){}});
 assert.equal(closed,false);assert.match(nodes['#pass-pin-error'].textContent,/Incorrect/);assert.equal(nodes['#pass-pin'].value,'');
 failure=false;nodes['#pass-pin'].value='test-pin-only';await nodes['#pass-pin-form'].onsubmit({preventDefault(){}});
 assert.equal(calls[1].path,'/api/restore-collection');assert.equal(calls[1].body.revision,7);assert.equal(closed,true);assert.equal(nodes['#pass-pin'].value,'');assert.ok(!html.includes('test-pin-only'));
 console.log('PASS: masked PIN, wrong PIN keeps dialog open, correct submission requests one-time restore.');
})().catch(e=>{console.error(e);process.exitCode=1});
