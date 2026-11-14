import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const directory=path.dirname(fileURLToPath(import.meta.url));
const log=fs.readFileSync(path.join(directory,'frontend-tests-final.log'),'utf8');
const report=log.slice(log.indexOf('✖ failing tests:'));
const failures=[...report.matchAll(/^test at (.+?):(\d+):\d+\r?\n✖ (.+)$/gm)].map(m=>({file:m[1].replaceAll('\\','/'),line:Number(m[2]),test:m[3].replace(/ \([^)]*\)$/,'')}));
const groups={};for(const f of failures){(groups[f.file]??=[]).push(f.test);}
const count=(key)=>Number(log.match(new RegExp('^ℹ '+key+' (\\d+)','m'))?.[1]??0);
const summary={tests:count('tests'),pass:count('pass'),fail:count('fail'),cancelled:count('cancelled'),skipped:count('skipped'),parsedFailures:failures.length,groups};
fs.writeFileSync(path.join(directory,'frontend-test-failures.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(Object.entries(groups).map(([file,tests])=>({file,count:tests.length})),null,2));
