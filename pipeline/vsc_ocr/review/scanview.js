// The scan of a page with boxes on it, shared by page.html and diacritic.html.
// The page needs #pageLabel, #tabs, #scanview > #sheet > #img, #prevPage,
// #nextPage and [data-zoom] buttons; showPage(n, boxes, tabs) shows page n
// with its boxes ([{page, bbox: [x0, y0, x1, y1] as fractions}]) and a tab per
// page in `tabs`.
const scan = { page: null, boxes: [], zoom: 1, onError: n => {} };
try { scan.zoom = +localStorage.getItem("zoom") || 1; } catch (e) {}

function showPage(n, boxes, tabs) {
  scan.page = n;
  scan.boxes = boxes || [];
  document.querySelector("#pageLabel").textContent = "pdf p." + n;
  const t = document.querySelector("#tabs");
  t.innerHTML = "";
  if (tabs && tabs.length > 1) for (const p of tabs) {
    const btn = document.createElement("button");
    btn.className = "tab" + (p === n ? " on" : "");
    btn.textContent = "p." + p;
    btn.onclick = () => showPage(p, scan.boxes, tabs);
    t.appendChild(btn);
  }
  const img = document.querySelector("#img"), sheet = document.querySelector("#sheet");
  sheet.style.width = (scan.zoom * 100) + "%";
  sheet.querySelectorAll(".box").forEach(x => x.remove());
  const draw = () => {
    const mine = scan.boxes.filter(x => x.page === n);
    for (const x of mine) {
      const d = document.createElement("div");
      d.className = "box" + (x.approx ? " approx" : "");
      d.title = "Drag to move, drag an edge or corner to resize";
      place(d, x.bbox);
      draggable(d, x);
      sheet.appendChild(d);
    }
    if (mine.length) {
      const v = document.querySelector("#scanview"), top = Math.min(...mine.map(x => x.bbox[1])) * img.clientHeight;
      if (top < v.scrollTop || top > v.scrollTop + v.clientHeight - 80) v.scrollTo({ top: Math.max(0, top - 60), behavior: "smooth" });
    }
  };
  const src = "/scan/" + n;
  if (img.getAttribute("src") !== src) { img.onload = draw; img.onerror = () => scan.onError(n); img.src = src; }
  else draw();
}

function place(d, [x0, y0, x1, y1]) {
  Object.assign(d.style, { left: x0 * 100 + "%", top: y0 * 100 + "%",
                           width: (x1 - x0) * 100 + "%", height: (y1 - y0) * 100 + "%" });
}

const MIN_BOX = 0.005;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function edgesAt(d, e) {
  const r = d.getBoundingClientRect(), w = Math.min(7, r.width / 3), h = Math.min(7, r.height / 3);
  return { l: e.clientX - r.left < w, r: r.right - e.clientX < w, t: e.clientY - r.top < h, b: r.bottom - e.clientY < h };
}

function cursorFor({ l, r, t, b }) {
  if ((l && t) || (r && b)) return "nwse-resize";
  if ((r && t) || (l && b)) return "nesw-resize";
  if (l || r) return "ew-resize";
  if (t || b) return "ns-resize";
  return "move";
}

// Move a box, or resize it by an edge or corner, when it doesn't cover all of
// its text. Only on screen: the box changes for this visit, nothing is saved.
function draggable(d, x) {
  d.addEventListener("pointermove", e => { if (!d.hasPointerCapture(e.pointerId)) d.style.cursor = cursorFor(edgesAt(d, e)); });
  d.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    e.preventDefault();
    const sheet = document.querySelector("#sheet").getBoundingClientRect(), from = [...x.bbox], ed = edgesAt(d, e);
    const move = !(ed.l || ed.r || ed.t || ed.b), sx = e.clientX, sy = e.clientY;
    d.setPointerCapture(e.pointerId);
    d.classList.add("dragging");
    const onMove = ev => {
      const dx = (ev.clientX - sx) / sheet.width, dy = (ev.clientY - sy) / sheet.height;
      let [x0, y0, x1, y1] = from;
      if (move) {
        const mx = clamp(dx, -x0, 1 - x1), my = clamp(dy, -y0, 1 - y1);
        x0 += mx; x1 += mx; y0 += my; y1 += my;
      } else {
        if (ed.l) x0 = clamp(x0 + dx, 0, x1 - MIN_BOX);
        if (ed.r) x1 = clamp(x1 + dx, x0 + MIN_BOX, 1);
        if (ed.t) y0 = clamp(y0 + dy, 0, y1 - MIN_BOX);
        if (ed.b) y1 = clamp(y1 + dy, y0 + MIN_BOX, 1);
      }
      x.bbox = [x0, y0, x1, y1];
      place(d, x.bbox);
    };
    const end = () => {
      d.classList.remove("dragging");
      d.removeEventListener("pointermove", onMove);
      d.removeEventListener("pointerup", end);
      d.removeEventListener("pointercancel", end);
    };
    d.addEventListener("pointermove", onMove);
    d.addEventListener("pointerup", end);
    d.addEventListener("pointercancel", end);
  });
}

document.querySelector("#prevPage").onclick = () => showPage(Math.max(1, scan.page - 1), scan.boxes);
document.querySelector("#nextPage").onclick = () => showPage(scan.page + 1, scan.boxes);
document.querySelectorAll("[data-zoom]").forEach(b => b.onclick = () => {
  scan.zoom = +b.dataset.zoom;
  try { localStorage.setItem("zoom", scan.zoom); } catch (e) {}
  showPage(scan.page, scan.boxes);
});
