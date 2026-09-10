// Test/build diagnostics contain only synthetic fixture data, never runtime secrets.
function report(error){const message=String(error?.stack||error).replaceAll('%','%25').replaceAll('\r','%0D').replaceAll('\n','%0A');console.error('::error title=Frontend acceptance failed::'+message);process.exit(1);}
process.on('uncaughtException',report);process.on('unhandledRejection',report);
