import fs from 'node:fs';
import path from 'node:path';
import api from '../../../frontend/src/api/index.js';
function walk(dir) { return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e => e.isDirectory() ? walk(path.join(dir,e.name)) : [path.join(dir,e.name)]); }
const rows=[];
for (const file of walk('../../../frontend/src')) {
 if (!/\.(vue|js)$/.test(file)||file.endsWith('.test.js')) continue;
 const code=fs.readFileSync(file,'utf8');
 if(!/import api from ['"]@\/api(?:\/index\.js)?['"]/.test(code)) continue;
 for(const m of code.matchAll(/\bapi\.(\w+)\.(\w+)\s*\(/g)) if (typeof api[m[1]]?.[m[2]] !== 'function') rows.push({file:file.replaceAll('\\','/'),line:code.slice(0,m.index).split('\n').length,method:m[1]+'.'+m[2]});
}
fs.writeFileSync('frontend-missing-api.json',JSON.stringify(rows,null,2));
console.log(JSON.stringify(rows,null,2));
