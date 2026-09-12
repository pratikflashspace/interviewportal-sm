// Serialize writes per question, retaining the server revision across edits.
// Pure dependency-injected client so race handling can be tested without a mic.
export class DraftClient {
 constructor(call){this.call=call;this.current=null;this.chain=Promise.resolve();this.generation=0;}
 async load(application,question){
  const token=++this.generation;
  const result=await this.call(`/v2/applications/${application}/draft`);
  if(token!==this.generation||result.question_id!==question)return null;
  this.current={application,question,revision:result.revision,text:result.transcript};
  return result;
 }
 save(application,question,text){
  const token=this.generation;
  const run=async()=>{
   const state=this.current;
   if(token!==this.generation||!state||state.application!==application||state.question!==question)return null;
   if(text===state.text)return {revision:state.revision,transcript:state.text};
   const result=await this.call(`/v2/applications/${application}/draft`,{question_id:question,revision:state.revision,transcript:text});
   if(token===this.generation){state.revision=result.revision;state.text=result.transcript;}
   return result;
  };
  const promise=this.chain.then(run);
  this.chain=promise.catch(()=>{});
  return promise;
 }
 invalidate(){this.generation++;this.current=null;}
}
