// Run the installed cmux reactive runtime; intercept all external actions.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const nodes=new Map(),actions=[];
let root;
const ctx=vm.createContext({
  __host_applyOps:json=>{for(const o of JSON.parse(json)){
    if(o.op==='create') nodes.set(o.id,{...o,props:{},children:[]});
    if(o.op==='update') nodes.get(o.id).props[o.key]=o.value;
    if(o.op==='children') nodes.get(o.id).children=o.children;
    if(o.op==='append') nodes.get(o.id).children.push(o.child);
    if(o.op==='remove') nodes.delete(o.id);
    if(o.op==='root') root=o.id;
  }},
  __host_action:json=>actions.push(JSON.parse(json)),__host_log:()=>{},
});
vm.runInContext(fs.readFileSync(process.env.CMUX_SIDEBAR_RUNTIME || '/Applications/cmux.app/Contents/Resources/CmuxSwiftRenderUI_CmuxSwiftRenderUI.bundle/Contents/Resources/SidebarRuntime.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../sidebars/workspaces.js'),'utf8'),ctx);
const row={key:'tmux-test',name:'test-session',note:'常驻服务说明',project:'test',port:'1234',lifecycle:'常驻',protected:true,windows:'2',attached:'0',close_url:'test://close',confirm_url:'test://confirm'};
const workspace={id:'ws',title:'test-workspace',index:0,selected:true,color:'#FFCC66',agents:[]};
const usage={id:'meter',title:'cx7d |37% (2d)|',index:1,description:''};
function publish(note=row.note) {
  usage.description='sentinel-updated:1000\nsentinel-tmux:'+JSON.stringify({sessions:[{...row,note}],pending:null});
  ctx.__setData('workspaces',JSON.stringify([workspace,usage]));
}
ctx.__setData('clock',JSON.stringify({epoch:1001}));
publish();
function tree(id=root,result=[]) {const n=nodes.get(id);if(n){result.push(n);for(const c of n.children)tree(c,result);}return result;}
function has(text){return tree().some(n=>n.type==='text' && n.props.text===text);}
function contains(n,text){return tree(n.id,[]).some(child=>child.type==='text' && child.props.text===text);}
function tap(text) {
  const target=tree().find(n=>(n.props.tappable || n.type==='button') && contains(n,text));
  assert(target,'missing tap target '+text);
  const start=performance.now();ctx.__dispatch(target.id,'tap','{}');return performance.now()-start;
}
assert(!has('备注'));
const elapsed=tap('test-session');
assert(has('常驻服务说明'));
assert.equal(actions.length,0,'expand must not invoke host commands');
publish('更新后的常驻服务说明');
assert(has('更新后的常驻服务说明'),'live metadata must preserve expansion');
tap('× 关闭会话');
assert(has('确认关闭这个常驻会话？'));
assert.equal(actions.length,0,'confirmation prompt must be local');
tap('取消');
assert(!has('确认关闭这个常驻会话？'));
assert.equal(actions.length,0,'cancel must be local');
tap('× 关闭会话');tap('确认关闭');
assert.deepEqual(actions,[{kind:'openURL',url:'test://confirm'}]);
tap('test-session');assert(!has('备注'));
assert.equal(actions.length,1,'collapse must be local');
assert(has('Cmux') && has('37% (2d)'));
assert(tree().some(n=>n.type==='capsule' && n.props.fill==='#FFCC66' && n.props.opacity===1));
workspace.color=null;publish();
assert(tree().some(n=>n.type==='capsule' && n.props.opacity===0));
assert(tree().some(n=>n.props.background==='#33415ED9'),'selected background retained');
console.log(`PASS expand updates scene synchronously (${elapsed.toFixed(2)} ms, zero external commands)`);
console.log('PASS data refresh retains expansion; confirmation and cancel are local');
console.log('PASS only confirmed close dispatches external action; collapse is local');
console.log('PASS usage text, manual color and selected background preserved');

// Module controls use the same retained scene; only preference persistence is external.
const labels=['USAGE','WORKSPACES','TMUX'];
const headers=()=>tree().filter(n=>n.props.tappable && labels.some(label=>contains(n,label)));
const order=()=>headers().map(n=>labels.find(label=>contains(n,label)));
assert.deepEqual(order(),labels);
const tmuxHeader=headers().find(n=>contains(n,'TMUX')).id;
tap('USAGE');assert(!has('37% (2d)'));assert(has('test-workspace'));
tap('WORKSPACES');assert(!has('test-workspace'));assert(has('test-session'));
tap('TMUX');assert(!has('test-session'));
const topButton=tree(tmuxHeader,[]).find(n=>n.type==='button' && n.props.text==='置顶');
assert(topButton);
ctx.__dispatch(topButton.id,'tap','{}');
assert.deepEqual(order(),['TMUX','USAGE','WORKSPACES']);
assert.equal(headers().find(n=>contains(n,'TMUX')).id,tmuxHeader,'moving sections must preserve identity');
publish();assert(!has('test-session'),'data refresh must preserve module collapse');
tap('TMUX');assert(has('test-session'));assert(!has('test-workspace'));
const last=actions.at(-1);
assert.equal(last.kind,'openURL');
assert(last.url.startsWith('cmux-sentinel://layout/'));
const saved=JSON.parse(decodeURIComponent(last.url.split('/').at(-1)));
assert.deepEqual(saved.order,['tmux','usage','workspaces']);
assert.equal(saved.collapsed.tmux,false);
assert.equal(saved.collapsed.workspaces,true);
assert(actions.slice(1).every(a=>a.kind==='openURL' && a.url.startsWith('cmux-sentinel://layout/')),
  'module actions must not select/close/reorder a workspace or tmux session');
// Simulate loading saved preferences after the local override is gone.
usage.description='sentinel-updated:1000\nsentinel-tmux:'+JSON.stringify({sessions:[row],pending:null,layout:saved});
ctx.__setData('workspaces',JSON.stringify([workspace,usage]));
vm.runInContext('setLayoutOverride(null)',ctx);
assert.deepEqual(order(),['TMUX','USAGE','WORKSPACES']);
assert(!has('test-workspace') && has('test-session'));
console.log('PASS independent module collapse, context-menu ordering, retained identity and saved layout restore');

// Previously saved four-section layouts must lose the retired section and its controls.
usage.description='sentinel-tmux:'+JSON.stringify({sessions:[row],layout:{
  order:['terminal','tmux','usage','workspaces'],collapsed:{terminal:false,usage:true},revision:saved.revision+1},
  console:{output:'retired output',urls:{run:'test://console/run'}}});
ctx.__setData('workspaces',JSON.stringify([workspace,usage]));
assert.deepEqual(order(),['TMUX','USAGE','WORKSPACES']);
assert(!has('SHELL') && !has('retired output'));
assert(!tree().some(n=>n.type==='textfield'));
tap('USAGE');
const migrated=JSON.parse(decodeURIComponent(actions.at(-1).url.split('/').at(-1)));
assert.deepEqual(migrated.order,['tmux','usage','workspaces']);
assert(!Object.hasOwn(migrated.collapsed,'terminal'));
console.log('PASS old layouts drop retired console, input and preferences');

// No provider workspace is required for tmux metadata transport.
workspace.description=usage.description;
ctx.__setData('workspaces',JSON.stringify([workspace]));
assert(has('test-session'),'ordinary workspace remains a valid metadata carrier');
console.log('PASS tmux remains available without Codex/Grok workspaces');

// Live quota arrival/removal exercises the real keyed scene and module count.
vm.runInContext('setLayoutOverride({order:["usage","workspaces","tmux"],collapsed:{}})',ctx);
const goRows=['go1m','go5h','go7d'].map((label,index)=>({id:label,title:label+' |'+(index*10)+'%|',index:index+1}));
ctx.__setData('workspaces',JSON.stringify([workspace,...goRows]));
assert(has('OPENCODE GO · USED') && has('month') && has('0%'));
const goSection=tree().find(n=>n.type==='vstack' && contains(n,'OPENCODE GO · USED') && !contains(n,'USAGE'));
assert(goSection);
assert.deepEqual(tree(goSection.id,[]).filter(n=>n.type==='text' && ['session','week','month'].includes(n.props.text)).map(n=>n.props.text),['session','week','month']);
assert(!tree().some(n=>n.type==='text' && /^go(5h|7d|1m) /.test(n.props.text)));
ctx.__setData('workspaces',JSON.stringify([workspace]));
assert(!has('OPENCODE GO · USED'));
console.log('PASS Go three-window rendering, ordering, workspace filtering and removal');

// A long credential error must not squeeze the period into a vertical stack.
ctx.__setData('workspaces',JSON.stringify([workspace,{id:'grok',title:'grokcredits |⚠ login missing; run grok login|'}]));
assert(has('week') && has('⚠ sign in'));
const period=tree().find(n=>n.type==='text' && n.props.text==='week');
assert.equal(period.props.lineLimit,1);
const periodColumn=tree().find(n=>n.type==='hstack' && n.props.width===56 && contains(n,'week'));
assert(periodColumn && nodes.get(periodColumn.children.at(-1)).type==='spacer');
const error=tree().find(n=>n.type==='text' && n.props.text==='⚠ sign in');
assert.equal(error.props.lineLimit,1);
assert.equal(error.props.help,'⚠ login missing; run grok login');
ctx.__setData('workspaces',JSON.stringify([workspace,{id:'grok',title:'grokcredits |82% (1d 20h)|'}]));
assert(has('82% (1d 20h)') && !has('⚠ sign in'));
console.log('PASS long usage error has a fixed single-line period, concise status and full tooltip; recovery replaces it');

// The port chip is the tmux row's only link out: it must hit loopback and nothing else.
vm.runInContext('setLayoutOverride({order:["tmux","usage","workspaces"],collapsed:{}})',ctx);
usage.description='\nsentinel-tmux:'+JSON.stringify({sessions:[{...row,key:'ports',name:'ports-session',port:'30141, 3300；30141, 说明文本'}],pending:null});
ctx.__setData('workspaces',JSON.stringify([workspace,usage]));
tap('ports-session');
assert(has('端口') && has('30141') && has('3300'));
assert(!has('说明文本'),'non-numeric @port text never becomes a chip');
tap('30141');
assert.deepEqual(actions.at(-1),{kind:'openURL',url:'http://127.0.0.1:30141'},'port chip opens the endpoint in the default browser');
tap('3300');
assert.deepEqual(actions.at(-1),{kind:'openURL',url:'http://127.0.0.1:3300'},'every listed port is reachable as its own chip');
usage.description='\nsentinel-tmux:'+JSON.stringify({sessions:[{...row,key:'noport',name:'no-port-session',port:''}],pending:null});
ctx.__setData('workspaces',JSON.stringify([workspace,usage]));
tap('no-port-session');
assert(has('端口 无标注'));
assert(!tree().some(n=>(n.type==='button') && contains(n,'127.0.0.1')),'no port means no link');
console.log('PASS port chips open loopback only, split multiple @port values and stay absent without one');

const claudeRows=[{id:'claude-week',title:'7d |4% (2d)|'}, {id:'claude-session',title:'5h |2% (4h)|'}, {id:'claude-spend',title:'spend |none|'}];
ctx.__setData('workspaces',JSON.stringify([workspace,...claudeRows]));
assert(has('CLAUDE CODE · USED') && has('2% (4h)') && has('4% (2d)'));
const claudeSection=tree().find(n=>n.type==='vstack' && contains(n,'CLAUDE CODE · USED') && !contains(n,'USAGE'));
assert.deepEqual(tree(claudeSection.id,[]).filter(n=>n.type==='text' && ['session','week'].includes(n.props.text)).map(n=>n.props.text),['session','week']);
assert(!has('none') && !has('extra'));
ctx.__setData('workspaces',JSON.stringify([workspace]));
assert(!has('CLAUDE CODE · USED'));
console.log('PASS Claude live section, period order, hidden zero spend and removal');
