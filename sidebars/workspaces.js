// Retained cmux scene: local interactions never spawn a process or reload this file.
// tmux metadata uses one workspace description per window (a usage meter when available).
const C = {bg:'#1F2430', fg:'#D9D7CE', dim:'#8A9199', blue:'#73D0FF', green:'#87D96C', yellow:'#FFCC66', red:'#F28779'};
const all = () => data.workspaces() || [];
const groups = () => data.groups() || [];
const epoch = () => (data.clock() || {}).epoch || 0;
const text = (value, size=12, color=C.fg) => Text(value).font(size).monospaced().color(color);
// Empty/one-item keyed list gives conditional content a real mount/unmount lifecycle.
const when = (condition, build) => ForEach({items:()=>condition() ? [1] : [], key:()=> 'visible'}, build);
const match = (w, keys) => keys.some(k => w.title === k || (w.title || '').startsWith(k+' '));
const codex = w => match(w,['cx5h','cx7d']);
const claude = w => match(w,['5h','7d','m7d','spend']) && !(match(w,['spend']) && (w.title || '').split('|')[1]==='none');
const grok = w => match(w,['grokcredits']);
const opencodeGo = w => match(w,['go5h','go7d','go1m']);
const meter = w => match(w,['cx5h','cx7d','grokcredits','go5h','go7d','go1m','5h','7d','m7d','spend','ampu','ampo']);
const workingCount = w => (w.agents || []).filter(a=>a.status==='working' && epoch()-a.lastActivityAt<3600).length;
const compacting = w => (w.title || '').startsWith('⏳');
const working = w => (w.title || '').startsWith('⚡') || workingCount(w)>0;
const waiting = w => (w.title || '').startsWith('❓') || (w.agents || []).some(a=>a.kind!=='claude' && a.status==='needs_input');
const needsYou = w => !compacting(w) && (waiting(w) || (!working(w) && w.unread>0));
const repoInfo = w => !!(w.pr?.label || w.branch || w.dirty);
const showActivity = w => compacting(w) || working(w) || needsYou(w) || !repoInfo(w);
const activityColor = w => compacting(w) ? '#DFBFFF' : working(w) ? C.green : needsYou(w) ? C.yellow : C.dim;
function activityText(w) {
  if(compacting(w)) return 'Compacting…';
  if(waiting(w)) return 'asking…';
  if(working(w)) return w.progress?.label || (workingCount(w)>1 ? `Working… ×${workingCount(w)}` : 'Working…');
  return needsYou(w) ? (w.unread>1 ? `needs you · ${w.unread}` : 'needs you') : 'idle';
}
const anchor = w => groups().find(g=>g.anchorId===w.id);
const title = w => anchor(w)?.name || (w.title || '').replace(/^[⏳❓⚡]/u,'');
const hasColor = w => typeof w.color==='string' && w.color.startsWith('#');
const accentColor = w => hasColor(w) ? w.color : C.dim;
const accentOpacity = w => hasColor(w) ? 1 : 0;
const rowFill = w => w.selected ? '#33415ED9' : needsYou(w) ? '#FFCC661A' : (working(w)||compacting(w)) ? '#FFFFFF09' : '#FFFFFF06';
const numbered = w => !anchor(w) && !groups().some(g=>g.id===w.group && g.collapsed);
function shortcut(w) {
  if(!numbered(w)) return '';
  const rows=all().filter(numbered), pos=rows.filter(r=>r.index<w.index).length;
  return pos<8 ? `⌘${pos+1}` : pos===rows.length-1 ? '⌘9' : '';
}
const workspaceAction = (w, action, extra={}) => cmux('workspace.action',{workspace_id:w.id, action,...extra});
function workspaceRow(w) {
  return VStack({spacing:0},[
    HStack({alignment:'top',spacing:5},[
      HStack({alignment:'center',spacing:5},[
        HStack({alignment:'center',spacing:3},[
          Capsule().frame({width:3,height:26}).fill(()=>accentColor(w())).opacity(()=>accentOpacity(w())),
          text(()=>shortcut(w()),10,()=>w().selected ? C.fg : '#707A8C').frame({width:18}),
        ]),
        VStack({spacing:2},[
          HStack({spacing:5},[
            text(()=>title(w()),13,()=>w().selected ? '#FFFFFF' : C.fg)
              .weight(()=>w().selected ? 'bold' : 'medium')
              .lineLimit(()=>w().selected ? 3 : 2).help(()=>title(w())),
            when(()=>!!anchor(w()),()=>Image('square.stack').font(10).color(C.dim)),
            when(()=>!!w().pinned,()=>Image('pin.fill').font(9).color(C.dim)),
          ]),
          when(()=>showActivity(w()),()=>HStack({spacing:5},[
            when(()=>needsYou(w()),()=>Image('bell.fill').font(9).color(()=>activityColor(w()))),
            text(()=>activityText(w()),11,()=>activityColor(w())).lineLimit(1),
          ])),
          when(()=>repoInfo(w()),()=>HStack({spacing:4},[
            Image('arrow.triangle.branch').font(9).color('#6E7787'),
            text(()=>w().pr?.label ? w().pr.label+(w().pr.stale?' · stale':'') : (w().branch || ''),11,
              ()=>w().pr?.label && w().pr.status==='open' ? C.blue : C.dim).lineLimit(1),
            when(()=>!!w().dirty,()=>text('*',12,C.yellow).bold()),
          ])),
        ]).layoutPriority(1),
      ]).layoutPriority(1),
      Spacer({minLength:0}),
      when(()=>w().unread>0,()=>text(()=>String(w().unread),10,C.bg).bold().padding(4).background(C.yellow).cornerRadius(8)),
      Button('',()=>cmux('workspace.close',{workspace_id:w().id}),[
        Image('xmark').font(11).color(()=>w().selected?'#FFFFFF':needsYou(w())?C.yellow:'#A7AFBD').frame({width:18,height:20}),
      ]),
    ]).padding(6).background(()=>rowFill(w())).onTap(()=>cmux('workspace.select',{workspace_id:w().id}))
      .contextMenu([
        Button('Open',()=>cmux('workspace.select',{workspace_id:w().id})),
        Button(()=>w().pinned?'Unpin':'Pin',()=>workspaceAction(w(),w().pinned?'unpin':'pin')),
        // cmux 0.64.24 SceneNodeView omits menu nodes; keep colors directly in the context menu.
        Divider(),
        ...[['Orange',C.yellow],['Blue',C.blue],['Green',C.green],['Red',C.red]].map(([label,color])=>Button(label,()=>workspaceAction(w(),'set-color',{color}))),
        Button('Clear color',()=>workspaceAction(w(),'clear-color')),
        Divider(),
        Button('Move up',()=>workspaceAction(w(),'move-up')),
        Button('Move down',()=>workspaceAction(w(),'move-down')),
        Button('Move to top',()=>workspaceAction(w(),'move-top')),
        Divider(),Button('Close',()=>cmux('workspace.close',{workspace_id:w().id})).destructive(),
      ]),
    Divider(),
  ]);
}
function stale(w) {
  const stamp=(w.description || '').match(/^sentinel-updated:(\d+)/);
  return !!stamp && epoch()-Number(stamp[1])>900;
}
function usageDetail(w) {
  const detail=(w.title || '').split('|')[1] || '';
  if(detail.includes('⚠')) return detail;
  if(stale(w)) return 'stale · refresh needed';
  if(w.progress?.value>=0) return w.progress.label || '';
  return detail || 'waiting…';
}
const usageOrder = w => match(w,['5h','cx5h','go5h']) ? 0 : match(w,['go1m','m7d']) ? 2 : match(w,['spend']) ? 3 : 1;
const usageWindow = w => match(w,['m7d']) ? (w.title || '').split('|')[3] || 'model' : match(w,['spend']) ? 'extra' : ['session','week','month'][usageOrder(w)];
function usageDisplay(w) {
  const detail=usageDetail(w);
  if(!detail.includes('⚠')) return stale(w) ? 'stale' : detail;
  const cached=detail.match(/^(\d+(?:\.\d+)?%) · stale/);
  if(cached) return `⚠ ${cached[1]} · stale`;
  if(/login|credentials|key rejected|auth/i.test(detail)) return '⚠ sign in';
  if(/offline|network|temporarily unavailable/i.test(detail)) return '⚠ offline';
  if(/throttl|rate limit/i.test(detail)) return '⚠ rate limited';
  if(/subscription required/i.test(detail)) return '⚠ no plan';
  if(/access blocked/i.test(detail)) return '⚠ blocked';
  if(/format|no data/i.test(detail)) return '⚠ no data';
  return '⚠ unavailable';
}
function usageSection(label,filter) {
  return when(()=>all().some(filter),()=>VStack({spacing:0},[
    VStack({spacing:4},[
    HStack({spacing:6},[text(label,11,C.fg).weight('medium').lineLimit(1),Spacer()]),
    ForEach({items:()=>all().filter(filter).sort((a,b)=>usageOrder(a)-usageOrder(b)),key:w=>w.id},w=>
      HStack({spacing:6},[
        HStack({spacing:0},[
          text(()=>usageWindow(w()),12,'#CCCAC2').lineLimit(1),Spacer({minLength:0}),
        ]).frame({width:56}).layoutPriority(1),
        Spacer({minLength:0}),
        text(()=>usageDisplay(w()),11,()=>stale(w()) || usageDetail(w()).includes('⚠')?C.yellow:C.dim).lineLimit(1).help(()=>usageDetail(w())),
      ])),
    ]).padding(9),Divider(),
  ]));
}

// Live metadata updates preserve the scene and local open/confirmation state.
let cachedTmux = {sessions:[],pending:null};
function tmuxData() {
  for(const w of all()) {
    const d=w.description || '', index=d.indexOf('\nsentinel-tmux:');
    if(index<0) continue;
    try {
      const value=JSON.parse(d.slice(index+'\nsentinel-tmux:'.length));
      if(Array.isArray(value.sessions)) cachedTmux=value;
    } catch(_) {}
  }
  return cachedTmux;
}
const [expanded,setExpanded]=signal(null);
const [confirming,setConfirming]=signal(null);
const [dismissed,setDismissed]=signal(null);
const [closing,setClosing]=signal(null);
function toggleTmux(id) {
  setConfirming(null);
  setDismissed(tmuxData().pending);
  setExpanded(expanded()===id ? null : id);
}
function needsConfirm(row) {
  const pending=tmuxData().pending;
  return confirming()===row.key || (pending===row.key && dismissed()!==pending);
}
function requestClose(row) {
  if(row.protected) { setConfirming(row.key); return; }
  setClosing({key:row.key,at:epoch()});
  openURL(row.close_url);
}
function confirmClose(row) {
  setConfirming(null);
  setDismissed(tmuxData().pending);
  setClosing({key:row.key,at:epoch()});
  openURL(row.confirm_url);
}
function cancelClose() {setConfirming(null);setDismissed(tmuxData().pending);}
const detail = (label,value,color='#ECF2FA') => VStack({spacing:3},[text(label,10,'#AEBED1'),text(value,12,color)]);
const dangerButton = (label,action) => Button('',action,[
  HStack({spacing:6},[text(label,12,'#FFAAA5').bold(),Spacer()]).padding(8).background('#493440').cornerRadius(5),
]);
// `@port` is operator-authored text, so only plain numbers may become links: a stray
// note in the annotation must never end up pasted into a URL. Commas or spaces
// separate several annotations; duplicates collapse to one chip.
function sessionPorts(row) {
  const ports=[];
  for(const value of String(row.port || '').split(/[,，、;；\s]+/)) {
    const port=Number(value);
    if(/^\d{1,5}$/.test(value) && port>0 && port<65536 && !ports.includes(port)) ports.push(port);
  }
  return ports;
}
// The port chip is the only tmux affordance that leaves the app: NSWorkspace opens it
// in the default browser. Nothing is fetched or probed here, so a dead port is a
// harmless browser error rather than a broken row.
function portButton(row,port) {
  return Button('',()=>openURL(`http://127.0.0.1:${port()}`),[
    text(()=>String(port()),11,'#8DD8FF').padding(5).background('#20304A').cornerRadius(5),
  ]).help(()=>`在浏览器打开 http://127.0.0.1:${port()}`);
}
function tmuxRow(r) {
  const open=()=>expanded()===r().key;
  return VStack({spacing:0},[
    HStack({alignment:'top',spacing:5},[
      Image(()=>open()?'chevron.down':'chevron.right').font(9).color(C.dim).frame({width:12,height:15}),
      text(()=>r().name,12,'#F0F5FC').weight('medium').lineLimit(()=>open()?null:2).layoutPriority(1),Spacer({minLength:0}),
    ]).padding(6).background(()=>open()?'#33415ED9':'#FFFFFF06')
      .help(()=>r().name).onTap(()=>toggleTmux(r().key)),
    when(open,()=>VStack({spacing:12},[
      detail('备注',()=>r().note || '未填写备注'),detail('项目',()=>r().project || '未标注'),
      HStack({spacing:8},[
        text(()=>r().lifecycle,11,()=>r().protected?'#99D98C':'#FFD187').bold(),Spacer({minLength:0}),
        when(()=>sessionPorts(r()).length===0,()=>text('端口 无标注',11,'#8DD8FF')),
        when(()=>sessionPorts(r()).length>0,()=>HStack({spacing:5},[
          text('端口',10,'#7E93A8'),
          ForEach({items:()=>sessionPorts(r()),key:p=>String(p)},p=>portButton(r,p)),
        ])),
      ]),
      text(()=>`${r().windows} 个窗口 · ${r().attached} 个连接`,11,'#B5C6D9'),Divider(),
      when(()=>needsConfirm(r()),()=>VStack({spacing:8},[
        text('确认关闭这个常驻会话？',12,'#FFD187').bold(),
        text('该会话的所有窗口和任务将结束。',11,'#D6E1F0'),
        HStack({spacing:8},[
          dangerButton('确认关闭',()=>confirmClose(r())),
          Button('',cancelClose,[text('取消',12,'#F0F5FC').padding(8).background('#3A4D64').cornerRadius(5)]),
        ]),
      ])),
      when(()=>!needsConfirm(r()),()=>dangerButton(
        ()=>closing()?.key===r().key && epoch()-closing().at<10 ? '正在关闭…' : '× 关闭会话',()=>requestClose(r()))),
    ]).padding(10).background('#263345')),
    Divider(),
  ]);
}

// Peer sections share one header and separator contract. Order changes
// reconcile the keyed sections, preserving workspace and tmux row identity.
const SECTION_IDS=['usage','workspaces','tmux'];
const SECTION_TITLES={usage:'USAGE',workspaces:'WORKSPACES',tmux:'TMUX'};
const [layoutOverride,setLayoutOverride]=signal(null);
function layout() {
  const saved=layoutOverride() || tmuxData().layout || {};
  const order=Array.isArray(saved.order) ? saved.order.filter((id,i,a)=>SECTION_IDS.includes(id) && a.indexOf(id)===i) : [];
  return {order:[...order,...SECTION_IDS.filter(id=>!order.includes(id))],collapsed:Object.fromEntries(SECTION_IDS.filter(id=>typeof saved.collapsed?.[id]==='boolean').map(id=>[id,saved.collapsed[id]])),revision:saved.revision || 0};
}
function saveLayout(next) {
  next.revision=Math.max(Date.now(),layout().revision+1);
  setLayoutOverride(next); // Change the scene first; persistence runs behind it.
  openURL('cmux-sentinel://layout/'+encodeURIComponent(JSON.stringify(next)));
}
function toggleSection(id) {
  const current=layout();
  if(id==='tmux') cancelClose();
  saveLayout({...current,collapsed:{...current.collapsed,[id]:!current.collapsed[id]}});
}
function moveSection(id,where) {
  const current=layout(),order=[...current.order],from=order.indexOf(id);
  const to=where==='top' ? 0 : Math.max(0,Math.min(order.length-1,from+where));
  if(from===to) return;
  order.splice(from,1);order.splice(to,0,id);
  saveLayout({...current,order});
}
function sectionCount(id) {
  if(id==='workspaces') return all().filter(w=>!meter(w)).length;
  if(id==='tmux') return tmuxData().sessions.length;
  return Number(all().some(claude))+Number(all().some(codex))+Number(all().some(grok))+Number(all().some(opencodeGo));
}
function sectionBody(id) {
  if(id==='usage') return VStack({spacing:0},[
    usageSection('CLAUDE CODE · USED',claude),
    usageSection('GPT / CODEX · USED',codex),usageSection('GROK · USED',grok),
    usageSection('OPENCODE GO · USED',opencodeGo),
    when(()=>sectionCount(id)===0,()=>VStack({spacing:0},[text('暂无用量数据',11,C.dim).padding(9),Divider()])),
  ]);
  if(id==='workspaces') return Reorderable({items:()=>all().filter(w=>!meter(w)).sort((a,b)=>a.index-b.index),key:w=>w.id,
    onMove:(workspace_id,index)=>cmux('workspace.reorder',{workspace_id,index})},workspaceRow);
  return VStack({spacing:0},[
    ForEach({items:()=>tmuxData().sessions,key:r=>r.key},tmuxRow),
    when(()=>tmuxData().sessions.length===0,()=>VStack({spacing:0},[text('暂无 tmux 会话',11,C.dim).padding(9),Divider()])),
  ]);
}
function sidebarSection(id) {
  return VStack({spacing:0},[
    HStack({spacing:8},[
      Image(()=>layout().collapsed[id]?'chevron.right':'chevron.down').font(9).color(C.dim).frame({width:12,height:12}),
      text(SECTION_TITLES[id],10,C.dim).bold(),Spacer(),text(()=>String(sectionCount(id)),10,'#6E7787'),
    ]).padding(9).background(C.bg).hoverBackground('#FFFFFF08')
      .help('点击折叠或展开；右键调整模块顺序').onTap(()=>toggleSection(id))
      .contextMenu([
        Button(()=>layout().collapsed[id]?'展开':'折叠',()=>toggleSection(id)),Divider(),
        Button('上移',()=>moveSection(id,-1)),Button('下移',()=>moveSection(id,1)),Button('置顶',()=>moveSection(id,'top')),
      ]),
    Divider(),when(()=>!layout().collapsed[id],()=>sectionBody(id)),
  ]);
}
sidebar(()=>VStack({spacing:0},[
  HStack({spacing:10},[
    text('Cmux',12).bold(),Spacer(),
    ...[[needsYou,'bell.fill',C.yellow],[working,'bolt.fill',C.green],[compacting,'hourglass','#DFBFFF']].map(([filter,icon,color])=>
      when(()=>all().some(filter),()=>HStack({spacing:4},[
        Image(icon).font(10).color(color),text(()=>String(all().filter(filter).length),11,color).bold(),
      ]))),
  ]).padding(9),Divider(),
  ForEach({items:()=>layout().order,key:id=>id},id=>sidebarSection(id())),Spacer(),
]).background(C.bg));
