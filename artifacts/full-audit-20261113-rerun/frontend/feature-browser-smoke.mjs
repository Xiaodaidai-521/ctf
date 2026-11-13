import fs from 'node:fs';
import assert from 'node:assert/strict';
import { chromium } from 'file:///C:/Users/29681/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
const evidence = {mode:'real Chrome and Vite with synthetic intercepted API; no live API/database or permissions verified',workflows:[],pageErrors:[]};
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const config={title:'合成配置',issue_group_ids:['group-source'],baseline_config_version:'base-source',candidate_config_version:'candidate-source',single_changed_factor:'source-limit',rollback_version:'base-source',baseline_config:{'source-limit':10},candidate_config:{'source-limit':12},target_task_versions:['task-source@1'],excluded_scope:['排除范围'],expected_risk:'原始风险'};
const report={run_id:'run-source',report_id:'report-source',report_version:'source-v1',report_digest:'report-source-digest',candidate_config_digest:'candidate-source-digest',recommendation:'fail',completed:false,missing_cases:3};
const ticket=i=>({feedback_id:'ticket-'+i,student_id:7,student_name:'合成学生',task_title:'合成练习'+i,category:'teaching',issue_type:'scoring_dispute',status:'pending_fact_review',created_at:'2026-11-13T01:00:00Z',waiting_days:1,impact_level:'high',novelty:'new',conflict_flag:true,version:1,evidence:[],referrals:[],missing_evidence:[]});
const all=Array.from({length:205},(_,i)=>ticket(i+1));
let resourceRejected=false,publicReads=0;
try {
for(const role of ['teacher','admin']){
 const user={id:role==='teacher'?18:19,role,username:'Synthetic_'+role},context=await browser.newContext({viewport:{width:1365,height:900}}),calls=[];
 await context.addInitScript(user=>localStorage.setItem('userInfo',JSON.stringify(user)),user);
 const page=await context.newPage();page.on('pageerror',err=>evidence.pageErrors.push({role,error:err.message}));
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),key=url.pathname,method=request.method(),body=request.postData();if(!key.startsWith('/api/'))return route.continue();calls.push({method,path:key,query:Object.fromEntries(url.searchParams),body:body?JSON.parse(body):null});
  let status=503,payload={error:'合成服务未提供此项'};
  if(key==='/api/users/profile/'){status=200;payload=user;}
  else if(key==='/api/users/csrf/'){status=200;payload={};}
  else if(key==='/api/ai/list/'){status=200;payload=[];}
  else if(key==='/api/feedback/options/'){status=200;payload={statuses:[{value:'pending_fact_review',label:'待核查'}],categories:[{value:'teaching',label:'教学反馈'}],destinations:[{value:'module6',label:'核验'}]};}
  else if(key==='/api/feedback/teacher/queue/'){status=200;const size=Number(url.searchParams.get('page_size')||50),p=Number(url.searchParams.get('page')||1);payload={items:all.slice((p-1)*size,p*size),total:205,page:p,page_size:size,counts:{pending_fact_review:205}};}
  else if(key==='/api/feedback/teacher/sampling-batches/'){status=200;payload={items:[]};}
  else if(key.startsWith('/api/feedback/teacher/ticket-')&&key.endsWith('/')){status=200;payload=ticket(key.split('/')[4].split('-')[1]);}
  else if(key==='/api/feedback/teacher/phase3/issue-groups/'){status=200;payload={items:[{group_id:'group-source',title:'合成问题组',status:'confirmed',counts:{},category:'teaching',issue_type:'scoring_dispute'}],phase3_write_enabled:true,release_enabled:false};}
  else if(key==='/api/feedback/teacher/phase3/candidates/'){status=200;payload=method==='POST'?{candidate_id:'new-synthetic'}:{items:[{candidate_id:'candidate-source',title:'合成待评测候选',state:'pending_eval',state_label:'待评测',baseline_config_version:'v1',candidate_config_version:'v2',single_changed_factor:'source-limit',target_task_versions:[]}]};}
  else if(key==='/api/feedback/teacher/phase3/candidates/candidate-source/report/'){status=409;payload={code:'report_not_completed'};}
  else if(key==='/api/feedback/teacher/reconciliation/'){status=200;payload={items:[],counts:{linked:0},scanned:0};}
  else if(key==='/api/challenges/categories/'){status=200;payload={results:[{id:3,name:'合成分类'}],count:1,next:null};}
  else if(key==='/api/challenges/challenges/'){status=200;payload={results:[{id:42,title:'合成题目',category:3,category_name:'合成分类',difficulty:'easy',score:10,is_active:false,solve_count:0}],count:1,next:null};}
  else if(key==='/api/challenges/challenge/42/'){status=200;payload={id:42,title:'合成题目',category:3,difficulty:'easy',score:10,is_active:false,description:'合成题面',hint:'原提示'};}
  else if(key==='/api/challenges/challenges/42/'){status=200;payload={id:42,title:'合成题目'};}
  else if(key==='/api/resources/'){publicReads++;status=publicReads===1?503:200;payload=publicReads===1?{error:'合成读取失败'}:{results:[],count:0,next:null};}
  else if(key==='/api/resources/admin/'){status=200;const pending=!resourceRejected&&(!url.searchParams.get('status')||url.searchParams.get('status')==='pending');payload={results:pending?[{id:8,title:'合成讲义',description:'合成说明',resource_type:'document',status:'pending',category:'合成分类',file_size:1024,created_at:'2026-11-13T01:00:00Z',uploader_info:{username:'合成上传者'}}]:[],count:pending?1:0,next:null};}
  else if(key==='/api/resources/review/'){status=200;resourceRejected=true;payload={id:8,status:'rejected'};}
  else if(key.startsWith('/api/skill-review/teacher/')){status=200;payload=key.endsWith('/queue/')?{counts:{}}:key.includes('/sampling/items/')?{items:[]}:key.endsWith('/stats/')||key.endsWith('/regression-cases/')?{}:{items:[]};}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(payload)});
 });
 if(role==='teacher'){
  await page.goto('http://127.0.0.1:5173/teacher/feedback?status=pending_fact_review#sampling',{waitUntil:'networkidle'});
  assert.equal(await page.locator('#feedback-sampling').evaluate(el=>el.open),true);
  await page.getByRole('button',{name:'读取高风险选择',exact:true}).click();await page.getByRole('button',{name:'刷新高风险选择',exact:true}).waitFor();
  assert.equal(await page.locator('#feedback-sampling select[multiple] option').count(),205);
  const reads=calls.filter(c=>c.path==='/api/feedback/teacher/queue/'&&c.query.page_size==='100');assert.deepEqual(reads.map(c=>c.query.page),['1','2','3']);assert.ok(reads.every(c=>!c.query.status&&!c.query.category&&!c.query.owner));
  evidence.workflows.push({name:'sampling-anchor-and-all-205-risk-choices',success:true,pages:reads.map(c=>c.query.page)});
  await page.getByRole('link',{name:'问题组与候选',exact:true}).click();await page.locator('#candidates details').waitFor();
  await page.locator('input[type=file]').first().setInputFiles({name:'source-config.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(config))});
  await page.getByRole('button',{name:'登记草稿',exact:true}).click();await page.getByText('候选草稿已登记。',{exact:true}).waitFor();
  assert.deepEqual(calls.find(c=>c.method==='POST'&&c.path==='/api/feedback/teacher/phase3/candidates/').body,config);
  const reportFile=page.getByText('导入真实评测报告引用',{exact:false}).locator('input');
  await reportFile.setInputFiles({name:'source-report.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(report))});
  await page.getByRole('button',{name:'登记报告',exact:true}).click();
  await page.waitForTimeout(250);
  assert.deepEqual(calls.find(c=>c.path.endsWith('/candidate-source/report/')&&c.method==='POST').body,report);
  evidence.workflows.push({name:'candidate-real-file-payloads-and-incomplete-report-retained',success:true,configuration:config,report});
  await page.screenshot({path:'candidate-workbench.png',fullPage:true});
  await page.goto('http://127.0.0.1:5173/teacher/feedback/ticket-1',{waitUntil:'networkidle'});
  await page.getByRole('heading',{name:/合成练习1/}).waitFor();assert.equal(await page.getByText('ticket-1',{exact:true}).count(),0);
  evidence.workflows.push({name:'feedback-readable-detail-no-visible-reference-id',success:true});
 }
 if(role==='admin'){
  await page.goto('http://127.0.0.1:5173/admin/challenges',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'编辑',exact:true}).click();await page.locator('input[type=password]').waitFor();assert.equal(await page.locator('input[type=password]').getAttribute('required'),null);
  await page.getByRole('button',{name:'保存',exact:true}).click();await page.getByText('题目内容已保存，请另行核对答案是否生效。',{exact:true}).waitFor();
  const edit=calls.find(c=>c.method==='PUT'&&c.path==='/api/challenges/challenges/42/');assert.ok(edit);assert.equal(Object.hasOwn(edit.body,'flag'),false);
  evidence.workflows.push({name:'admin-edit-omits-empty-flag-and-preserves-all-other-fields',success:true,payload:edit.body});
  await page.goto('http://127.0.0.1:5173/admin/resources',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'拒绝',exact:true}).click();await page.getByRole('textbox',{name:'拒绝原因（必填）'}).fill('合成审核：缺少来源');
  await page.getByRole('button',{name:'确认',exact:true}).click();await page.getByText('审核已完成。',{exact:true}).waitFor();
  assert.deepEqual(calls.find(c=>c.method==='POST'&&c.path==='/api/resources/review/').body,{resource_id:8,status:'rejected',review_comment:'合成审核：缺少来源'});
  evidence.workflows.push({name:'admin-resource-review-uses-real-dialog-props-and-exact-reason',success:true});
  await page.goto('http://127.0.0.1:5173/resources',{waitUntil:'networkidle'});await page.getByText('资源列表读取失败，请重试。',{exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'暂无资源',exact:true}).count(),0);await page.getByRole('button',{name:'重试读取资源',exact:true}).click();await page.getByRole('heading',{name:'暂无资源',exact:true}).waitFor();evidence.workflows.push({name:'public-resource-failure-and-retry-show-distinct-states',success:true});
 }
 await context.close();
}
assert.deepEqual(evidence.pageErrors,[]);
} catch(error){evidence.error=error.stack;throw error;} finally{fs.writeFileSync('feature-browser-smoke.json',JSON.stringify(evidence,null,2));await browser.close();}
console.log(JSON.stringify(evidence,null,2));