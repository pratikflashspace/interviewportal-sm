import assert from 'node:assert/strict';
export async function checkMyApplications(browser){
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 try{
  const page=await context.newPage();page.setDefaultTimeout(15000);let user={role:'candidate',admin:false,name:'Synthetic Candidate'},fail=false,reads=0;
  const active={id:'active',role_title:'Synthetic Engineering',created_at:'2026-09-10T08:00:00Z',stage:'applied',interview_status:'interview',version:0,flow_version:2,events:[]};
  const complete={...active,id:'complete',role_title:'Synthetic Marketing',created_at:'2026-09-12T08:00:00Z',stage:'shortlisted',interview_status:'completed',version:1,events:[{stage:'shortlisted',created:'2026-09-13T08:00:00Z',actor:'HIDDEN-ACTOR'}],evaluation:{score:99},notes:'HIDDEN-NOTES'};
  let rows=[active,complete];
  await page.route('**/api/me',r=>r.fulfill({json:user}));
  await page.route('**/api/workspace/candidate/applications',r=>{reads++;assert.equal(r.request().method(),'GET');return r.fulfill(fail?{status:500,json:{error:'secret diagnostic'}}:{json:rows});});
  await page.route('**/interview-v2?application=*',r=>r.fulfill({contentType:'text/html',body:'Synthetic existing interview destination. No recording.'}));
  const open=()=>page.goto('http://127.0.0.1:8765/candidate/workspace/applications');
  const card=name=>page.getByRole('article').filter({has:page.getByRole('heading',{name,exact:true})});
  await open();await page.getByText('2 applications found · Newest first',{exact:true}).waitFor();
  assert.deepEqual(await page.locator('.ma-card h2').allTextContents(),['Synthetic Marketing','Synthetic Engineering']);
  assert.equal(await page.locator('a[href*="recruiter"]').count(),0);
  assert.equal(await page.locator('.tr-main>header').getByRole('link',{name:'My Profile',exact:true}).getAttribute('href'),'/candidate/workspace/profile');
  await page.getByLabel('Search by role',{exact:true}).fill('engineering');await page.getByText('1 application found · Newest first',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Clear filters',exact:true}).click();await page.getByLabel('Hiring status',{exact:true}).selectOption('shortlisted');await page.getByLabel('Interview status',{exact:true}).selectOption('completed');await page.getByText('1 application found · Newest first',{exact:true}).waitFor();
  await card('Synthetic Marketing').getByRole('button',{name:'View application',exact:true}).click();const modal=page.getByRole('dialog');await modal.waitFor();
  assert.equal(await modal.locator('.ma-timeline li').count(),2);assert.equal(await modal.getByRole('button',{name:'Continue interview',exact:true}).count(),0);
  assert.equal(await modal.getByText('Date not recorded',{exact:true}).count(),1);
  const text=await modal.innerText();for(const forbidden of ['HIDDEN-ACTOR','HIDDEN-NOTES','Eligibility check','Assessment'])assert.equal(text.includes(forbidden),false);
  for(const width of [390,320]){await page.setViewportSize({width,height:844});const box=await modal.boundingBox();assert(box.x>=0&&box.x+box.width<=width+1);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
  await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});await page.getByRole('button',{name:'Clear filters',exact:true}).click();
  // A completed update after initial render must block stale continuation.
  rows=[{...active,interview_status:'completed',stage:'under_review'},complete];
  await card('Synthetic Engineering').getByRole('button',{name:'Continue interview',exact:false}).click();await page.getByText('This application cannot be continued. Its latest status is shown.',{exact:true}).waitFor();
  assert.equal(await card('Synthetic Engineering').getByRole('button',{name:'Continue interview',exact:false}).count(),0);
  await card('Synthetic Engineering').getByRole('button',{name:'View application',exact:true}).click();await modal.waitFor();await modal.getByRole('heading',{name:'Synthetic Engineering',exact:true}).waitFor();assert.equal(await modal.locator('.ma-timeline li').count(),1,'Inferred review must not create a timeline event');await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});
  rows=[active];await page.getByRole('button',{name:'Refresh applications',exact:true}).click();await page.getByText('1 application found · Newest first',{exact:true}).waitFor();await card('Synthetic Engineering').getByRole('button',{name:'Continue interview',exact:false}).click();await page.waitForURL('**/interview-v2?application=active');
  rows=[];await open();await page.getByRole('heading',{name:'No applications yet',exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'Explore Jobs →',exact:true}).getAttribute('href'),'/candidate/workspace/jobs');
  fail=true;await page.getByRole('button',{name:'Refresh applications',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.getByRole('heading',{name:'No applications yet',exact:true}).count(),0);
  fail=false;rows=[active];await page.getByRole('button',{name:'Try again',exact:true}).click();await page.getByText('1 application found · Newest first',{exact:true}).waitFor();await page.getByLabel('Search by role',{exact:true}).fill('does-not-match');await page.getByRole('heading',{name:'No matching applications',exact:true}).waitFor();
  const before=reads;user={role:'recruiter',admin:true,name:'Recruiter'};await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(reads,before);assert.equal(await page.locator('.ma-shell').count(),0);
  user=null;await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(reads,before);
  console.log('::notice title=My Applications acceptance::PASS: newest ordering, role/status filters, real/undated history, private-field exclusion, completed and stale continuation guard, existing interview navigation, empty/error/retry, candidate denial, 390/320px fit. Synthetic API data only.');
 }finally{await context.close();}
}
