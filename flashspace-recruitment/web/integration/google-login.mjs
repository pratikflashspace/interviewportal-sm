// Synthetic provider boundary only; no real Google request/token/account.
import assert from 'node:assert/strict';
export async function checkGoogleLogin(browser){
 const context=await browser.newContext({viewport:{width:390,height:844}});
 try{
  const page=await context.newPage();let enabled=false,configCalls=0,sdkCalls=0,loginCalls=0;
  await page.route('**/api/auth/candidate/google/config',route=>{configCalls++;return route.fulfill({json:{enabled}});});
  await page.route('**/api/auth/candidate/google/challenge',route=>route.fulfill({json:{client_id:'synthetic.apps.googleusercontent.com',nonce:'a'.repeat(64),expires_in:300}}));
  await page.route('**/api/auth/candidate/google',route=>{loginCalls++;assert.equal(route.request().method(),'POST');assert.deepEqual(route.request().postDataJSON(),{credential:'synthetic-browser-token'});return route.fulfill({status:409,json:{error:'synthetic collision'}});});
  await page.route('https://accounts.google.com/**',route=>{
   sdkCalls++;return route.fulfill({contentType:'text/javascript',body:`window.google={accounts:{id:{initialize(options){window.syntheticGoogleOptions=options;},renderButton(target){const b=document.createElement('button');b.textContent='Synthetic Google sign in';b.onclick=()=>window.syntheticGoogleOptions.callback({credential:'synthetic-browser-token'});target.append(b);}}}};`});
  });
  // Intercept HTML only to permit the mocked SDK in the isolated test server's
  // default CSP. Production candidate-only CSP is tested separately in WSGI.
  await page.route('**/candidate/login',async route=>{const response=await route.fetch();const headers={...response.headers()};delete headers['content-security-policy'];await route.fulfill({response,headers});});
  await page.goto('http://127.0.0.1:8765/candidate/login');
  await page.getByText('Google sign-in pending configuration. Use email and password.',{exact:true}).waitFor();
  assert.equal(sdkCalls,0);assert.equal(await page.getByRole('button',{name:'Sign in',exact:true}).isEnabled(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  const before=configCalls;await page.goto('http://127.0.0.1:8765/recruiter/login');
  await page.getByRole('heading',{name:'Recruiter sign in',exact:true}).waitFor();
  assert.equal(await page.getByRole('region',{name:'Candidate Google sign-in'}).count(),0);assert.equal(configCalls,before);assert.equal(sdkCalls,0);
  enabled=true;await page.goto('http://127.0.0.1:8765/candidate/login');
  await page.getByRole('button',{name:'Synthetic Google sign in',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.syntheticGoogleOptions.nonce),'a'.repeat(64));
  assert.equal(await page.evaluate(()=>window.syntheticGoogleOptions.auto_select),false);
  await page.getByRole('button',{name:'Synthetic Google sign in',exact:true}).click();
  await page.getByText('Use email and password for this account, or sign out before trying Google. Accounts are not automatically linked.',{exact:true}).waitFor();
  assert.equal(loginCalls,1);assert.equal(await page.getByRole('button',{name:'Sign in',exact:true}).isEnabled(),true);
  assert.equal(await page.getByRole('button',{name:'Try Google again',exact:true}).isVisible(),true);
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  console.log('PASS: candidate Google disabled/configured states, recruiter exclusion, nonce, collision/manual fallback and mobile fit (mock provider only).');
 }finally{await context.close();}
}
