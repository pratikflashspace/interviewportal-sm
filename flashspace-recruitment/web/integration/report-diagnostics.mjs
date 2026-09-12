// Read-only observation of synthetic CI responses; no candidate contents logged.
export function watchReports(page){
 const reads=[];
 page.on('response',async response=>{
  if(!new URL(response.url()).pathname.startsWith('/api/admin/v2/reports/'))return;
  try{const data=await response.json();reads.push({status:response.status(),reportPresent:!!data.report,scoringStatus:data.report?.scoring_status??null,sync:data.sync_status??null});if(reads.length>12)reads.shift();}
  catch{reads.push({unreadable:true});}
 });
 return ()=>JSON.stringify(reads);
}
