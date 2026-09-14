import assert from 'node:assert/strict';
export async function checkExploreJobs(browser){
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 try{
  const page=await context.newPage();page.setDefaultTimeout(15000);let fail=false,jobReads=0,applications=[],applies=0,user={role:'candidate',admin:false,name:'Synthetic Candidate'};
  const job={id:'synthetic-engineer',title:'Synthetic Engineer',department:'IT',location:'Remote/On-site - Both Available',type:'Full Time',experience:'0-1',description:'Synthetic engineering description.',details:'- Build Python tools\n- Test APIs\n\nRequirements:\n- Saved exact text\n<script>untrusted</script>',skills:['Python','APIs'],internal_notes:'NEVER-RENDER-THIS'};
  const jobs=[job,{...job,id:'synthetic-sales',title:'Synthetic Sales',department:'Sales',location:'Delhi',type:'Part-time',experience:'0-2 years experience',skills:['CRM'],details:'Maintain customer relationships.'}];
  await page.route('**/api/me',r=>r.fulfill({json:user}));
  await page.route('**/api/roles',r=>{jobReads++;return r.fulfill(fail?{status:500,json:{error:'private internal details'}}:{json:jobs});});
  await page.route('**/api/applications',r=>r.fulfill({json:applications}));
  await page.route('**/api/v2/applications',r=>{applies++;const body=r.request().postDataJSON();assert.equal(body.role_id,job.id);assert.equal(body.consent,true);assert.equal(body.consent_version,'flashspace-sarvam-conversation-v2');return r.fulfill({json:{application_id:'synthetic-created'}});});
  await page.route('**/interview-v2?application=*',r=>r.fulfill({contentType:'text/html',body:'Synthetic interview destination; no capture started.'}));
  const open=()=>page.goto('http://127.0.0.1:8765/candidate/workspace/jobs');
  const reset=()=>page.getByRole('button',{name:'Clear filters',exact:true}).click();
  const viewEngineer=()=>page.getByRole('article').filter({has:page.getByRole('heading',{name:job.title,exact:true})}).getByRole('button',{name:'View role',exact:false}).click();
  await open();await page.getByText('2 roles found',{exact:true}).waitFor();assert.equal(await page.locator('a[href*="recruiter"]').count(),0);
  await page.getByLabel('Search jobs, skills or keywords',{exact:true}).fill('saved exact');await page.getByText('1 role found',{exact:true}).waitFor();await reset();
  for(const [label,value] of [['Department','IT'],['Experience','0-1'],['Location',job.location],['Work mode',job.location],['Employment type','Full Time'],['Skills','Python']]){await page.getByLabel(label,{exact:true}).selectOption(value);await page.getByText('1 role found',{exact:true}).waitFor();assert.equal(await page.locator('.ej-page article h2').innerText(),job.title);await reset();}
  await page.getByLabel('Department',{exact:true}).selectOption('IT');await page.getByLabel('Skills',{exact:true}).selectOption('CRM');await page.getByRole('heading',{name:'No matching roles',exact:true}).waitFor();await reset();
  await viewEngineer();
  const modal=page.getByRole('dialog');await modal.waitFor();assert.equal(await modal.locator('.ej-saved-text').nth(1).textContent(),job.details);assert.equal(await modal.locator('.ej-saved-text').nth(1).evaluate(e=>getComputedStyle(e).whiteSpace),'pre-wrap');assert.equal(await modal.locator('script').count(),0);assert.equal((await page.locator('body').innerText()).includes('NEVER-RENDER-THIS'),false);
  for(const width of [390,320]){await page.setViewportSize({width,height:844});const box=await modal.boundingBox();assert(box.x>=0&&box.x+box.width<=width+1);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
  await page.setViewportSize({width:1440,height:1000});await modal.getByRole('button',{name:'Apply for this role',exact:true}).click();
  await page.getByRole('heading',{name:'First, a little about you.',exact:true}).waitFor();assert.equal(applies,0);
  await page.getByLabel('Relevant experience',{exact:true}).fill('Synthetic relevant experience for application transport.');await page.locator('#consent').click();await page.getByRole('button',{name:'Apply & start interview',exact:true}).click();await page.waitForURL('**/interview-v2?application=synthetic-created');assert.equal(applies,1);
  applications=[{id:'synthetic-existing',role_id:job.id,flow_version:2,status:'interview'}];await open();await viewEngineer();await page.getByRole('button',{name:'Apply for this role',exact:true}).click();await page.waitForURL('**/interview-v2?application=synthetic-existing');assert.equal(applies,1,'Existing application must not be recreated');
  fail=true;await open();await page.getByRole('alert').waitFor();assert.equal(await page.locator('article').count(),0);fail=false;await page.getByRole('button',{name:'Try again',exact:true}).click();await page.getByText('2 roles found',{exact:true}).waitFor();
  const count=jobReads;user={role:'recruiter',admin:true,name:'Synthetic Recruiter'};await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(jobReads,count);assert.equal(await page.locator('.ej-shell').count(),0);
  console.log('::notice title=Explore Jobs acceptance::PASS: exact saved multiline text, six literal-value filters, keyword search/clear/no-results, candidate-only access, safe role modal, 390/320px fit, retry, new Apply and existing resume without duplicate. Synthetic API responses only.');
 }finally{await context.close();}
}
