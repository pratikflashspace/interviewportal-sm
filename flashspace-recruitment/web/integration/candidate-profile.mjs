// Real local WSGI/SQLite profile persistence. Synthetic accounts only; no providers.
import assert from 'node:assert/strict';
export async function checkCandidateProfile(browser){
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const origin='http://127.0.0.1:8765',endpoint='/api/workspace/candidate/profile';
 const headers={'Origin':origin,'X-Requested-With':'Flashspace'};
 try{
  const page=await context.newPage();page.setDefaultTimeout(15000);page.on('dialog',dialog=>dialog.accept());
  const signup=await context.request.post(origin+'/api/auth/candidate/signup',{headers,data:{name:'Synthetic Profile Candidate',email:'profile-browser@example.com',password:'synthetic-profile-password',confirm_password:'synthetic-profile-password'}});assert.equal(signup.status(),200);
  const legacy='Original education text\nPreserved exactly.';
  const legacySave=await context.request.post(origin+'/api/workspace/profile',{headers,data:{version:0,fields:{education:legacy}}});assert.equal(legacySave.status(),200);
  const open=()=>page.goto(origin+'/candidate/workspace/profile');
  const get=async()=>{const r=await context.request.get(origin+endpoint);assert.equal(r.status(),200);return r.json();};
  const edit=title=>page.getByRole('button',{name:'Edit '+title,exact:true}).click();
  const save=async()=>{await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.getByRole('status').filter({hasText:'Profile saved.'}).waitFor();};
  const summary=()=>page.getByRole('textbox',{name:'Professional summary',exact:true});
  await open();await page.getByLabel('Login email',{exact:true}).waitFor();assert.equal(await page.getByLabel('Login email',{exact:true}).getAttribute('readonly'),'');assert.equal(await page.locator('a[href*="recruiter"]').count(),0);
  assert.equal(await page.locator('.cp-legacy p').textContent(),legacy);
  await edit('Personal details');await page.getByLabel('Full name *',{exact:true}).fill('Updated Profile Candidate');await page.getByLabel('Current city',{exact:true}).fill('Delhi');await page.getByLabel('Professional headline',{exact:true}).fill('Python developer');await save();
  assert.equal((await get()).sections.personal.city,'Delhi');
  await edit('Education');await page.getByRole('button',{name:'Add another education entry',exact:true}).click();await page.getByLabel('Qualification *',{exact:true}).fill('BSc');await page.getByLabel('Institution *',{exact:true}).fill('Synthetic College');await page.getByLabel('Start year',{exact:true}).fill('2020');await page.getByLabel('End year',{exact:true}).fill('2024');await save();
  assert.equal((await get()).legacy.education,legacy);assert.equal((await get()).sections.education.items[0].institution,'Synthetic College');
  await edit('Experience');await page.getByLabel('No work experience yet',{exact:true}).check();await save();assert.equal((await get()).sections.experience.no_experience,true);
  await edit('Projects');await page.getByRole('button',{name:'Add another project',exact:true}).click();await page.getByLabel('Project name *',{exact:true}).fill('Synthetic API');await page.getByLabel('Your personal contribution',{exact:true}).fill('Designed the API');await page.getByLabel('Project or demo link',{exact:true}).fill('https://example.com/demo');await save();
  await edit('Skills');await page.getByLabel('Add a skill',{exact:true}).fill('Python');await page.getByRole('button',{name:'Add skill',exact:true}).click();await save();assert.deepEqual((await get()).sections.skills.items,['Python']);
  await edit('Portfolio and professional links');await page.getByLabel('Portfolio website',{exact:true}).fill('https://example.com/portfolio');await save();
  await edit('Resume link');await page.getByLabel('Resume link (HTTPS)',{exact:true}).fill('https://example.com/resume');await save();assert.equal(await page.locator('input[type=file]').count(),0);
  await edit('Professional summary');await summary().fill('Unsaved retry draft');
  const outage=route=>route.request().method()==='POST'?route.fulfill({status:503,json:{error:'synthetic outage'}}):route.continue();
  await page.route('**/api/workspace/candidate/profile',outage);await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await summary().inputValue(),'Unsaved retry draft');assert.equal(await page.getByText('Profile saved.',{exact:true}).count(),0);
  await page.unroute('**/api/workspace/candidate/profile',outage);await save();assert.equal((await get()).sections.summary.summary,'Unsaved retry draft');
  await edit('Professional summary');await summary().fill('Local conflicting draft');const snapshot=await get();const external=await context.request.post(origin+endpoint,{headers,data:{version:snapshot.version,section:'summary',value:{summary:'Other session value'}}});assert.equal(external.status(),200);
  await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await summary().inputValue(),'Local conflicting draft');assert.equal(await page.getByRole('button',{name:'Save profile',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Review latest saved section',exact:true}).click();await page.getByRole('button',{name:'Use latest saved section',exact:true}).click();assert.equal(await summary().inputValue(),'Other session value');await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.reload();await page.getByText('Other session value',{exact:true}).waitFor();assert.equal(await page.locator('.cp-legacy p').textContent(),legacy);
  await edit('Projects');await page.getByRole('button',{name:'Remove entry 1',exact:true}).click();await save();assert.equal((await get()).sections.projects.items.length,0);
  for(const width of [390,320]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Profile fits '+width);}
  await edit('Personal details');await page.getByLabel('Current city',{exact:true}).fill('Discard me');await page.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal((await get()).sections.personal.city,'Delhi');
  await context.request.post(origin+'/api/logout',{headers,data:{}});await open();await page.getByRole('heading',{name:'Candidate access required',exact:true}).waitFor();
  console.log('::notice title=Candidate Profile acceptance::PASS: real local WSGI/SQLite section saves/readback, education legacy preservation, repeatable entries/removal, fresher flag, skill tags, links/resume-link only, read-only email, draft retention/retry, cross-session conflict resolution, cancel, 390/320px fit and signed-out denial. Synthetic accounts; no live providers.');
 }finally{await context.close();}
}
