// Import the browser runner with sanitized Actions annotations on failure.
function safe(error){let text=String(error?.stack||error);for(const [k,v] of Object.entries(process.env)){if(/TOKEN|SECRET|PASSWORD|DATABASE_URL|API_KEY/i.test(k)&&v.length>3)text=text.split(v).join('[REDACTED]');}return text.slice(0,3000).replaceAll('%','%25').replaceAll('\r','%0D').replaceAll('\n','%0A');}
try{await import('./run.mjs');}catch(e){console.error('::error title=Browser integration failure::'+safe(e));process.exitCode=1;}
