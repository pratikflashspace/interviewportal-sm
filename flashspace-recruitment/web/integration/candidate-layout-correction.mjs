import assert from 'node:assert/strict';
export async function checkLayoutCorrection(browser){
 const context=await browser.newContext();
 try{
  const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.route('**/api/me',r=>r.fulfill({json:{role:'candidate',admin:false,name:'Synthetic Candidate With A Long Display Name'}}));
  const app={id:'synthetic',role_title:'Synthetic role with a longer descriptive title',created_at:'2026-09-10T00:00:00Z',stage:'applied',interview_status:'interview',version:0,flow_version:2,events:[]};
  await page.route('**/api/workspace/candidate/applications',r=>r.fulfill({json:[app]}));
  await page.route('**/api/workspace/profile',r=>r.fulfill({json:{role:'candidate',fields:{},version:0}}));
  await page.route('**/api/workspace/candidate/recommendations',r=>r.fulfill({json:[]}));
  await page.route('**/api/roles',r=>r.fulfill({json:[{id:'r',title:app.role_title,department:'Engineering',location:'Remote / On-site — both available',type:'Full-time',experience:'0-2 years',description:'Synthetic role description.',details:'First line\nSecond line',skills:['Python','API integration']}]}));
  for(const route of ['dashboard','jobs','applications','interviews']){
   for(const width of [1440,390,320]){
    await page.setViewportSize({width,height:1000});await page.goto('http://127.0.0.1:8765/candidate/workspace/'+route);
    await page.locator('.cd-shell article, .cd-shell .cd-stat').first().waitFor();
    assert.equal(await page.locator('nav a[href="/candidate/workspace/resume"]:visible').count(),0);
    assert.equal(await page.getByRole('link',{name:/^Resume/}).count(),0);
    const issues=await page.evaluate(()=>{
     const h=document.querySelector('.cd-intro').getBoundingClientRect();
     const cards=[...document.querySelectorAll('main article, main .cd-stat')].map(e=>e.getBoundingClientRect());
     return {overflow:document.documentElement.scrollWidth>innerWidth,headingOverlap:cards.some(c=>c.top<h.bottom-1&&c.bottom>h.top),cardOverlap:cards.some((a,i)=>cards.some((b,j)=>j>i&&Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1))};
    });assert.deepEqual(issues,{overflow:false,headingOverlap:false,cardOverlap:false},route+' '+width);
   }
  }
  // Legacy bookmark redirects; do not instantiate the old standalone editor.
  await page.goto('http://127.0.0.1:8765/candidate/workspace/resume');
  await page.waitForURL('**/candidate/workspace/profile#cp-title-resume');
  assert.equal(await page.locator('nav a[href="/candidate/workspace/resume"]:visible').count(),0);
  console.log('::notice title=Candidate layout correction::PASS: no visible/accessibility Resume menu, old route redirects to profile, headings/cards do not overlap at 1440/390/320px on dashboard/jobs/applications/interviews. Synthetic data only.');
 }finally{await context.close();}
}
