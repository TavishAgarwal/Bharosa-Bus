// Drag the line between the panel and the map to change the panel width. Double-click resets it.
(function(){
 const app=document.querySelector(".app");if(!app)return;
 const KEY="bb-panel-w",DEF=460,MIN=340;
 const clamp=w=>Math.round(Math.max(MIN,Math.min(w,Math.max(MIN,window.innerWidth-320))));
 const set=w=>{app.style.setProperty("--panel-w",clamp(w)+"px");window.dispatchEvent(new Event("resize"));};
 const saved=parseInt(localStorage.getItem(KEY)||"",10);if(saved)set(saved);
 const h=document.createElement("div");h.className="resizer";h.title="Drag to resize · double-click to reset";
 h.setAttribute("role","separator");h.setAttribute("aria-orientation","vertical");h.tabIndex=0;app.appendChild(h);
 let drag=false;
 h.addEventListener("pointerdown",e=>{drag=true;h.setPointerCapture(e.pointerId);document.body.classList.add("resizing");});
 h.addEventListener("pointermove",e=>{if(drag)set(e.clientX-app.getBoundingClientRect().left);});
 const end=()=>{if(!drag)return;drag=false;document.body.classList.remove("resizing");
  localStorage.setItem(KEY,parseInt(getComputedStyle(app).getPropertyValue("--panel-w"),10));};
 h.addEventListener("pointerup",end);h.addEventListener("pointercancel",end);
 h.addEventListener("dblclick",()=>{localStorage.removeItem(KEY);set(DEF);});
 h.addEventListener("keydown",e=>{const cur=parseInt(getComputedStyle(app).getPropertyValue("--panel-w"),10)||DEF;
  if(e.key==="ArrowLeft"||e.key==="ArrowRight"){set(cur+(e.key==="ArrowLeft"?-20:20));localStorage.setItem(KEY,clamp(cur+(e.key==="ArrowLeft"?-20:20)));e.preventDefault();}});
 window.addEventListener("resize",()=>{const cur=parseInt(app.style.getPropertyValue("--panel-w"),10);if(cur&&clamp(cur)!==cur)app.style.setProperty("--panel-w",clamp(cur)+"px");});
})();
