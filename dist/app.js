// Shared by routes.html and operators.html: colours, labels, map setup and drawing one route by stretch.
const COLOR={seats:"#1a7f37",standing:"#b7791f",crowded:"#c62828",unknown:"#9e9e9e"};
const CODE=["seats","standing","crowded"];            // route_profiles.json level codes; -1 = not enough tickets
const LABEL={seats:"Seats likely",standing:"Standing room",crowded:"Crowded",unknown:"Not enough data"};
const BANDS_SHORT=["5-6","7-10","11-16","17-20","21-4"];
const $=id=>document.getElementById(id);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const lvl=c=>c<0?"unknown":CODE[c];
const cap=v=>v>100?"100+":v;

function makeMap(el){
  if(typeof L==="undefined"){$(el).innerHTML='<div class="nomap">Map needs an internet connection (map library and tiles).</div>';return null;}
  const m=L.map(el,{zoomControl:false}).setView([28.62,77.21],11);
  L.control.zoom({position:"bottomright"}).addTo(m);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    {maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(m);
  m._bb=L.layerGroup().addTo(m);
  return m;
}
function legendHTML(){
  return ["seats","standing","crowded"].map(k=>`<span><i style="background:${COLOR[k]}"></i>${LABEL[k]}</span>`).join("")+
    `<span><i style="background:repeating-linear-gradient(90deg,#555 0 6px,transparent 6px 10px)"></i>${LABEL.unknown}</span>`;
}
// stops: [[lat,lon,name],...]; prof: {level:[codes], load:[people]} or null
function drawRoute(map,stops,prof,route){
  if(!map)return;
  map._bb.clearLayers();
  const pts=[];
  for(let i=0;i+1<stops.length;i++){
    const c=prof?prof.level[i]:-1, k=lvl(c), nd=c<0;
    const tip=`${esc(stops[i][2])} → ${esc(stops[i+1][2])}<br><b>${LABEL[k]}</b>`+(nd?"":` · about ${cap(prof.load[i])} people`);
    L.polyline([stops[i],stops[i+1]].map(s=>[s[0],s[1]]),{color:nd?"#555":COLOR[k],weight:nd?5:7,opacity:.95,dashArray:nd?"8 6":null,lineCap:nd?"butt":"round"})
      .bindTooltip(tip,{sticky:true}).addTo(map._bb);
  }
  stops.forEach((s,i)=>{pts.push([s[0],s[1]]);
    if(i>0&&i<stops.length-1)L.circleMarker([s[0],s[1]],{radius:2.5,color:"#161616",weight:1,fillColor:"#fff",fillOpacity:1}).bindTooltip(esc(s[2])).addTo(map._bb);});
  [[stops[0],route+" start"],[stops[stops.length-1],"end"]].forEach(([s,t],j)=>{
    L.marker([s[0],s[1]],{icon:L.divIcon({className:"",html:`<span class="pin">${esc(s[2].split(" (")[0].slice(0,32))}</span>`,iconSize:null,iconAnchor:[0,28]})}).addTo(map._bb);
    L.circleMarker([s[0],s[1]],{radius:6,color:"#fff",weight:2,fillColor:"#161616",fillOpacity:1}).addTo(map._bb);});
  if(pts.length)map.fitBounds(L.latLngBounds(pts),{paddingTopLeft:[40,70],paddingBottomRight:[40,window.innerWidth>860?170:40]});
}
function stretchBar(prof,n,cls){
  const lv=prof?prof.level:Array(n).fill(-1);
  return `<div class="${cls||"bar"}">${lv.map(c=>`<span style="flex:1;background:${COLOR[lvl(c)]}"></span>`).join("")}</div>`;
}
