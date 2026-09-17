// Synthetic UI responses only. Existing WSGI tests cover server-side isolation.
import assert from 'node:assert/strict';
export async function checkCandidateDashboard(browser){
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 try{
  const page=await context.newPage();page.setDefaultTimeout(15000);
  let user={role:'candidate',admin:false,name:'Synthetic Candidate'},apps=[],fields={},recommendations=[],fail=false,privateReads=0;
  const job={id:'synthetic-role',title:'Synthetic Engineering Role',department:'Engineering',location:'Remote',type:'Full-time',experience:'0–2 years',description:'Synthetic role description for testing only.',details:'Synthetic responsibilities and requirements.',skills:['Python','APIs'],internal_notes:'INTERNAL-DO-NOT-DISPLAY'};
  await page.route('**/api/me',route=>route.fulfill({json:user}));
  await page.route('**/api/workspace/candidate/applications',route=>{privateReads++;return route.fulfill(fail?{status:500,json:{error:'private error'}}:{json:apps});});
  await page.route('**/api/workspace/profile',route=>route.fulfill({json:{role:'candidate',version:0,fields}}));
  await page.route('**/api/workspace/candidate/recommendations',route=>route.fulfill({json:recommendations}));
  const open=()=>page.goto('http://127.0.0.1:8765/candidate/workspace/dashboard');
  const card=label=>page.locator('.cd-stat').filter({has:page.locator('.cd-stat-label',{hasText:label})});
  await open();await page.getByText('Recommendations start with your first application',{exact:true}).waitFor();
  assert.equal(await card('Applications').locator('strong').innerText(),'0');assert.equal(await card('Interviews').locator('strong').innerText(),'0 / 0');
  assert.equal(await page.locator('a[href*="recruiter"]').count(),0);
  assert.equal(await page.getByRole('navigation',{name:'Workspace',exact:true}).count(),1);assert.equal(await page.getByRole('navigation',{name:'Account',exact:true}).count(),1);
  assert.equal(await page.locator('.tr-main>header').getByRole('link',{name:'My Profile',exact:true}).getAttribute('href'),'/candidate/workspace/profile');
  assert.equal(await page.getByRole('heading',{level:1}).innerText().then(s=>s.includes('Synthetic Candidate')),true);
  apps=[{id:'first',interview_status:'completed',stage:'shortlisted'},{id:'second',interview_status:'interview',stage:'applied'}];fields={summary:'Synthetic summary',education:'Synthetic education'};recommendations=[{role:job,reason:'Same department as a role you applied for.'}];
  await page.getByRole('button',{name:'Refresh dashboard',exact:true}).click();
  await page.getByRole('heading',{name:job.title,exact:true}).waitFor();
  assert.equal(await card('Applications').locator('strong').innerText(),'2');assert.equal(await card('Interviews').locator('strong').innerText(),'1 / 2');assert.equal(await card('Shortlisted').locator('strong').innerText(),'1');assert.equal(await card('Profile completeness').locator('strong').innerText(),'29%');
  await page.getByText('How profile completeness is calculated',{exact:true}).click();assert.equal(await page.locator('.cd-completeness li').count(),7);
  assert.equal((await page.locator('body').innerText()).includes('INTERNAL-DO-NOT-DISPLAY'),false);
  for(const width of [390,320]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Dashboard fits '+width);}
  await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'View role',exact:false}).click();
  await page.getByRole('button',{name:'Apply for this role',exact:true}).waitFor();
  fields={summary:'New summary',education:'Education',experience:'Experience',skills:'Skills',projects:'Projects',preferences:'Preferences',resume_url:'https://example.com/resume'};
  await open();await page.waitForFunction(()=>document.querySelectorAll('.cd-stat strong')[3]?.textContent==='100%');
  fail=true;await page.getByRole('button',{name:'Refresh dashboard',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.locator('.cd-stat').count(),0,'Server failure must not render invented zeros');
  fail=false;await page.getByRole('button',{name:'Try again',exact:true}).click();await page.getByRole('heading',{name:job.title,exact:true}).waitFor();
  const before=privateReads;user={role:'recruiter',admin:true,name:'Synthetic Recruiter'};await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(await page.locator('.cd-shell').count(),0);assert.equal(privateReads,before);
  user=null;await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(privateReads,before);
  console.log('::notice title=Candidate Dashboard acceptance::PASS: empty/populated metrics, seven-section completeness, refresh/persistence reads, candidate-only access, safe recommendation modal, server-error recovery, 390/320px fit. Synthetic API responses; not live staging.');
 }finally{await context.close();}
}
