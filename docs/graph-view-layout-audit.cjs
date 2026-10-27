const { chromium } = require('/workspace/frontend/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const out = '/workspace/docs/evidence/graph-layout-audit-2026-10-27';
fs.mkdirSync(out, {recursive:true});
const doc = {id:1,name:'Architektur und Integrationshandbuch',url:'https://audit.invalid/architecture',source_id:2};
const project = {id:1,name:'Graph-Layout-Prüfung',status:'completed',repo_id:1};
const nodes = [
 {id:'doc:1',type:'document',label:doc.name,url:doc.url,source_type:'confluence',source_id:2},
 {id:'entity:1',type:'entity',label:'ContentRepositoryEndpoint',entity_type:'class',file_path:'src/ContentRepositoryEndpoint.java',source_id:1},
 {id:'file:1',type:'code_file',label:'ContentRepositoryEndpoint.java',file_path:'src/ContentRepositoryEndpoint.java',source_id:1,entity_ids:[1]},
 {id:'entity:2',type:'entity',label:'Buchung verarbeiten',entity_type:'program',file_path:'src/BOOKING.cbl',source_id:1},
 {id:'doc:2',type:'document',label:'Integrationsleitfaden',source_type:'pdf',source_id:2},
 {id:'doc:3',type:'document',label:'Betriebshandbuch',source_type:'markdown',source_id:2},
 {id:'external:1',type:'external',label:'Kundendatenbank',source_type:'jira',source_id:2}
].map((n,i)=>({...n,project_id:1,fx:Math.cos(i)*100,fy:Math.sin(i)*100}));
const types=['semantic','keyword','documented','syntactic','coref','manual','code_dependency'];
const edges=types.map((type,i)=>({id:'edge:'+i,source:nodes[i%nodes.length].id,target:nodes[(i+1)%nodes.length].id,link_type:type,edge_type:type,direction:['directed','undirected','bidirectional'][i%3],score:.9}));
const variants=[{w:1440,h:900,n:1},{w:1440,h:900,n:2},{w:1440,h:900,n:3},{w:1440,h:900,n:4},{w:1280,h:800,n:3},{w:1280,h:800,n:4},{w:1920,h:1080,n:3},{w:1440,h:900,n:2,split:25}];
(async()=>{
 const binaryRoot=fs.readdirSync('/ms-playwright').find(p=>p.startsWith('chromium-'));
 const browser=await chromium.launch({headless:true,executablePath:`/ms-playwright/${binaryRoot}/chrome-linux/chrome`,args:['--no-sandbox']});
 const results=[];
 for(const v of variants){
  const context=await browser.newContext({viewport:{width:v.w,height:v.h}});
  const configs=['graph','chat','code','doc'].slice(0,v.n);
  const session={id:9001,uuid:'audit',title:'Layout-Prüfung',project_id:1,snapshot_json:{panelConfigs:configs,panelFrozen:configs.map(()=>false),panelSelections:configs.map((type)=>({selectedFile:null,selectedEntity:null,selectedDoc:type==='graph'?doc:null})),selectedProjectId:1,splitPercent:v.split||50}};
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.port==='3000')return route.continue();
   let body=[];
   if(u.pathname==='/auth/me')body={id:1,username:'layout-audit',is_admin:true};
   else if(u.pathname==='/projects')body=[project];
   else if(u.pathname==='/chat/sessions/page')body={sessions:[session],has_more:false,limit:30};
   else if(u.pathname.startsWith('/chat/sessions/by-uuid/'))body=session;
   else if(u.pathname==='/graph')body={nodes,edges};
   else if(u.pathname==='/graph/neighborhood')body={nodes,edges,focus_id:'doc:1',has_more:true,next_cursor:'audit-next'};
   else if(u.pathname==='/knowledge-sources')body=[{id:1,project_id:1,name:'Spring Web Services – Quellcode und Beispielanwendungen',source_type:'git',sync_status:'completed'},{id:2,project_id:1,name:'Architektur- und Integrationsdokumentation',source_type:'confluence',sync_status:'completed'}];
   else if(u.pathname==='/model-info')body={llm:'audit',embedding:'audit'};
   else if(u.pathname==='/models')body={models:[]};
   else if(u.pathname.endsWith('/stats'))body={total_files:3,total_lines:100,languages:[]};
   await route.fulfill({status:200,headers:{'Content-Type':'application/json','Access-Control-Allow-Origin':'http://127.0.0.1:3000','Access-Control-Allow-Credentials':'true','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'},body:JSON.stringify(body)});
  });
  const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:3000/');
  await page.locator('#project-selector').click();
  await page.getByRole('option',{name:project.name,exact:false}).click();
  await page.getByText('Layout-Prüfung',{exact:true}).first().click();
  await page.locator('canvas').first().waitFor({timeout:15000,state:'attached'});
  await page.waitForTimeout(900);
  const canvas=page.locator('canvas').first();
  const graph=canvas.locator('xpath=../../../..');
  const metrics=await canvas.evaluate(c=>{
   let root=c.parentElement;
   while(root && !root.firstElementChild?.classList.contains('flex-wrap'))root=root.parentElement;
   if(!root)throw new Error('graph root missing');
   const toolbar=root.firstElementChild;
   const rect=e=>{const r=e.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}};
   return {canvas:rect(c),root:rect(root),toolbar:rect(toolbar),buttons:[...root.querySelectorAll('button')].map(e=>({text:(e.textContent||'').trim(),title:e.title,...rect(e)})),overflow:[...root.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>root.getBoundingClientRect().right+2).slice(0,12).map(e=>({tag:e.tagName,text:(e.textContent||'').slice(0,80),...rect(e)}))};
  });
  const name=`${v.w}x${v.h}-${v.n}-views${v.split?'-split'+v.split:''}`;
  await page.screenshot({path:path.join(out,name+'.png')});
  if(v.n===3 || v.n===4){
   const drawer=page.locator('div.absolute.left-0.right-0.bottom-0.border-t').first();
   if(await drawer.count()){
    await drawer.locator(':scope > div').first().click();
    try {await page.getByText('Legende',{exact:true}).click({timeout:1000});}
    catch {metrics.legendBlockedByDetails=true;}
    await page.screenshot({path:path.join(out,name+'-details-legend.png')});
    metrics.expandedDrawer=await drawer.evaluate(e=>({height:Math.round(e.getBoundingClientRect().height),bodyHeight:e.lastElementChild.clientHeight,bodyScrollHeight:e.lastElementChild.scrollHeight}));
    const neighborhood=page.getByRole('button',{name:'Nur Nachbarschaft laden',exact:true});
    if(await neighborhood.count() && await neighborhood.isVisible() && v.h!==800){
     await neighborhood.click();
     await page.getByRole('button',{name:'Zurück zur Übersicht',exact:true}).waitFor({timeout:10000});
     metrics.neighborhood=await canvas.evaluate(c=>{
      let root=c.parentElement;while(root && !root.firstElementChild?.classList.contains('flex-wrap'))root=root.parentElement;
      return {canvasHeight:c.getBoundingClientRect().height,toolbarHeight:root.firstElementChild.getBoundingClientRect().height,overflowWidth:root.firstElementChild.scrollWidth-root.clientWidth};
     });
     await page.screenshot({path:path.join(out,name+'-neighborhood.png')});
    }
   }
  }
  results.push({name,...v,metrics,errors});
  fs.writeFileSync(path.join(out,'measurements.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify({name,canvas:metrics.canvas,root:metrics.root,toolbar:metrics.toolbar,overflow:metrics.overflow.length,errors}));
  await context.close();
 }
 fs.writeFileSync(path.join(out,'measurements.json'),JSON.stringify(results,null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
