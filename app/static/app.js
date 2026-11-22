'use strict';
const $ = (s, root=document)=>root.querySelector(s);
const el = (tag, cls='', text='')=>{const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x};
const state={user:null,page:'dashboard',setup:false,importText:'',scanToken:'',scanResult:null,scanBusy:false,stream:null,scanTimer:null,detector:null,stats:null,localCameraActive:false,scanEpoch:0};
const icons={testqr:'◈',live:'◉',dashboard:'▦',students:'♙',import:'⇧',counters:'▣',activity:'◷',guide:'?',scanner:'▧',server:'◉'};
let lastHeart=null;
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function formatIST(value){
 if(value===null || value===undefined || value==='')return '—';
 const date=new Date(value);
 if(Number.isNaN(date.getTime()))return 'Time unavailable';
 return new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}).format(date)+' IST';
}
const num=n=>Number(n||0).toLocaleString('en-IN');
function toast(message,type=''){const t=el('div','toast '+type,message);$('#toast-area').append(t);setTimeout(()=>t.remove(),4200)}
async function api(path,body=null,method='GET'){
  const opt={method,credentials:'same-origin',headers:{'X-FoodDesk':'local-app'}};
  if(body!==null){opt.method='POST';opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
  let res;
  try{res=await fetch(path,opt)}catch(e){throw new Error('Cannot reach local server. Check Wi-Fi and that the laptop is running.')}
  let data={};try{data=await res.json()}catch{}
  if(!res.ok){if(res.status===401&&path!=='/api/login'){state.user=null;showAuth(false)};const error=new Error(data.error||'Request failed');error.data=data;error.status=res.status;throw error}
  return data;
}
function showAuth(setup){stopLive();state.setup=setup;$('#auth-screen').classList.remove('hidden');$('#app-screen').classList.add('hidden');$('#auth-title').textContent=setup?'Set up your food desk':'Welcome back';$('#auth-description').textContent=setup?'Create the administrator password. This is a one-time setup.':'Sign in to your local food distribution system.';$('#username-wrap').classList.toggle('hidden',setup);$('#login-username').disabled=setup;$('#login-username').required=!setup;$('#confirm-password').disabled=!setup;$('#confirm-password').required=setup;$('#login-password').minLength=setup?12:1;$('#login-password').maxLength=128;if(setup)$('#login-username').value='admin';$('#confirm-wrap').classList.toggle('hidden',!setup);$('#login-submit').innerHTML=setup?'Create admin account →':'Sign in →';$('#login-password').value='';$('#confirm-password').value='';if(setup)$('#login-password').autocomplete='new-password';else $('#login-password').autocomplete='current-password'}
async function boot(){try{let x=await api('/api/session');if(x.setup_required){showAuth(true)}else if(x.user){state.user=x.user;showApp()}else showAuth(false)}catch(e){showAuth(false);toast(e.message,'error')}}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const password=$('#login-password').value;const button=$('#login-submit');button.disabled=true;try{if(state.setup){if(password!==$('#confirm-password').value)throw new Error('Passwords do not match.');await api('/api/setup',{password});toast('Administrator account created. Sign in now.','success');showAuth(false)}else{await api('/api/login',{username:$('#login-username').value,password,device_name:$('#device-name').value});const s=await api('/api/session');state.user=s.user;showApp();toast('Signed in successfully.','success')}}catch(ex){toast(ex.message,'error')}finally{button.disabled=false}});
function showApp(){if(!state.user)return;document.body.classList.toggle('staff-mode',state.user.role==='counter');$('#auth-screen').classList.add('hidden');$('#app-screen').classList.remove('hidden');$('#user-name').textContent=state.user.role==='admin'?'Administrator':(state.user.counter_name||state.user.username);$('#user-role').textContent=state.user.role==='admin'?'Full access':'Food counter';$('#avatar-letter').textContent=(state.user.counter_name||state.user.username||'A')[0].toUpperCase();const pages=state.user.role==='admin'?[['dashboard','Overview'],['live','Live operations'],['testqr','Test QR · phones'],['students','Students'],['import','Import attendance'],['counters','Food counters'],['activity','Activity logs'],['server','Laptop server'],['guide','Setup guide'],['scanner','Try scanner']]:[['scanner','Scan food passes']];$('#main-nav').innerHTML=pages.map(([p,n])=>`<button class="nav-link" data-page="${p}"><span>${icons[p]}</span>${n}</button>`).join('');$('#main-nav').querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.page)));navigate(state.user.role==='admin'?'dashboard':'scanner');heartBeat()}
function navigate(page){stopLive();state.page=page;$('#sidebar').classList.remove('open');$('#main-nav').querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));const labels={live:'Live operations',dashboard:'Overview',students:'Student directory',import:'Import attendance',counters:'Food counters',activity:'Activity logs',guide:'Setup guide',server:'Laptop server',scanner:'QR scanner',testqr:'Phone test QR'};$('#breadcrumb').textContent=labels[page]||'Food desk';const views={live:liveOperations,dashboard,students,importPage,counters,activity,serverPage,guide,scanner,testqr:phoneTestQR};$('#content').innerHTML='<div class="empty">Loading…</div>';(views[page]||dashboard)().catch(e=>{$('#content').innerHTML=`<div class="panel"><h3>Unable to load</h3><p>${escapeHtml(e.message)}</p><button class="btn" id="retry-page">Retry</button></div>`;$('#retry-page').onclick=()=>navigate(page)});
}
$('#logout-button').onclick=async()=>{try{await api('/api/logout',{})}catch{}state.user=null;showAuth(false)};
$('#menu-toggle').onclick=()=>$('#sidebar').classList.toggle('open');
async function heartBeat(){clearTimeout(lastHeart);if(!state.user)return;try{await api('/api/heartbeat',{});$('#connection-pill').className='pill ok';$('#connection-pill').innerHTML='<span class="mini-dot"></span> Local server connected';$('#network-note').textContent='Laptop server · internet not required'}catch{$('#connection-pill').className='pill down';$('#connection-pill').innerHTML='<span class="mini-dot"></span> Connection lost';$('#network-note').textContent='Do not distribute until connection returns'}lastHeart=setTimeout(heartBeat,6500)}
function pagehead(title,sub,actions=''){return `<div class="page-header"><div><h1>${title}</h1><p>${sub}</p></div>${actions?`<div class="actions">${actions}</div>`:''}</div>`}
const badge=(text,tone='')=>`<span class="status-tag ${tone}">${escapeHtml(text)}</span>`;
const mealBadge=meal=>`<span class="meal-badge ${meal==='VEG'?'veg':'nonveg'}">${escapeHtml(meal)}</span>`;
async function dashboard(){const x=await api('/api/stats');state.stats=x;const t=x.totals||{};const progress=t.eligible?Math.round((t.served/t.eligible)*100):0;const meals=Object.fromEntries((x.meals||[]).map(m=>[m.food_type,m]));$('#content').innerHTML=pagehead('Food distribution overview','See verified attendance, served meals and counters in one place.',`<button class="btn" id="refresh-stats">↻ Refresh</button><button class="btn primary" id="export-report">↓ Export report</button>`)+`
<div class="stats-grid">
  ${stat('Form records',t.total,'Records imported','purple','▤')}
  ${stat('Attendance present',t.present,`${num(t.absent)} marked absent`,'blue','☑')}
  ${stat('Food collected',t.served,'One-time QR redemptions','green','✓')}
  ${stat('Meals remaining',t.remaining,'Active unredeemed passes','orange','◷')}
</div>
<section class="panel" style="margin-bottom:20px"><h3>${x.gate.classroom?.year?'Year '+escapeHtml(x.gate.classroom.year)+' classroom':'Choose this laptop’s year'}</h3><p>${x.gate.classroom?.year?'Only students whose verified QR year matches this venue can collect food here.':'Select 2nd, 3rd or 4th year when opening counters.'} Each laptop keeps its own meal stock, counter logins and report.</p><label for="admin-year-select">Students served at this venue</label><div class="actions"><select id="admin-year-select" aria-label="Students served at this venue"><option value="">Select year</option>${['2','3','4'].map(y=>`<option value="${y}" ${x.gate.classroom?.year===y?'selected':''}>${y==='2'?'2nd':y==='3'?'3rd':'4th'} year only</option>`).join('')}</select><button class="btn primary" id="setup-classroom">Set year &amp; meal quantities</button></div><p class="muted">Students from another year must go to their assigned venue.</p></section>
<div class="gate-banner ${x.gate.open?'gate-open':'gate-closed'}"><div class="gate-head"><div class="gate-icon">${x.gate.open?'✓':'⊘'}</div><div><h3>${x.gate.open?'FOOD DISTRIBUTION IS OPEN':'FOOD DISTRIBUTION IS CLOSED'}</h3><p>${x.gate.open?'All approved counters can redeem QR passes.':'All redemptions are blocked until an administrator opens the counters.'}</p></div></div><div class="actions"><button class="btn ${x.gate.open?'danger':'primary'}" id="toggle-distribution">${x.gate.open?'Close food counters':'Open food counters'}</button><button class="btn" id="open-server">Laptop server ↗</button></div></div>
<div class="dashboard-grid">
  <section class="panel"><div class="between"><h3>Distribution progress</h3>${badge(progress+'% completed','good')}</div><p class="panel-sub">Served meals versus currently eligible active passes</p><div class="between"><strong>${num(t.served)} meals served</strong><strong>${num(t.eligible)} eligible passes</strong></div><div class="progress-track"><div class="progress-bar" style="width:${Math.min(100,progress)}%"></div></div><p class="muted" style="font-size:11px;margin:13px 0 0">Revoked and absent students cannot redeem. Already-served students remain in the audit report.</p><div class="divider"></div><h3>Meal-wise breakdown</h3><div class="meal-row">${mealBadge('VEG')}<span>${num(meals.VEG?.served)} served / ${num(meals.VEG?.active)} eligible</span></div><div class="meal-row">${mealBadge('NON-VEG')}<span>${num(meals['NON-VEG']?.served)} served / ${num(meals['NON-VEG']?.active)} eligible</span></div><p class="muted" style="font-size:11px;margin:12px 0 0">Meal counts can change when you import updated attendance. To estimate catering quantities, review the original Google Form choices separately as well.</p></section>
  <section class="panel"><h3>Counter status</h3><p class="panel-sub">Food served by each registered desk</p>${x.counters.length?x.counters.map(c=>`<div class="meal-row"><span><strong>${escapeHtml(c.counter_name)}</strong><br><small class="muted">@${escapeHtml(c.username)}</small></span><span style="text-align:right"><strong>${num(c.served)}</strong> served<br>${badge(c.active?'Enabled':'Disabled',c.active?'good':'bad')}</span></div>`).join(''):'<div class="empty">No counters created yet.<br>Create at least one counter login.</div>'}<div class="divider"></div><div class="hint">Connect every counter phone to the same Wi-Fi router as this laptop. The router does not need internet.</div></section>
</div>`;$('#refresh-stats').onclick=()=>navigate('dashboard');$('#export-report').onclick=()=>{window.location.href='/api/export'};
$('#open-server').onclick=()=>navigate('server');
$('#toggle-distribution').onclick=()=>confirmDistribution(x.gate.open);
$('#setup-classroom').onclick=()=>{const year=$('#admin-year-select').value;if(!year)return toast('Select 2nd, 3rd or 4th year.','error');confirmDistribution(false);$('#classroom-year').value=year;};
$('#content').insertAdjacentHTML('beforeend',`<section class="panel" style="margin-top:20px"><h3>Meal quantities</h3><p class="panel-sub">Total food prepared for this distribution, including meals already given.</p>${['VEG','NON-VEG'].map(k=>`<div class="meal-row">${mealBadge(k)}<span>${x.inventory?.[k]?.total==null?'Not entered':num(x.inventory[k].remaining)+' remaining / '+num(x.inventory[k].total)+' prepared'} · ${num(x.inventory?.[k]?.served)} given</span></div>`).join('')}<button class="btn" id="edit-meals">${x.gate.open?'Update meal quantities':'Enter quantities & open counters'}</button></section><section class="panel" style="margin-top:20px" id="admin-phone-login"><h3>Phone login QR</h3><p>Loading phone connection…</p></section>`);
$('#edit-meals').onclick=()=>confirmDistribution(false);
loadAdminPhoneQR();
$('#content').insertAdjacentHTML('beforeend','<section class="panel" style="margin-top:20px"><h3>Live operations</h3><p>Connected phones, scan requests and food given update every 3 seconds.</p><button class="btn primary" id="go-live">Open live operations →</button><div id="live-summary" class="hint"></div></section>');$('#go-live').onclick=()=>navigate('live');refreshLiveSummary();
}
async function phoneTestQR(){
  const x=await api('/api/qr-setup-status');
  $('#content').innerHTML=pagehead('Live phone scanner · test QR','Scan an offline TEST QR from the laptop screen with a counter phone. No website AES key needed.')+`
  <div class="dashboard-grid">
    <section class="panel">
      <h3>Generate a safe test QR</h3>
      <p class="panel-sub">Select a meal and generate a signed, 30-minute QR for a fake student. It is distinct from production passes and cannot affect real food counts.</p>
      <label style="display:block;margin-bottom:12px">Test meal <select id="test-meal"><option value="veg">VEG</option><option value="non_veg">NON-VEG</option></select></label>
      <button class="btn primary" id="generate-test-qr">◈ Generate new TEST QR</button>
      <div id="test-qr-result" style="margin-top:17px"></div>
    </section>
    <section class="panel">
      <h3>Website QR verification status</h3>
      <div class="hint ${x.website_qr_configured&&x.cryptography_installed?'':'warning'}">
        <b>${x.website_qr_configured&&x.cryptography_installed?'Configuration check passed':'Set up QR configuration again'}</b>
        <p class="muted">${escapeHtml(x.message)}</p>
      </div>
      <p class="muted">Your existing <b>TV26E2 encrypted website demo QR</b> needs the matching encryption secret and website public verification key. A local TEST QR works independently.</p>
      <p class="muted">If this check fails, run <b>Mac / Windows - Setup Website QR</b> on the laptop and import the matching JSON. Then reopen this page to check again. Never paste the private key into a web page or chat.</p>
      <div class="hint warning"><b>Never give food for a test QR.</b> Test confirmation and duplicate blocking write only to the demo test table, not the students table.</div>
    </section>
  </div>`;
  $('#generate-test-qr').onclick=async()=>{
    const btn=$('#generate-test-qr');btn.disabled=true;
    try{
      const result=await api('/api/local-test-qr/create',{meal:$('#test-meal').value});
      $('#test-qr-result').innerHTML=`<div class="hint warning" style="text-align:center"><b>TEST ONLY · DO NOT SERVE FOOD</b><br><small>Fake student · ${result.meal==='veg'?'VEG':'NON-VEG'} · expires ${escapeHtml(formatIST(result.expires_at*1000))}</small></div><div style="text-align:center;margin-top:14px"><img src="${result.image}" alt="Local demo QR to scan from a staff phone" style="width:min(100%,340px);height:auto;background:white;padding:10px;border-radius:12px" /></div><div class="actions" style="margin-top:14px;justify-content:center"><button class="btn" id="copy-local-test-token">Copy test QR text</button><button class="btn" id="reset-test-qr">Generate another QR</button></div><p class="muted" style="text-align:center;font-size:12px">Open the phone's secure HTTPS scanner and scan this code. Tap SIMULATE DEMO REDEMPTION, then rescan to confirm duplicate blocking. Every new QR is a new test.</p>`;
      $('#copy-local-test-token').onclick=()=>{navigator.clipboard?.writeText(result.token).then(()=>toast('TEST token copied','success')).catch(()=>toast('Copy unavailable; scan the QR instead.','error'))};
      $('#reset-test-qr').onclick=()=>$('#generate-test-qr').click();
    }catch(e){$('#test-qr-result').innerHTML=`<div class="hint warning">${escapeHtml(e.message)}</div>`}
    finally{btn.disabled=false}
  };
}
function stat(label,value,note,shade,icon){return `<div class="stat-card"><div class="stat-head"><span class="stat-label">${label}</span><span class="stat-icon ${shade}">${icon}</span></div><h2>${num(value)}</h2><span class="stat-note">${note}</span></div>`}
async function students(){const content=$('#content');content.innerHTML=pagehead('Student directory','Search students, view meal status and collection time in IST, and manage passes with the administrator PIN.',`<button class="btn primary" id="students-export">↓ Export CSV</button>`)+`<section class="panel"><div class="search-row"><div class="search-field"><input id="student-q" placeholder="Search register number, name or email" aria-label="Search students"></div><select id="student-filter" aria-label="Filter students"><option value="all">All students</option><option value="present">Present</option><option value="absent">Absent</option><option value="pending">Not served</option><option value="redeemed">Food collected</option><option value="revoked">Revoked</option></select></div><p class="count-note" id="students-count">Loading students…</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Student</th><th>Register no.</th><th>Department</th><th>Meal</th><th>Attendance</th><th>Food</th><th>Collected at (IST)</th><th>Action</th></tr></thead><tbody id="students-tbody"></tbody></table></div></section>`;
$('#students-export').onclick=()=>window.location.href='/api/export';let timer;$('#student-q').oninput=()=>{clearTimeout(timer);timer=setTimeout(loadStudents,260)};$('#student-filter').onchange=loadStudents;await loadStudents();}
async function loadStudents(){const q=$('#student-q')?.value||'';const f=$('#student-filter')?.value||'all';const x=await api('/api/students?q='+encodeURIComponent(q)+'&filter='+encodeURIComponent(f));if(state.page!=='students')return;$('#students-count').textContent=`${num(x.total)} records found${x.limited?' · Showing first 100; refine search to see more':''}`;$('#students-tbody').innerHTML=x.students.length?x.students.map(s=>`<tr><td><b>${escapeHtml(s.name)}</b><br><small class="muted">${escapeHtml(s.email)}</small></td><td>${escapeHtml(s.reg_no)}</td><td>${escapeHtml(s.department)} ${escapeHtml(s.section)}</td><td>${mealBadge(s.food_type)}</td><td>${badge(s.attendance==='present'?'Present':'Absent',s.attendance==='present'?'good':'bad')}</td><td>${badge(s.recollection_allowed?'QR restored · scan once':s.redeemed?'Collected':s.pass_status==='revoked'?'Revoked':'Not collected',s.recollection_allowed?'wait':s.redeemed?'good':s.pass_status==='revoked'?'bad':'wait')}</td><td>${s.redeemed?escapeHtml(formatIST(s.redeemed_at)):'—'}${s.redeemed&&s.redeemed_counter?`<br><small class="muted">${escapeHtml(s.redeemed_counter)}</small>`:''}</td><td><div class="actions"><button class="btn small" data-qr="${escapeHtml(s.reg_no)}" ${s.attendance!=='present'?'disabled':''}>QR</button>${s.redeemed?`<button class="btn small primary" data-recollect="${escapeHtml(s.reg_no)}" data-revision="${Number(s.collection_revision)}" ${s.recollection_allowed?'disabled':''}>${s.recollection_allowed?'QR restored':'Restore QR'}</button>`:`<button class="btn small ${s.pass_status==='active'?'danger':''}" data-revoke="${escapeHtml(s.reg_no)}">${s.pass_status==='active'?'Revoke':'Restore'}</button>`}</div></td></tr>`).join(''):'<tr><td colspan="8" class="empty">No matching records.</td></tr>';
$('#students-tbody').querySelectorAll('[data-qr]').forEach(b=>b.onclick=()=>showQr(b.dataset.qr));$('#students-tbody').querySelectorAll('[data-revoke]').forEach(b=>b.onclick=()=>changePass(b.dataset.revoke,b.textContent));$('#students-tbody').querySelectorAll('[data-recollect]').forEach(b=>b.onclick=()=>changePass(b.dataset.recollect,'Restore QR',Number(b.dataset.revision)));}
function modal(html){$('#modal-content').innerHTML=html;$('#modal-overlay').classList.remove('hidden');$('#modal-overlay').setAttribute('aria-hidden','false');$('#modal-content').querySelectorAll('[data-close]').forEach(b=>b.onclick=closeModal)}
function closeModal(){$('#modal-overlay').classList.add('hidden');$('#modal-overlay').setAttribute('aria-hidden','true');$('#modal-content').innerHTML=''}
$('#modal-overlay').addEventListener('click',e=>{if(e.target===$('#modal-overlay'))closeModal()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
function showQr(reg){modal(`<div class="between"><h3>Student QR pass</h3><button class="btn small" data-close>✕</button></div><p class="muted">Register number: <b>${escapeHtml(reg)}</b></p><img src="/api/pass-qr/${encodeURIComponent(reg)}" alt="Food pass QR for ${escapeHtml(reg)}"><p class="muted" style="font-size:11px;text-align:center">This QR is for a student whose attendance is present. Do not distribute screenshots publicly.</p><div class="modal-actions"><button class="btn" data-close>Close</button><a class="btn primary" download="${escapeHtml(reg)}.png" href="/api/pass-qr/${encodeURIComponent(reg)}">Download QR</a></div>`)}
async function changePass(reg,current,revision){
 const recollect=current.trim()==='Restore QR';
 const verb=current.trim()==='Revoke'?'revoke':'restore';
 modal(`<h3>${recollect?'Restore QR for one more collection':verb==='revoke'?'Revoke food pass':'Restore food pass'}?</h3><p>Register number: <b>${escapeHtml(reg)}</b>.</p><p>${recollect?'The counter can scan this QR once more. The previous collection and meal count will remain in the history. The QR must still pass signature, date, venue and stock checks.':verb==='revoke'?'This blocks food collection until the pass is restored.':'This allows an approved, unused pass to be scanned again.'}</p><form id="pass-pin-form"><label for="pass-pin">Administrator PIN</label><input id="pass-pin" type="password" required maxlength="128" autocomplete="off" style="width:100%;margin-top:8px"><p id="pass-pin-error" class="text-red" role="alert"></p><div class="modal-actions"><button type="button" class="btn" data-close>Cancel</button><button type="submit" class="btn ${verb==='revoke'?'danger':'primary'}" id="confirm-pass">${recollect?'Restore QR — allow once':'Confirm '+verb}</button></div></form>`);
 $('#pass-pin').focus();
 $('#pass-pin-form').onsubmit=async e=>{
  e.preventDefault();const button=$('#confirm-pass');button.disabled=true;$('#pass-pin-error').textContent='';
  try{
   const pin=$('#pass-pin').value;$('#pass-pin').value='';
   const result=await api(recollect?'/api/restore-collection':'/api/revoke',{reg_no:reg,pin,revision});
   toast(result.message||'Food pass updated.','success');closeModal();await loadStudents();
  }catch(error){
   const message=$('#pass-pin-error');if(message)message.textContent=error.message;
  }finally{const confirm=$('#confirm-pass');if(confirm)confirm.disabled=false;}
 };
}

async function importPage(){const content=$('#content');content.innerHTML=pagehead('Import attendance records','Load the approved list from your website before distributing food.',`<a class="btn" download="import_template.csv" href="/static/import_template.csv">↓ Download template</a>`)+`
<div class="import-grid"><section class="panel"><h3>Import student CSV</h3><p class="panel-sub">CSV data remains on this laptop. You can import updates without clearing redemption history.</p><label for="csv-upload" id="drop-zone" class="dropzone"><div><div class="drop-icon">⇧</div><h3 style="margin-bottom:4px">Choose your verified CSV file</h3><p class="muted">Click to browse or drag a .csv file here</p><span class="btn soft">Browse files</span></div></label><input type="file" accept=".csv,text/csv" id="csv-upload" class="hidden"><p class="muted" id="import-file-info" style="font-size:12px;margin-top:12px">No file selected</p><div class="hint warning" style="margin:18px 0"><b>Important:</b> The <span class="code">qr_token</span> column must contain the same secret token already encoded in each emailed QR. Existing tokens must never be regenerated during re-imports.</div><button class="btn primary full" id="do-import" disabled>⇧ Import approved records</button><div id="import-result" style="margin-top:14px"></div></section><section class="panel"><h3>Before you import</h3><p class="panel-sub">Follow these steps for a safe distribution</p><div class="steps"><div class="step"><div class="step-num">01</div><div><b>Collect Google Forms</b><p>Get the student details, email and meal preference.</p></div></div><div class="step"><div class="step-num">02</div><div><b>Approve attendance</b><p>Staff update the signed paper list on the main website.</p></div></div><div class="step"><div class="step-num">03</div><div><b>Export approved passes</b><p>Use one high-entropy QR token per register number, with present/absent status.</p></div></div><div class="step"><div class="step-num">04</div><div><b>Import and test</b><p>Bring CSV to this laptop and confirm student and meal details.</p></div></div><div class="step"><div class="step-num">05</div><div><b>Keep desks connected</b><p>All counters use the same laptop over a private Wi-Fi network.</p></div></div></div><div class="divider"></div><p class="muted" style="font-size:11px">Supported columns: <span class="code">${['register_number','student_name','department','section','email','food_type','attendance_status','qr_token'].join(', ')}</span></p></section></div>`;
const input=$('#csv-upload'),zone=$('#drop-zone');input.onchange=()=>chooseCsv(input.files[0]);zone.ondragover=e=>{e.preventDefault();zone.style.borderColor='#6959ed'};zone.ondragleave=()=>zone.style.borderColor='';zone.ondrop=e=>{e.preventDefault();zone.style.borderColor='';chooseCsv(e.dataTransfer.files[0])};$('#do-import').onclick=uploadCsv;}
async function chooseCsv(file){if(!file)return;if(!file.name.toLowerCase().endsWith('.csv')||file.size>6*1024*1024){toast('Select a .csv file smaller than 6 MB.','error');return}state.importText=await file.text();$('#import-file-info').textContent=`Ready: ${file.name} · ${(file.size/1024).toFixed(1)} KB`;$('#do-import').disabled=false;$('#import-result').innerHTML=''}
async function uploadCsv(){let btn=$('#do-import');btn.disabled=true;btn.textContent='Importing records…';try{let res=await api('/api/import',{csv:state.importText});$('#import-result').innerHTML=`<div class="hint"><b>✓ Import complete</b><br>${num(res.created)} new · ${num(res.updated)} updated · ${num(res.preserved)} prior redemptions preserved</div>`;toast(res.message,'success')}catch(e){let issues=e.data?.issues?.length?'<br>'+e.data.issues.map(escapeHtml).join('<br>'):'';$('#import-result').innerHTML=`<div class="hint warning"><b>Import not applied</b><br>${escapeHtml(e.message)}${issues}</div>`;toast('Import rejected. Review the details below.','error')}finally{btn.disabled=false;btn.textContent='⇧ Import approved records'}}
async function counters(){let x=await api('/api/stats');$('#content').innerHTML=pagehead('Manage food counters','Set up separate desk logins so every food handoff has an audit trail.')+`
<div class="dashboard-grid"><section class="panel"><h3>Create a new counter</h3><p class="panel-sub">For example: Counter 1, Counter 2, Counter 3, Counter 4</p><form id="counter-form" class="field-stack"><label>Counter name<input id="counter-display" placeholder="Veg Counter A" required maxlength="50"></label><label>Login username<input id="counter-login" placeholder="counter1" required maxlength="24" pattern="[a-z0-9_-]{3,24}"></label><label>Counter password (minimum 8 characters)<input id="counter-password" type="password" minlength="8" required autocomplete="new-password"></label><button class="btn primary" type="submit">+ Create counter login</button></form><div class="hint" style="margin-top:20px"><b>Phone access:</b> Open the LAN URL printed on this laptop when the server starts. Log in with the counter username/password.</div></section>
<section class="panel"><h3>Existing counters</h3><p class="panel-sub">Manage access and monitor servings</p>${x.counters.length?x.counters.map(c=>`<div class="meal-row"><div><b>${escapeHtml(c.counter_name)}</b><br><small class="muted">@${escapeHtml(c.username)} · ${num(c.served)} meals served</small><br>${badge(c.active?'Enabled':'Disabled',c.active?'good':'bad')}</div><button class="btn small ${c.active?'danger':'soft'}" data-counter="${escapeHtml(c.username)}">${c.active?'Disable':'Enable'}</button></div>`).join(''):'<div class="empty">Create a counter to start scanning.</div>'}</section></div>`;
$('#counter-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/create-counter',{counter_name:$('#counter-display').value,username:$('#counter-login').value,password:$('#counter-password').value});toast('Counter created.','success');navigate('counters')}catch(e){toast(e.message,'error')}};$('#content').querySelectorAll('[data-counter]').forEach(b=>b.onclick=async()=>{let current=b.textContent;modal(`<h3>${current} this counter?</h3><p>${escapeHtml(b.dataset.counter)} will be ${current==='Disable'?'signed out and blocked from further serving':'allowed to sign in again'}.</p><div class="modal-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="confirm-toggle">Confirm</button></div>`);$('#confirm-toggle').onclick=async()=>{try{await api('/api/toggle-counter',{username:b.dataset.counter});closeModal();navigate('counters');toast('Counter updated.','success')}catch(e){toast(e.message,'error')}}});}
async function activity(){let x=await api('/api/audit');$('#content').innerHTML=pagehead('Activity & redemption logs','An audit trail of imports, counter logins, pass changes and food distribution.')+`<section class="panel"><h3>Recent activity <span class="count-note">(latest 150)</span></h3><p class="panel-sub">All times are shown in Indian Standard Time (IST, UTC+05:30).</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Time</th><th>Staff</th><th>Action</th><th>Register no.</th><th>Details</th><th>IP address</th></tr></thead><tbody>${x.logs.length?x.logs.map(l=>`<tr><td>${escapeHtml(formatIST(l.at))}</td><td><b>${escapeHtml(l.actor)}</b></td><td>${badge(l.action,l.action==='served'?'good':'')}</td><td>${escapeHtml(l.reg_no||'—')}</td><td>${escapeHtml(l.description||'—')}</td><td class="muted">${escapeHtml(l.ip||'—')}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">No activity yet.</td></tr>'}</tbody></table></div></section>`}
function confirmDistribution(open){
 const target=!open;
 const inventory=state.stats?.inventory||{};const classroom=state.stats?.gate?.classroom||{};
 modal(`<h3>${target?'Meal quantities & open counters':'Close all food counters?'}</h3>${target?`<p>Enter total meals prepared, including any already served. Existing student verification and duplicate protection stay active.</p><label>Year served by this laptop<select id="classroom-year"><option value="">Select year</option>${['2','3','4'].map(y=>`<option value="${y}" ${classroom.year===y?'selected':''}>${y==='2'?'2nd':y==='3'?'3rd':'4th'} year</option>`).join('')}</select></label><p class="muted">The verified year inside each QR must match this venue. Students from other years are directed to their year’s venue.</p><label>Veg meals<input id="meal-veg" type="number" min="0" max="1000000" step="1" value="${inventory.VEG?.total??''}" placeholder="e.g. 300"></label><label>Non-veg meals<input id="meal-nonveg" type="number" min="0" max="1000000" step="1" value="${inventory['NON-VEG']?.total??''}" placeholder="e.g. 200"></label>`:'<p>All counters will stop accepting redemptions.</p>'}<div class="modal-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="confirm-gate">${target?'Save & open counters':'Close counters'}</button></div>`);
 $('#confirm-gate').onclick=async()=>{try{const body={open:target};if(target){const veg=$('#meal-veg').value,nonveg=$('#meal-nonveg').value;if(!veg.trim()||!nonveg.trim())throw Error('Enter both quantities. Use 0 when a meal is unavailable.');body.year=$('#classroom-year').value;if(!body.year)throw Error('Select 2nd, 3rd or 4th year.');body.quantities={'VEG':Number(veg),'NON-VEG':Number(nonveg)}}await api('/api/distribution',body);closeModal();toast(target?'Meal quantities saved. Counters opened.':'Counters closed.','success');navigate('dashboard')}catch(e){toast(e.message,'error')}};
}
async function loadAdminPhoneQR(){
 const [s,qr]=await Promise.all([api('/api/server-info'),api('/api/qr-setup-status')]);const box=$('#admin-phone-login');if(!box)return;
 box.innerHTML=`${!qr.website_qr_configured?'<div class="hint warning"><b>Website QR verification needs setup.</b><p>Run Setup Website QR on this laptop and import the single private website QR setup JSON. Until then, real passes cannot authorize food.</p></div>':''}<h3>Phone login QR</h3><p>Connect staff phones to the same Wi-Fi, scan below and sign in with a food-counter account.</p>${s.addresses.map(a=>`<div style="display:inline-block;text-align:center;padding:12px"><img src="/api/connect-qr?ip=${encodeURIComponent(a.ip)}" alt="Phone login QR" style="width:220px;max-width:100%"><p><a href="${escapeHtml(a.url)}">${escapeHtml(a.url)}</a></p></div>`).join('')||'<p>Connect this laptop to Wi-Fi to show the phone login QR.</p>'}${s.phone_setup_url?`<p>First-time phone: <a href="${escapeHtml(s.phone_setup_url)}" target="_blank" rel="noopener">open certificate setup</a>, install and trust the event certificate, then scan the login QR.</p>`:''}`;

}
async function serverPage(){
 const s=await api('/api/server-info');if(state.page!=='server')return;
 const devices=s.devices||[],active=devices.filter(d=>d.online);
 const urls=(s.addresses||[]).map((a,i)=>`<div class="server-url"><div class="server-url-text"><small>LOCAL LINK ${i+1}</small><b>${escapeHtml(a.url)}</b></div><div class="actions"><button class="btn small" data-copy="${escapeHtml(a.url)}">Copy</button><button class="btn small" data-pair="${escapeHtml(a.ip)}">Show QR</button></div></div>`).join('');
 $('#content').innerHTML=pagehead('Your laptop is the server','Runs on this laptop with no cloud, internet or external database.',`<button class="btn" id="refresh-server">↻ Refresh status</button><a class="btn primary" href="/api/backup" id="download-backup">↓ Backup database</a>`)+`
 <section class="server-hero panel"><div><div class="hero-eyebrow"><span class="mini-dot"></span> PRIVATE OFFLINE OPERATIONS</div><h2>One laptop. One live database.<br>Every food counter stays in sync.</h2><p>Local data stays on your laptop. Use the laptop by itself, or create a private Wi-Fi network for additional counters. No internet is needed.</p><div class="server-modes"><span>✓ Laptop-only: no network</span><span>✓ Multiple counters: local Wi-Fi only</span></div></div><div class="hero-glyph">◉</div></section>
 <div class="server-stat-grid"><div class="server-stat"><small>SERVER STATUS</small><b class="text-green">● Running</b><span>Local port ${num(s.port)}</span></div><div class="server-stat"><small>FOOD COUNTERS</small><b>${s.gate.open?'Open':'Closed'}</b><span>${num(s.gate.active_counters)} registered</span></div><div class="server-stat"><small>DEVICES ACTIVE</small><b>${num(active.length)}</b><span>Seen within 25 seconds</span></div><div class="server-stat"><small>STUDENTS LOADED</small><b>${num(s.gate.imported)}</b><span>${num(s.gate.eligible)} ready to redeem</span></div></div>
 <div class="dashboard-grid server-grid"><section class="panel"><div class="between"><h3>Counter connection</h3>${badge('NO INTERNET REQUIRED','good')}</div><p class="panel-sub">Open the app on every counter phone using a local address below.</p><div class="server-url"><div class="server-url-text"><small>THIS LAPTOP ONLY</small><b>${escapeHtml(s.localhost)}</b></div><button class="btn small" data-copy="${escapeHtml(s.localhost)}">Copy</button></div>${urls || (`<div class="hint warning">${s.mode === 'laptop_only' ? 'Laptop-only mode is selected. To connect phones, stop the desktop server, choose Multiple counters, then restart.' : 'No local Wi-Fi address detected. Start a private router/hotspot, connect this laptop, then click Refresh.'}</div>`)}<div class="hint" style="margin-top:14px"><b>Connect phones:</b> Join the same private Wi-Fi network as this laptop, then type or scan a local link. Do not connect the router to the internet. Disable client/AP isolation.</div><div class="hint warning" style="margin-top:10px"><b>Live phone camera:</b> ${s.tls?'HTTPS is enabled. Trust the event certificate on every staff phone, then open the secure link above and tap Start live camera.':'Use localhost or a trusted HTTPS connection for browser live scanning.'}</div>${s.phone_setup_url?`<div class="server-url"><div class="server-url-text"><small>FIRST-TIME PHONE CERTIFICATE SETUP</small><b>${escapeHtml(s.phone_setup_url)}</b></div><button class="btn small" data-copy="${escapeHtml(s.phone_setup_url)}">Copy</button></div><p class="panel-sub">Open this HTTP setup page on the phone only to download the PUBLIC CA certificate, then install/enable trust in Settings. Never enter passwords on the setup page.</p><div class="hint"><b>CA SHA256:</b><br><span class="code">${escapeHtml(s.phone_ca_fingerprint||'')}</span></div>`:''}</section>
 <section class="panel"><div class="between"><h3>Live connected staff</h3>${badge(active.length+' active','good')}</div><p class="panel-sub">Devices appear after counter staff sign in and heartbeat locally.</p><div class="device-list">${devices.length?devices.map(d=>`<div class="device-line"><div><b>${escapeHtml(d.counter_name||d.username)}</b><small>${escapeHtml(d.device_ip)} · ${escapeHtml(d.role)}</small></div>${badge(d.online?'Online':'Idle',d.online?'good':'wait')}</div>`).join(''):'<div class="empty">No signed-in devices yet. Sign in on another counter phone.</div>'}</div><div class="divider"></div><h3>Server readiness</h3><div class="ready-row">${s.gate.imported?'✓':'○'} Student CSV imported</div><div class="ready-row">${s.gate.eligible?'✓':'○'} Present, approved food passes</div><div class="ready-row">${s.gate.active_counters?'✓':'○'} Active staff counter accounts</div><div class="ready-row">${s.gate.open?'✓':'○'} Distribution opened by administrator</div><p class="panel-sub" style="margin-top:14px">Last import: ${s.last_import?escapeHtml(formatIST(s.last_import.at)):'Not yet imported'}</p></section></div>
 <section class="panel"><h3>Choose your event setup</h3><div class="server-setup-cards"><div class="setup-card"><strong>01 · Laptop-only</strong><p>No Wi-Fi, no router, no phone. Connect a USB QR scanner to the laptop, open localhost, and select Try scanner. Fully standalone.</p></div><div class="setup-card"><strong>02 · Multiple counters</strong><p>Use an offline private Wi-Fi router (recommended) or a laptop hotspot if your OS supports one without internet. Connect the laptop and counter phones to it.</p></div><div class="setup-card"><strong>03 · Before students arrive</strong><p>Import your approved attendance CSV, create counter accounts, open distribution, and test an actual QR twice across two desks.</p></div></div></section>`;
 $('#refresh-server').onclick=()=>navigate('server');
 $('#content').querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText(b.dataset.copy);toast('Local link copied.','success')}catch{toast('Copy the address shown above manually.','error')}});
 $('#content').querySelectorAll('[data-pair]').forEach(b=>b.onclick=()=>{let ip=b.dataset.pair;let url=`${s.tls?'https':'http'}://${ip}:${s.port}`;modal(`<div class="between"><h3>Connect a counter phone</h3><button class="btn small" data-close>✕</button></div><div class="pair-qr"><img src="/api/connect-qr?ip=${encodeURIComponent(ip)}" alt="Local server connection QR"></div><p class="muted" style="text-align:center">${escapeHtml(url)}</p><p class="muted">Connect the phone to the same private Wi-Fi first. Then scan this QR to open the counter login.</p><div class="modal-actions"><button class="btn primary" data-close>Done</button></div>`)});
}
async function guide(){$('#content').innerHTML=pagehead('Event setup guide','A practical checklist to keep all counters running safely without internet.')+`<div class="hint"><b>Two offline modes:</b> A single laptop with USB QR scanner works with NO network. For phones, a PRIVATE LOCAL Wi-Fi connection is required, but never the internet. See Laptop server for the addresses and QR pairing.</div><div class="dashboard-grid"><section class="panel"><h3>Before food distribution</h3><ol class="instructions"><li>Install Python and dependencies <b>while internet is available</b>. Run the launcher on your main event laptop.</li><li>Create the administrator password (12+ characters) and create a staff login for each counter.</li><li>On your online website, send QR emails only after attendance is approved. Export the same QR tokens, meal type and student details as CSV.</li><li>Import the CSV here. Confirm the present count and Veg / Non-Veg totals.</li><li>Connect the server laptop and every phone to one private router/hotspot, with internet turned off for a full test.</li><li>On each staff phone, open the public certificate setup page (shown under Laptop server), install and fully trust the event CA, then open the HTTPS scanner. Test the live camera and duplicate blocking.</li><li>Keep the laptop awake, plugged in and (for phone counters) connected to the router until the event ends.</li><li>When finished, export the CSV report and back up the <span class="code">data/</span> folder.</li></ol></section><section class="panel"><h3>Scanning options</h3><div class="meal-row"><div><b>Native phone live camera (HTTP LAN)</b><br><small class="muted">An optional alternative when a device cannot trust the event CA. Requires an installed native companion app.</small></div>${badge('Phone primary','good')}</div><div class="meal-row"><div><b>Live browser camera</b><br><small class="muted">PRIMARY: Works in Safari/Chrome over locally trusted HTTPS, without an app. Open Start live camera. If native QR decoding is unavailable, the laptop decodes frames offline.</small></div>${badge('Phone primary','good')}</div><div class="meal-row"><div><b>Take QR photo</b><br><small class="muted">Use the phone camera to take a still picture. The laptop decodes it locally through OpenCV.</small></div>${badge('Recommended','good')}</div><div class="meal-row"><div><b>Laptop webcam without browser permission</b><br><small class="muted">On the laptop open localhost (HTTP or HTTPS), select QR scanner, then Use laptop webcam. Python/OpenCV captures locally.</small></div>${badge('Offline live','good')}</div><div class="meal-row"><div><b>USB/Bluetooth QR reader</b><br><small class="muted">Reader inputs QR text as keyboard. Enter to check.</small></div>${badge('Fastest','good')}</div><div class="divider"></div><div class="hint warning"><b>Important:</b> Ordinary <span class="code">http://192.168.x.x</span> LAN pages may not receive live browser-camera permission on iPhone/Android. Still-photo capture works as a fallback in supported mobile browsers. For live phone scanning in a normal browser, connect to the HTTPS phone-counter URL and install/fully trust the public event CA certificate first. An installed native companion app can be used as an alternative.</div><div class="divider"></div><h3>Protection against duplicates</h3><p class="muted">Every redemption is saved in one SQLite transaction on the main laptop. The same QR cannot be marked served twice, even by two counters at the same moment. If a phone loses LAN connectivity, <b>stop serving on that counter</b> until it reconnects.</p></section></div>`}
function buildVerification(data){const right=$('#scan-verification');if(!right)return;state.scanResult=data;
 if(data && window.innerWidth<850)requestAnimationFrame(()=>right.scrollIntoView({behavior:'smooth',block:'start'}));
 if(!data){right.innerHTML=`<div class="verification"><span class="big-icon purple">▧</span><div class="verify-title">Ready to verify</div><p class="muted">Scan a student's QR to see their identity, meal preference and collection status.</p></div>`;return}
 const s=data.student;if(data.status==='valid'&&s){right.innerHTML=`<div class="verification verify-ok"><span class="big-icon green">✓</span><div class="verify-title text-green">${s.demo?'TEST / DEMO QR VALID — NO FOOD':'VALID FOOD PASS'}</div><p class="student-name">${escapeHtml(s.name)}</p><div class="muted">${escapeHtml(s.reg_no)} · ${escapeHtml(s.department)} ${escapeHtml(s.section)}</div><div class="details"><div class="detail-box"><span>FOOD TYPE</span><b>${mealBadge(s.food_type)}</b></div><div class="detail-box"><span>ATTENDANCE</span><b class="text-green">✓ PRESENT</b></div></div><p class="muted" style="font-size:11px">${s.demo?'DEMO ONLY — no actual meal is authorized. Try redeeming twice to test duplicates.':'Confirm the student\'s identity and meal type before handing over the food.'}</p><button class="btn success verify-btn" id="give-food">${s.demo?'SIMULATE DEMO REDEMPTION':'✓ GIVE FOOD — MARK COLLECTED'}</button><button class="btn small" id="cancel-scan" style="margin-top:10px">Cancel / New scan</button></div>`;$('#give-food').onclick=redeem;$('#cancel-scan').onclick=()=>{resetScan();if(nativePhoneAvailable())startNativePhoneScanner();else if(window.isSecureContext)startLive()};return}
 if(data.status==='served'&&s){right.innerHTML=`<div class="verification verify-done"><span class="big-icon green">✓</span><div class="verify-title text-green">${s.demo?'DEMO REDEEMED — NO FOOD':'COLLECTION SAVED — GIVE FOOD'}</div><p class="student-name">${escapeHtml(s.name)}</p><p>${mealBadge(s.food_type)}</p><p class="muted">Collection time: ${escapeHtml(formatIST(s.redeemed_at))} · ${escapeHtml(s.redeemed_counter||'counter')}</p><button class="btn primary verify-btn" id="scan-next">Scan next student →</button></div>`;$('#scan-next').onclick=()=>{resetScan();if(nativePhoneAvailable())startNativePhoneScanner();else if(window.isSecureContext)startLive()};return}
 const used=data.status==='used',blocked=data.status==='blocked',closed=data.status==='closed';right.innerHTML=`<div class="verification verify-deny"><span class="big-icon red">✕</span><div class="verify-title text-red">${used?'ALREADY COLLECTED':blocked?'PASS NOT APPROVED':closed?'COUNTERS CLOSED':data.status==='unavailable'?'VERIFICATION NOT COMPLETED':'INVALID / POSSIBLY FAKE QR'}</div>${s?`<p class="student-name">${escapeHtml(s.name)}</p><div class="muted">${escapeHtml(s.reg_no)} · ${mealBadge(s.food_type)}</div>`:''}<p style="margin-top:12px">${escapeHtml(data.message||data.error||'This pass cannot be redeemed.')}</p>${used&&s?.redeemed_at?`<p class="muted">You already collected on ${escapeHtml(formatIST(s.redeemed_at))} · ${escapeHtml(s.redeemed_counter||'Counter')}</p>`:''}<div class="status-tag bad" style="margin:8px auto 20px">DO NOT GIVE FOOD</div><button class="btn primary verify-btn" id="scan-next">Scan next student →</button></div>`;$('#scan-next').onclick=()=>{resetScan();if(nativePhoneAvailable())startNativePhoneScanner();else if(window.isSecureContext)startLive()};}
async function scanner(){const isCounter=state.user?.role==='counter';$('#content').innerHTML=pagehead('QR food scanner','A valid first scan saves collection automatically. Match the student ID before scanning. No internet needed.',isCounter?'':`<button class="btn" id="open-guide">? Scanner guide</button>`)+`<div class="counter-layout"><div class="quick-stats"><span class="quick-stat"><b>✓</b>Connected desks share one database</span><span class="quick-stat"><b>1×</b>One meal per approved QR</span></div><div class="scanner-grid"><section class="panel"><h3>Scan student's food pass</h3><p class="panel-sub">Use your phone camera, QR reader or paste the QR token.</p><div class="camera-box" id="camera-box"><div class="camera-empty"><div class="camera-mark">▧</div><b>Ready to scan</b><p style="color:#9ba9c7;font-size:12px;margin:8px 0 0">Align QR within camera frame</p></div></div>${nativePhoneAvailable()?'<button class="btn primary native-phone-action" id="start-phone-native">▣ SCAN QR WITH PHONE CAMERA</button>':''}<div class="camera-controls"><button class="btn primary" id="start-live">▣ START LIVE PHONE CAMERA</button><label class="btn soft" for="scan-photo">◉ Take QR photo</label><input id="scan-photo" type="file" accept="image/*" capture="environment" class="hidden"></div>${['localhost','127.0.0.1','::1'].includes(location.hostname)?'<button class="btn camera-local-btn" id="start-laptop">◉ Use laptop webcam · works on HTTP</button>':''}<p class="camera-status" id="camera-status" role="status"></p><form id="manual-form" class="manual-form"><input id="manual-token" placeholder="Paste QR token / use QR scanner" autocomplete="off" aria-label="Enter scanned QR token"><button type="submit" class="btn">Check QR →</button></form><p class="scan-footer">Photos are decoded on this event laptop. No cloud OCR or internet is used.</p></section><section class="panel" id="scan-verification"></section></div><div class="hint warning" style="margin-top:19px">Live QR works in Safari or Chrome on the locally trusted HTTPS URL. If the browser says Not Secure, first install and fully trust the event CA certificate using the Phone HTTPS Setup link. No internet or native phone app is needed.</div></div>`;
if($('#open-guide'))$('#open-guide').onclick=()=>navigate('guide');const nativeButton=$('#start-phone-native');if(nativeButton)nativeButton.onclick=startNativePhoneScanner;buildVerification(null);$('#manual-form').onsubmit=e=>{e.preventDefault();checkToken($('#manual-token').value)};$('#scan-photo').onchange=photoSelected;$('#start-live').onclick=startLive;const webcam=$('#start-laptop');if(webcam)webcam.onclick=startLaptopCamera;const status=$('#camera-status');if(status){status.textContent=nativePhoneAvailable()?'Native phone camera ready · works with offline local HTTP. Tap the large purple button to scan.':!window.isSecureContext?'Live phone camera is blocked on ordinary HTTP LAN addresses. Use Take QR photo / Bluetooth QR scanner. Laptop webcam mode runs on localhost without HTTPS.':'Live scanning available with camera permission. Native QR decoding or offline laptop decoding will be used.'}if(!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent))$('#manual-token').focus();}

// Native iPhone/Android bridge: the installed app scans with AVFoundation/CameraX
// and passes ONLY the decoded QR text to the existing authenticated verification.
// No QR or student data is ever sent to a cloud service.
function nativePhoneAvailable(){
 return !!(window.webkit?.messageHandlers?.techvistraScanner || window.TechvistraAndroid?.openScanner);
}
function startNativePhoneScanner(){
 if(!state.user){toast('Sign in to your food counter first.','error');return}
 if(state.scanBusy){toast('Finish the current check first.','error');return}
 if(window.webkit?.messageHandlers?.techvistraScanner){
   window.webkit.messageHandlers.techvistraScanner.postMessage('open');return;
 }
 if(window.TechvistraAndroid?.openScanner){window.TechvistraAndroid.openScanner();return}
 cameraMessage('Install the TECHVISTRA phone scanner app for a live phone camera over local HTTP.',true);
}
window.techvistraReceiveNativeQR=async function(scanned){
 if(!state.user){toast('Sign in before scanning.','error');return}
 if(state.page!=='scanner'){toast('Open Scan food passes before scanning.','error');return}
 if(typeof scanned!=='string'||!scanned.trim()||scanned.length>2400){
   toast('QR code is empty or too long.','error');return;
 }
 // Validation and one-time collection are enforced by the laptop server.
 await checkToken(scanned);
};

function resetScan(){if(state.scanToken&&state.scanResult?.status==='valid')api('/api/cancel-scan',{token:state.scanToken}).catch(()=>{});state.scanToken='';state.scanResult=null;buildVerification(null);const input=$('#manual-token');if(input){input.value='';input.focus()}let f=$('#scan-photo');if(f)f.value=''}
async function checkToken(raw){
 if(state.scanBusy)return;
 stopLive();const token=(raw||'').trim();if(!token)return toast('Scan a QR before continuing.','error');
 state.scanToken=token;state.scanBusy=true;
 try{
  let x=await api('/api/check',{token});
  if(x.status==='valid' && x.student && !x.student.demo && !x.test_only){
   x=await api('/api/redeem',{token});
   toast('Collection saved. Give food only to the student shown.','success');
  }
  buildVerification(x);
 }catch(e){
  buildVerification({status:e.data?.status||'unavailable',student:e.data?.student,message:e.message});
 }finally{state.scanBusy=false}
}
async function redeem(){if(state.scanBusy||!state.scanToken)return;state.scanBusy=true;let button=$('#give-food');if(button){button.disabled=true;button.textContent='Saving redemption…'}try{const x=await api('/api/redeem',{token:state.scanToken});buildVerification(x);toast(x.demo?'TEST simulated — no food served.':'Food marked collected successfully.','success')}catch(e){buildVerification({status:e.data?.status||'invalid',student:e.data?.student,message:e.message});toast(e.message,'error')}finally{state.scanBusy=false}}
async function photoSelected(e){const file=e.target.files[0];if(!file)return;toast('Reading QR from photo…');try{const image=await prepareQrPhoto(file);const x=await api('/api/decode-photo',{image});$('#manual-token').value=x.token;await checkToken(x.token)}catch(e){toast(e.message,'error')}finally{e.target.value=''}}
function prepareQrPhoto(file){return new Promise((resolve,reject)=>{
 const url=URL.createObjectURL(file);const img=new Image();
 img.onload=()=>{try{const max=1700,scale=Math.min(1,max/Math.max(img.naturalWidth,img.naturalHeight));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(img.naturalWidth*scale));canvas.height=Math.max(1,Math.round(img.naturalHeight*scale));const context=canvas.getContext('2d');context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(img,0,0,canvas.width,canvas.height);const result=canvas.toDataURL('image/jpeg',0.88);URL.revokeObjectURL(url);resolve(result)}catch(e){URL.revokeObjectURL(url);reject(new Error('Could not process this camera photo.'))}};
 img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('Unsupported image format. Please take a new QR photo.'))};img.src=url;
})}
function cameraMessage(message, error=false){
 const status=$('#camera-status');if(status){status.textContent=message;status.classList.toggle('error',error)}
}
function cameraEmpty(){
 const box=$('#camera-box');if(box)box.innerHTML='<div class="camera-empty"><div class="camera-mark">▧</div><b>Ready to scan</b><p style="color:#9ba9c7;font-size:12px;margin:8px 0 0">Align QR within camera frame</p></div>';
}
let qrCanvas=null,qrFrameCount=0,lastServerFrame=0;
async function browserFrameDecode(video){
 if(!video.videoWidth)return '';
 qrCanvas=qrCanvas||document.createElement('canvas');
 const w=video.videoWidth,h=video.videoHeight;
 // Alternate centered square and full view to retain detail on dense passes.
 const crop=(++qrFrameCount%4)!==0;
 const side=Math.min(w,h),sw=crop?side:w,sh=crop?side:h;
 const ratio=Math.min(1,(crop?960:1280)/Math.max(sw,sh));
 qrCanvas.width=Math.round(sw*ratio);qrCanvas.height=Math.round(sh*ratio);
 const context=qrCanvas.getContext('2d',{willReadFrequently:true});
 context.drawImage(video,crop?(w-side)/2:0,crop?(h-side)/2:0,sw,sh,0,0,qrCanvas.width,qrCanvas.height);
 if(typeof window.jsQR==='function'){
   const pixels=context.getImageData(0,0,qrCanvas.width,qrCanvas.height);
   const result=window.jsQR(pixels.data,pixels.width,pixels.height,{inversionAttempts:'dontInvert'});
   if(result?.data)return result.data;
 }
 // Retain occasional laptop fallback, rather than sending every camera frame.
 if(performance.now()-lastServerFrame<2500)return '';
 lastServerFrame=performance.now();
 try{
   const decoded=await api('/api/decode-photo',{image:qrCanvas.toDataURL('image/jpeg',0.88)});
   return decoded.token||'';
 }catch(e){if(e.status===422)return '';throw e;}
}

async function startLive(){
 if(state.localCameraActive||state.stream)stopLive();
 if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
   const message='This phone/browser cannot open a live camera on HTTP LAN. For a live browser camera use trusted HTTPS or open localhost on the SAME device. For HTTP, try Take QR photo or a Bluetooth 2D QR reader.';
   cameraMessage(message,true);toast('Browser blocked live camera on this address.','error');return;
 }
 let stream=null;
 try{
  stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});
  if(state.page!=='scanner'){stream.getTracks().forEach(t=>t.stop());return}
  state.stream=stream;
  const epoch=++state.scanEpoch;
  const box=$('#camera-box');box.innerHTML='<video id="live-video" autoplay muted playsinline></video>';
  const video=$('#live-video');video.srcObject=stream;await video.play();
  if(epoch!==state.scanEpoch||!state.stream)return;
  state.detector=null;
  if('BarcodeDetector' in window){
    try{
      const formats=typeof BarcodeDetector.getSupportedFormats==='function'?await BarcodeDetector.getSupportedFormats():['qr_code'];
      if(formats.includes('qr_code'))state.detector=new BarcodeDetector({formats:['qr_code']});
    }catch(e){state.detector=null}
  }
  qrFrameCount=0;lastServerFrame=performance.now();let nativeMisses=0;
  $('#start-live').textContent='■ Stop live camera';$('#start-live').onclick=stopLive;
  cameraMessage('Live camera active · keep the QR centered, steady and large in the frame · scanning on your phone');
  let running=false;
  state.scanTimer=setInterval(async()=>{
    if(running||!state.stream||epoch!==state.scanEpoch||state.page!=='scanner')return;
    if(video.readyState<2)return;
    running=true;
    try{
      let token='';
      if(state.detector){try{const hits=await state.detector.detect(video);token=hits[0]?.rawValue||''}catch(e){state.detector=null}}
      if(!token){nativeMisses++;if(!state.detector||nativeMisses%4===0)token=await browserFrameDecode(video);}
      if(token&&epoch===state.scanEpoch){stopLive();await checkToken(token)}
    }catch(e){if(epoch===state.scanEpoch){stopLive();cameraMessage(e.message,true);toast(e.message,'error')}}
    finally{running=false}
  },220);
 }catch(e){
   if(stream&&!state.stream)stream.getTracks().forEach(t=>t.stop());
   stopLive();
   const message=e.name==='NotAllowedError'?'Camera permission denied. Allow camera access for this browser in device settings and reload.':e.name==='NotFoundError'?'No usable camera detected. Connect a webcam or use QR photo.':e.message;
   cameraMessage(message,true);toast(message,'error');
 }
}
async function startLaptopCamera(){
 if(state.localCameraActive)return stopLive();
 stopLive();
 if(!['localhost','127.0.0.1','::1'].includes(location.hostname)){
  cameraMessage('Laptop webcam works only from localhost on the event laptop.',true);return;
 }
 const epoch=++state.scanEpoch;
 cameraMessage('Opening the laptop camera…');
 try{
  await api('/api/local-camera/start',{});
  if(epoch!==state.scanEpoch||state.page!=='scanner'){
   await api('/api/local-camera/stop',{}).catch(()=>{});return;
  }
  state.localCameraActive=true;
  const box=$('#camera-box');box.innerHTML='<img id="laptop-camera-frame" alt="Live event laptop webcam preview">';
  const b=$('#start-laptop');if(b){b.textContent='■ Stop laptop webcam';b.onclick=stopLive}
  cameraMessage('Laptop webcam live · OpenCV reads the camera locally over HTTP · no browser camera permission needed');
  async function poll(){
   if(!state.localCameraActive||epoch!==state.scanEpoch||state.page!=='scanner')return;
   try{
    const result=await api('/api/local-camera/frame');
    if(!state.localCameraActive||epoch!==state.scanEpoch)return;
    const frame=$('#laptop-camera-frame');if(frame)frame.src=result.image;
    if(result.token){stopLive();await checkToken(result.token);return}
   }catch(e){
    if(epoch===state.scanEpoch){stopLive();cameraMessage(e.message,true);toast(e.message,'error')}
    return;
   }
   if(state.localCameraActive&&epoch===state.scanEpoch)state.scanTimer=setTimeout(poll,360);
  }
  poll();
 }catch(e){if(epoch===state.scanEpoch){stopLive();cameraMessage(e.message,true);toast(e.message,'error')}}
}
function stopLive(){
 ++state.scanEpoch;
 if(state.scanTimer){clearInterval(state.scanTimer);clearTimeout(state.scanTimer);state.scanTimer=null}
 if(state.stream){state.stream.getTracks().forEach(t=>t.stop());state.stream=null}
 state.detector=null;
 if(state.localCameraActive){state.localCameraActive=false;api('/api/local-camera/stop',{}).catch(()=>{})}
 const b=$('#start-live');if(b){b.textContent='▣ START LIVE PHONE CAMERA';b.onclick=startLive}
 const local=$('#start-laptop');if(local){local.textContent='◉ Use laptop webcam · works on HTTP';local.onclick=startLaptopCamera}
 cameraEmpty();
}

boot();

let livePoll;
async function refreshLiveSummary(){
 try {const x=await api('/api/live');if(state.page==='dashboard' && $('#live-summary'))$('#live-summary').textContent=`${x.devices.filter(d=>d.online).length} devices online · ${x.requests.filter(r=>r.status==='valid').length} recent valid scans awaiting collection save`; }catch{}
}
function tableHtml(headers, rows){return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">No records yet</td></tr>`}</tbody></table></div>`}
async function liveOperations(){
 $('#content').innerHTML=pagehead('Live operations','Phones report online while signed in and sending heartbeats. Devices become offline after 22 seconds without a heartbeat.', '<button class="btn" id="live-export">Export full food report</button>')+`<p id="live-updated" role="status">Connecting…</p><div id="operations-data"></div>`;
 $('#live-export').onclick=()=>location.href='/api/export';await refreshOperations();
}
async function refreshOperations(){
 const x=await api('/api/live');if(state.page!=='live'||!$('#operations-data'))return;
 $('#live-updated').textContent='Live · updated '+formatIST(x.time)+' · refreshes every 3 seconds';
 $('#operations-data').innerHTML=`<div class="stats-grid">${stat('Devices online',x.devices.filter(d=>d.online).length,'Heartbeat within 22 seconds','green','◉')}${stat('Checks awaiting save',x.requests.filter(r=>r.status==='valid').length,'Within latest 100 scans','orange','◷')}</div><section class="panel"><h3>Connected phones & devices</h3><p class="panel-sub">One entry per browser profile. Use a separate staff account and device label on each phone. Clearing cookies creates a new device.</p>${tableHtml(['Device / staff','Connection','Last seen','Veg','Non-Veg','Food given'],x.devices.map(d=>[`${escapeHtml(d.label)}<br><small>@${escapeHtml(d.username)} · ${escapeHtml(d.ip)}</small><details><summary>Browser</summary>${escapeHtml(d.agent)}</details>`,badge(d.online?'Online':'Offline',d.online?'good':'bad'),d.last_seen?escapeHtml(formatIST(d.last_seen*1000)):'Signed out',num(d.veg),num(d.nonveg),`<b>${num(d.served)}</b>`]))}</section><section class="panel" style="margin-top:20px"><h3>Live scan requests</h3><p class="panel-sub">Latest 100 checks. A valid first scan automatically saves collection. Give food only after COLLECTION SAVED appears. An interrupted request must be rescanned to confirm its saved status. Demo checks never count as meals.</p>${tableHtml(['Time','Staff','Student','Meal','Result'],x.requests.map(r=>[escapeHtml(formatIST(r.at)),escapeHtml(r.username),escapeHtml(r.name||r.reg_no||'Unrecognized pass'),escapeHtml(r.food_type),badge(r.status==='valid'?'Checks awaiting save':r.status,r.status==='served'?'good':'')]))}</section><section class="panel" style="margin-top:20px"><h3>Food given list</h3><p class="panel-sub">Latest 100 real meals. Export the full report for all records. Older meals retain their original counter and may have no device attribution.</p>${tableHtml(['Given at','Student','Meal','Counter','Device'],x.served.map(r=>[escapeHtml(formatIST(r.redeemed_at)),`${escapeHtml(r.name)}<br>${escapeHtml(r.reg_no)}`,mealBadge(r.food_type),escapeHtml(r.redeemed_counter),escapeHtml(r.device)]))}</section>`;
}
async function pollOperations(){
 try {if(state.user?.role==='admin'&&state.page==='live')await refreshOperations();else if(state.user?.role==='admin'&&state.page==='dashboard')await refreshLiveSummary();else if(state.user?.role==='counter'&&state.page==='scanner'){
 const x=await api('/api/my-device');let box=$('#phone-totals');if(!box){box=el('div','hint');box.id='phone-totals';$('#content').prepend(box);}box.textContent=`This device: ${num(x.total)} meals given · Veg ${num(x.veg)} · Non-Veg ${num(x.nonveg)}`;
 }}catch(e){if(state.page==='live'&&$('#live-updated'))$('#live-updated').textContent='Connection lost — displayed data is stale. '+e.message;}finally{livePoll=setTimeout(pollOperations,3000)}
}
pollOperations();
