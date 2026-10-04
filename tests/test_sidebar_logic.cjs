// Portable business-logic checks. No renderer emulation or pixel claims.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
let rows = [], now = 2000;
const actions = [];
const ctx = vm.createContext({
  data: {workspaces:()=>rows, groups:()=>[], clock:()=>({epoch:now})},
  signal: initial => {let value=initial; return [()=>value, next=>{value=next;}];},
  sidebar: () => {}, // Do not mount UI; local runtime test owns that contract.
  openURL: url=>actions.push(url),
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../sidebars/workspaces.js'), 'utf8'), ctx);
const run = source => vm.runInContext(source, ctx);
const object = source => JSON.parse(JSON.stringify(run(source)));
rows = [{id:'task',title:'project',index:0,description:'sentinel-tmux:'+JSON.stringify({sessions:[]})}];
// Marker is newline-prefixed, including when the user description is empty.
rows[0].description = '\nsentinel-tmux:'+JSON.stringify({sessions:[{key:'build'}],layout:{order:['terminal','tmux'],collapsed:{tmux:true}}});
assert.equal(run('tmuxData().sessions[0].key'), 'build', 'ordinary workspace carries tmux without Codex');
assert.deepEqual(object('layout().order'), ['tmux','usage','workspaces']);
assert.equal(run('layout().collapsed.tmux'), true);
run('toggleSection("tmux")');
assert.equal(run('layout().collapsed.tmux'), false);
assert(actions.at(-1).startsWith('cmux-sentinel://layout/'));
rows[0].description = '\nsentinel-tmux:invalid';
assert.equal(run('tmuxData().sessions[0].key'), 'build', 'torn payload retains last good snapshot');
assert.equal(run('usageDetail({description:"sentinel-updated:1",progress:{value:0.4,label:"40%"}})'), 'stale · refresh needed');
assert.equal(run('usageDetail({description:"sentinel-updated:1999",progress:{value:0,label:"0%"}})'), '0%');
assert.deepEqual(object('sessionPorts({port:"30141"})'),[30141]);
assert.deepEqual(object('sessionPorts({port:"3300, 3301；3300"})'),[3300,3301],'several ports split; duplicates collapse to one chip');
assert.deepEqual(object('sessionPorts({port:"0 -1 99999 abc 8.5"})'),[],'only plain ports in range become links');
assert.deepEqual(object('sessionPorts({})'),[],'a session without @port has no chip');
const count=actions.length;
run('requestClose({key:"build",protected:true,close_url:"test://close"})');
assert.equal(actions.length,count);
assert.equal(run('confirming()'), 'build');
run('cancelClose()');
assert.equal(run('confirming()'), null);
run('confirmClose({key:"build",confirm_url:"test://confirmed"})');
assert.equal(actions.at(-1),'test://confirmed');
rows=Array.from({length:12},(_,i)=>({id:String(i),title:'task '+i,index:i}));
assert.equal(run('shortcut(all()[0])'),'⌘1');
assert.equal(run('shortcut(all()[8])'),'');
assert.equal(run('shortcut(all()[11])'),'⌘9');
console.log('PASS portable JS: carrier fallback, layout migration, stale data, confirmation and shortcuts');
rows=[{id:'month',title:'go1m |100%|'}, {id:'week',title:'go7d |12%|'}, {id:'session',title:'go5h |0%|'}];
assert.equal(run('sectionCount("usage")'),1);
assert.equal(run('sectionCount("workspaces")'),0,'Go meters must stay out of task rows');
assert.deepEqual(object('all().sort((a,b)=>usageOrder(a)-usageOrder(b)).map(usageWindow)'),['session','week','month']);
assert.equal(run('usageDetail({title:"go7d |12% · stale · ⚠ Go offline|",description:"sentinel-updated:1",progress:{value:0.12,label:"12%"}})'), '12% · stale · ⚠ Go offline');
console.log('PASS Go windows sort correctly, remain hidden from workspaces and show stale errors');
rows=[{id:'cw',title:'7d |4% (2d)|'}, {id:'cs',title:'5h |2% (4h)|'}, {id:'extra',title:'spend |none|'}];
assert.equal(run('sectionCount("usage")'),1);
assert.equal(run('sectionCount("workspaces")'),0);
assert.deepEqual(object('all().filter(claude).sort((a,b)=>usageOrder(a)-usageOrder(b)).map(usageWindow)'),['session','week']);
assert.equal(run('claude({title:"spend |5% ($5 of $100)|"})'),true);
assert.equal(run('usageDisplay({title:"5h |⚠ auth|"})'),'⚠ sign in');
assert.equal(run('usageWindow({title:"m7d |12%|bar|Opus"})'),'Opus');
console.log('PASS Claude section, periods, authentication errors and hidden zero spend');
