// Synthetic frontend acceptance diagnostics only; not runtime request logging.
function report(error){const text=String(error?.message||error)+'\n'+String(error?.stack||'');const message=text.replaceAll('%','%25').replaceAll('\r','%0D').replaceAll('\n','%0A');console.error('::error title=Frontend acceptance failed::'+message);process.exit(1);}
process.on('uncaughtException',report);process.on('unhandledRejection',report);
