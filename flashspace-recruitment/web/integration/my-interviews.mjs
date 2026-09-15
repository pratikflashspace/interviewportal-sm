import assert from 'node:assert/strict';
export async function checkMyInterviews(browser){
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 try{
  const page=await context.newPage();page.setDefaultTimeout(15000);let user={role:'candidate',admin:false,name:'Synthetic Candidate'},fail=false,reads=0;
  const active={id:'active',role_title:'Synthetic Engineering',created_at:'2026-09-10T08:00:00Z',stage:'applied',interview_status:'interview',version:0,flow_version:2,events:[]};
  const complete={...active,id:'complete',role_title:'Synthetic Marketing',stage:'under_review',interview_status:'completed',evaluation:{score:99},notes:'PRIVATE-RECRUITER-NOTE'};
  let rows=[active,complete];
  await page.route('**/api/me',r=>r.fulfill({json:user}));
  await page.route('**/api/workspace/candidate/applications',r=>{reads++;assert.equal(r.request().method(),'GET');return r.fulfill(fail?{status:500,json:{error:'private diagnostic'}}:{json:rows});});
  await page.route('**/interview-v2?application=*',r=>r.fulfill({contentType:'text/html',body:'Synthetic existing interview destination. No capture.'}));
  const open=()=>page.goto('http://127.0.0.1:8765/candidate/workspace/interviews');
  const card=name=>page.getByRole('article').filter({has:page.getByRole('heading',{name,exact:true})});
  await open();await card(active.role_title).waitFor();assert.equal(await card(complete.role_title).getByRole('button').count(),0);assert.equal(await page.locator('a[href*="recruiter"]').count(),0);
  assert.equal((await page.locator('body').innerText()).includes('PRIVATE-RECRUITER-NOTE'),false);
  assert.equal(await card(complete.role_title).getByText('Interview completion date: not recorded.',{exact:true}).count(),1);
  await page.getByLabel('Search by role',{exact:true}).fill('engineering');await page.getByText('No matching completed interviews.',{exact:true}).waitFor();await page.getByRole('button',{name:'Clear search',exact:true}).click();
  for(const width of [390,320]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
  await card(complete.role_title).getByRole('link',{name:'View application →',exact:true}).click();await page.waitForURL('**/applications?application=complete');await page.getByRole('dialog').getByRole('heading',{name:complete.role_title,exact:true}).waitFor();assert.equal(await page.getByRole('dialog').getByRole('button',{name:'Continue interview',exact:true}).count(),0);
  await page.goto('http://127.0.0.1:8765/candidate/workspace/applications?application=not-owned');await page.getByText('This application is not available in your account.',{exact:true}).waitFor();assert.equal(await page.getByRole('dialog').count(),0);
  await open();await card(active.role_title).waitFor();rows=[{...active,interview_status:'completed'},complete];await card(active.role_title).getByRole('button',{name:'Open / Continue interview',exact:true}).click();await page.getByText('This interview cannot be continued. Its latest status is shown.',{exact:true}).waitFor();assert.equal(await card(active.role_title).getByRole('button').count(),0);
  rows=[active];await page.getByRole('button',{name:'Refresh interviews',exact:true}).click();await card(active.role_title).getByRole('button',{name:'Open / Continue interview',exact:true}).click();await page.waitForURL('**/interview-v2?application=active');
  rows=[];await open();await page.getByRole('heading',{name:'No interviews yet',exact:true}).waitFor();
  fail=true;await page.getByRole('button',{name:'Refresh interviews',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.getByRole('heading',{name:'No interviews yet',exact:true}).count(),0);
  fail=false;rows=[active];await page.getByRole('button',{name:'Try again',exact:true}).click();await card(active.role_title).waitFor();
  const before=reads;user={role:'recruiter',admin:true,name:'Recruiter'};await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(reads,before);user=null;await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();assert.equal(reads,before);
  console.log('::notice title=My Interviews acceptance::PASS: recorded-state groups, role search, no invented completion dates/durations, completed and stale continuation guards, owned detail links, private-field exclusion, candidate denial, empty/error/retry, 390/320px fit. Synthetic APIs only.');
 }finally{await context.close();}
}
