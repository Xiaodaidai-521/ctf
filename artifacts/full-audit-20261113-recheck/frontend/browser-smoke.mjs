import fs from 'node:fs';
import { chromium } from 'file:///C:/Users/29681/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const evidence={mode:'synthetic API mocks; no live service or data changed',routes:[],workflows:[]};
const modules=[{id:12,title:'审计测试章节',description:'合成章节说明',module_type:'theory',content:'## 合成内容\n\n验证教材渲染与真实状态按钮。',estimated_minutes:20,is_required:true,requires:[],labs:[],order:1}];
const path={id:7,title:'审计测试航线',description:'合成航线说明',difficulty:'AP',estimated_hours:2,total_modules:1,total_labs:0,enrollment_count:0,color:'#B7352D',is_published:true,modules};
for(const [role,paths] of Object.entries({guest:['/privacy','/login','/register','/challenges','/resources','/community','/missing-audit-route'],student:['/guide','/dashboard','/learning-paths/7','/learning-paths/7/modules/12','/exam-center','/exam-taking/12','/profile'],teacher:['/teacher','/teacher/learning-paths','/teacher/learning-paths/new','/teacher/materials'],admin:['/admin/dashboard','/admin/data-security','/learning-paths/manage','/learning-paths/new','/learning-paths/7/edit','/admin/categories']})) {
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const user={id:role==='admin'?19:role==='teacher'?18:17,role,username:'Audit_'+role,nickname:'合成测试用户'};
 await context.addInitScript(({role,user})=>{if(role!=='guest')localStorage.setItem('userInfo',JSON.stringify(user));},{role,user});
 const page=await context.newPage(); let errors=[]; const calls=[]; let joined=false;
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/**', async route=>{
  const request=route.request(),url=new URL(request.url()),key=url.pathname,method=request.method();
  if(!key.startsWith('/api/')) return route.continue();
  calls.push({method,path:key});
  let payload={error:'审计模拟服务暂不可用'},status=503;
  if(key==='/api/users/profile/'){status=200;payload=user;}
  else if(key==='/api/users/csrf/'){status=200;payload={};}
  else if(key==='/api/ai/list/'){status=200;payload=[];}
  else if(key==='/api/learning-paths/paths/7/'){status=200;payload=path;}
  else if(key==='/api/learning-paths/paths/'){status=200;payload={results:[path],count:1,next:null,previous:null};}
  else if(key==='/api/learning-paths/modules/'){status=200;payload={results:modules,count:1,next:null,previous:null};}
  else if(key==='/api/learning-paths/modules/12/'){status=200;payload=modules[0];}
  else if(key==='/api/learning-paths/paths/7/progress/'){status=joined?200:404;payload=joined?{learning_path:7,current_module:12,completed_modules:0,total_modules:1,progress_percentage:0}:{error:'尚未开始学习此路径'};}
  else if(key==='/api/learning-paths/paths/7/start/'){joined=true;status=200;payload={learning_path:7,current_module:12,completed_modules:0,total_modules:1,progress_percentage:0};}
  else if(key==='/api/learning-paths/modules/12/start/'){status=200;payload={id:1,module:12,status:'IN_PROGRESS',started_at:'2026-11-13T01:00:00Z'};}
  else if(key==='/api/learning-paths/modules/12/complete/'){status=200;payload={id:1,module:12,status:'COMPLETED',started_at:'2026-11-13T01:00:00Z',completed_at:'2026-11-13T01:30:00Z'};}
  else if(key==='/api/learning-paths/progress/'){status=200;payload={results:[{id:93,learning_path:7,path_title:path.title,progress_percentage:35,completed_modules:0,total_modules:1,completed_labs:0,total_labs:0}],count:1};}
  else if(key==='/api/submissions/my/'){status=200;payload={results:[{id:8,challenge_title:'合成提交记录',category_name:'合成分类',created_at:'2026-11-13T01:00:00Z',is_correct:true,flag:'[REDACTED]'}],count:1};}
  else if(key==='/api/challenges/challenges/my_solved/'){status=200;payload={results:[{id:42,title:'合成已解题目',score:10}],count:1};}
  else if(key==='/api/exams/records/12/result/'){status=200;payload={id:12,status:'in_progress',theory_exam:6,exam_title:'合成考试',start_time:new Date(Date.now()-120000).toISOString(),answers:[]};}
  else if(key==='/api/exams/theory-exams/6/'){status=200;payload={id:6,duration:30};}
  else if(key==='/api/exams/theory-exams/6/questions/'){status=200;payload=[{id:19,question:91,points:10,question_detail:{question_type:'single_choice',question_text:'单选题',options:['选项一','选项二']}},{id:5,question:22,points:10,question_detail:{question_type:'multiple_choice',question_text:'多选题',options:['甲','乙','丙']}}];}
  else if(key==='/api/exams/records/12/answer/'||key==='/api/exams/records/12/submit/'){status=200;payload={is_correct:true,points_earned:10};}
  else if(key==='/api/challenges/categories/'){status=200;payload={results:[{id:1,name:'合成分类',description:'只读列表',challenge_count:0}],count:1,next:null};}
  else if(key==='/api/challenges/challenges/'||key==='/api/resources/'||key==='/api/articles/articles/'||key==='/api/articles/categories/'){status=200;payload={results:[],count:0,next:null,previous:null};}
  else if(key==='/api/data-security/policies/'){status=200;payload={policy:{version:'audit-v1',status:'approved',content_hash:'synthetic',rules:[],effective_at:'2026-11-13',expires_at:'2026-12-13'},keys:[],reveal_state:'disabled'};}
  else if(key==='/api/data-security/preview/'){status=200;payload={policy_version:'audit-v1',output:'合成遮蔽结果'};}
  else if(key==='/api/data-security/reveal-requests/'){status=200;payload={items:[],offset:0,limit:20,state:'disabled'};}
  else if(key==='/api/data-security/stats/'){status=200;payload={observed_at:'2026-11-13T01:00:00Z',state:'enabled-unverified',items:[],capabilities:[],unknown_sources:[],unknown_records:0,offset:0,limit:20,next_offset:null};}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(payload)});
 });
 for(const target of paths){
  errors=[];const firstCall=calls.length;
  await page.goto('http://127.0.0.1:5176'+target,{waitUntil:'networkidle'});
  const content=await page.locator('body').innerText();
  const entry={role,target,landed:new URL(page.url()).pathname,errors:[...errors],contentLength:content.length,head:content.slice(0,180),apiCalls:calls.slice(firstCall)};
  evidence.routes.push(entry);
  fs.writeFileSync('frontend-browser-smoke.json',JSON.stringify(evidence,null,2));
  console.log(JSON.stringify({role,target,errors,contentLength:content.length}));
  if(errors.length) continue;
  if(role==='student'&&target==='/learning-paths/7'){
   await page.getByRole('button',{name:'加入学习航线',exact:true}).click();
   await page.getByRole('button',{name:'确认，进入本章',exact:true}).waitFor();
   evidence.workflows.push({name:'path-join',success:await page.getByText('已加入这条航线').count()>0,write:calls.find(c=>c.path.endsWith('/paths/7/start/'))});
  }
  if(role==='student'&&target.endsWith('/modules/12')){
   await page.getByRole('button',{name:'开始学习',exact:true}).click();
   await page.getByText('进行中 · 开始').waitFor();
   await page.getByRole('button',{name:'标记完成',exact:true}).click();
   await page.getByText('已记录本章节完成').waitFor();
   await page.getByPlaceholder('记录你的理解与待验证的问题…').fill('合成笔记验证');
   await page.getByRole('button',{name:'保存到本机',exact:true}).click();
   evidence.workflows.push({name:'module-start-complete-local-note',success:await page.getByText('笔记已保存到本机浏览器').count()>0,writes:calls.filter(c=>c.method==='POST'&&c.path.includes('/modules/12/'))});
   await page.screenshot({path:'frontend-module-desktop.png',fullPage:true});
   await page.setViewportSize({width:390,height:844});await page.screenshot({path:'frontend-module-mobile.png',fullPage:true});
   await page.setViewportSize({width:1440,height:1000});
  }
  if(role==='admin'&&target==='/admin/data-security'){
   await page.getByRole('button',{name:'预览保护结果',exact:true}).click();await page.getByText('合成遮蔽结果').waitFor();
   evidence.workflows.push({name:'admin-protection-preview',success:true,write:calls.find(c=>c.path==='/api/data-security/preview/')});
   await page.screenshot({path:'frontend-protection-desktop.png',fullPage:true});
  }
  if(role==='student'&&target==='/exam-taking/12'){
   await page.getByText('选项一',{exact:true}).click();
   await page.getByRole('button',{name:/下一题/}).click();
   await page.getByText('甲',{exact:true}).click();await page.getByText('乙',{exact:true}).click();
   const selected=await page.locator('.option-item.selected').count();
   await page.getByRole('button',{name:'提交考试',exact:true}).first().click();await page.getByRole('button',{name:'确认提交',exact:true}).waitFor();
   evidence.workflows.push({name:'theory-single-multiple-and-save',success:selected===2,writes:calls.filter(c=>c.path==='/api/exams/records/12/answer/')});
   await page.screenshot({path:'frontend-exam-desktop.png',fullPage:true});
   await page.getByRole('button',{name:'取消',exact:true}).click();
  }
  if(role==='student'&&target==='/profile'){
   await page.locator('.menu-item').filter({hasText:'提交记录'}).click();
   await page.getByText('合成提交记录',{exact:true}).waitFor();
   await page.locator('.menu-item').filter({hasText:'学习进度'}).click();
   await page.getByRole('button',{name:'继续学习',exact:true}).click();
   await page.waitForURL('**/learning-paths/7');
   await page.goto('http://127.0.0.1:5176/profile',{waitUntil:'networkidle'});
   await page.locator('.menu-item').filter({hasText:'完成题目'}).click();
   await page.getByText('合成已解题目',{exact:true}).click();
   await page.waitForURL('**/challenge/42');
   evidence.workflows.push({name:'profile-paginated-submissions-and-original-destinations',success:true,pathId:7,progressRecordId:93,challengeId:42});
  }
 }
 await context.close();
}
await browser.close();
fs.writeFileSync('frontend-browser-smoke.json',JSON.stringify(evidence,null,2));
console.log(JSON.stringify({routes:evidence.routes.length,pageErrors:evidence.routes.filter(r=>r.errors.length).map(r=>({role:r.role,path:r.target,errors:r.errors})),workflows:evidence.workflows},null,2));
