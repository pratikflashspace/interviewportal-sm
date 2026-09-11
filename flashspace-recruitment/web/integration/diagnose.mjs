// Import browser runner with short sanitized Actions annotations on failure.
function safe(error){let text=String(error?.message||error).replaceAll('\n',' ').replaceAll('\r',' ');for(const [k,v] of Object.entries(process.env)){if(/TOKEN|SECRET|PASSWORD|DATABASE_URL|API_KEY/i.test(k)&&v.length>3)text=text.split(v).join('[REDACTED]');}return text.slice(0,1200).replaceAll('%','%25');}
try{await import('./run.mjs');}catch(e){console.error('::error::BROWSER_INTEGRATION_FAILURE '+safe(e));process.exitCode=1;}
