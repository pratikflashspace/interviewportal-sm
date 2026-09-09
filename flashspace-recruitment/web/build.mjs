import { build } from 'esbuild';
import postcss from 'postcss';
import tailwind from 'tailwindcss';
import animate from 'tailwindcss-animate';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const cwd=path.dirname(fileURLToPath(import.meta.url));process.chdir(cwd);
await fs.rm('dist',{recursive:true,force:true});await fs.mkdir('dist/assets',{recursive:true});
await build({entryPoints:['src/main.jsx'],outfile:'dist/assets/app.js',bundle:true,minify:true,format:'iife',target:['es2020'],define:{'process.env.NODE_ENV':'"production"'},alias:{'@kits/shadcn-ui':path.resolve('ui/index.jsx')},legalComments:'eof'});
const names=['background','foreground','card','card-foreground','popover','popover-foreground','primary','primary-foreground','secondary','secondary-foreground','muted','muted-foreground','accent','accent-foreground','destructive','destructive-foreground','border','input','ring'];
const colors=Object.fromEntries(names.map(n=>[n,`var(--${n})`]));
const css=await fs.readFile('dist/assets/app.css','utf8');
const tailwindConfig = {
 content:['./src/**/*.{js,jsx}','./ui/**/*.{js,jsx}'],
 theme:{extend:{colors,borderRadius:{lg:'var(--radius)',md:'calc(var(--radius) - 2px)',sm:'calc(var(--radius) - 4px)'},fontFamily:{sans:['Hind','sans-serif']}}},
 plugins:[animate]
};
const result=await postcss([tailwind(tailwindConfig)]).process(css,{from:'dist/assets/app.css'});
await fs.writeFile('dist/assets/app.css',result.css);
const assets={};for(const ext of ['js','css']){const data=await fs.readFile(`dist/assets/app.${ext}`);const hash=createHash('sha256').update(data).digest('hex').slice(0,12);assets[ext]=`app.${hash}.${ext}`;await fs.rename(`dist/assets/app.${ext}`,`dist/assets/${assets[ext]}`);}
await fs.writeFile('dist/runtime.js','window.__FLASHSPACE_LIVE__ = true;\n');
await fs.writeFile('dist/index.html',`<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Find your next role at Stirring Minds · Flashspace."><title>Flashspace Careers | Stirring Minds</title><link rel="stylesheet" href="/assets/${assets.css}"><script src="/runtime.js"></script><script defer src="/assets/${assets.js}"></script></head><body><div id="root"></div></body></html>`);
console.log('Built live frontend with hashed assets. No secrets included.');
