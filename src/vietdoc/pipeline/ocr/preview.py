"""Self-contained local OCR review artifact; no server or business workflow."""

from base64 import b64encode
from io import BytesIO
import json

from PIL import Image

from vietdoc.contracts.ocr import OcrPage


def render_preview(canonical: Image.Image, page: OcrPage, *, transcript: str | None = None) -> str:
    """Embed canonical pixels and immutable OCR data, without external resources.

    OCR/transcript content is data: JSON script delimiters are escaped and the
    viewer inserts text with textContent, never HTML. No file URLs/remote fetches.
    """
    if canonical.mode != "RGB" or canonical.size != (page.width, page.height):
        raise ValueError("Preview must use the matching canonical RGB image")
    if transcript is not None and not isinstance(transcript, str):
        raise ValueError("Transcript must be text or null")
    with BytesIO() as stream:
        canonical.save(stream, format="PNG")
        png = b64encode(stream.getvalue()).decode("ascii")
    payload = json.dumps({"ocr": page.to_dict(), "transcript": transcript}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _HTML.replace("__CANONICAL_PNG__", png).replace("__OCR_DATA__", payload)


_HTML = r'''<!doctype html>
<html lang="vi">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Kiểm tra OCR — VietDoc</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f8;color:#192637;font:15px/1.5 system-ui,sans-serif}
header{padding:18px 24px;background:#fff;border-bottom:1px solid #dce2ea}h1{font-size:23px;margin:0 0 4px}
p{margin:4px 0}.muted{color:#52657a;font-size:13px}main{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px;padding:18px}
.card{background:#fff;border:1px solid #dce2ea;border-radius:10px;padding:16px;min-width:0}
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}
button{font:inherit;cursor:pointer;border:1px solid #b9c6d6;border-radius:6px;background:#fff;padding:7px 11px;color:inherit}
button:focus-visible{outline:3px solid #427dff}button:hover{background:#edf3ff}
.page{position:relative;max-width:1200px;margin:auto;background:#fff;line-height:0}
.page img{display:block;width:100%;height:auto}.page svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
polygon{fill:#ed34251a;stroke:#c83226;stroke-width:2;vector-effect:non-scaling-stroke;cursor:pointer}
polygon.selected{fill:#1675ff26;stroke:#065bd6;stroke-width:3}polygon:focus{outline:none;stroke:#065bd6;stroke-width:4}
#blocks{display:flex;flex-direction:column;gap:7px;max-height:58vh;overflow:auto;margin:12px 0}
.block{text-align:left;padding:9px 11px}.block strong{display:block;white-space:pre-wrap;overflow-wrap:anywhere}
.block[aria-pressed=true]{border-color:#065bd6;background:#edf3ff}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,monospace}
details{margin-top:14px}summary{cursor:pointer;font-weight:600}#details{min-height:88px}.empty{padding:16px;background:#f3f5f8;border-radius:6px}
@media(max-width:850px){main{grid-template-columns:1fr;padding:10px}header{padding:14px}#blocks{max-height:320px}}
</style>
<header><h1>Kiểm tra OCR</h1><p id="summary"></p><p class="muted">Chọn vùng chữ trên ảnh hoặc trong danh sách để kiểm vị trí. Score là điểm của OCR engine.</p></header>
<main>
<section class="card" aria-label="Ảnh canonical và highlight">
<div class="toolbar"><button id="all" type="button">Hiện tất cả vùng</button><label><input id="visible" type="checkbox" checked> Hiện highlight</label><span id="selection" role="status" aria-live="polite">Tất cả vùng OCR</span></div>
<div class="page"><img alt="Ảnh canonical dùng để đối chiếu vị trí OCR" src="data:image/png;base64,__CANONICAL_PNG__"><svg id="overlay" xmlns="http://www.w3.org/2000/svg" aria-label="Các vùng chữ OCR"></svg></div>
</section>
<aside class="card"><strong>Vùng chữ phát hiện</strong><p class="muted">Tọa độ pixel theo ảnh canonical; quad JSON nằm trong [0,1].</p><div id="blocks"></div><pre id="details">Chọn một vùng để xem tọa độ.</pre>
<details open><summary>Text OCR theo thứ tự đọc</summary><pre id="text"></pre></details>
<details id="reference"><summary>Transcript đối chiếu</summary><p id="comparison" class="muted"></p><pre id="transcript"></pre></details>
<details><summary>Phiên bản OCR</summary><pre id="version"></pre></details>
</aside>
</main>
<script id="ocr-data" type="application/json">__OCR_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('ocr-data').textContent), page=data.ocr;
const el=id=>document.getElementById(id), ns='http://www.w3.org/2000/svg', shapes=[], buttons=[];
el('summary').textContent=`${page.width} × ${page.height} px · Trang ${page.page+1} · ${page.blocks.length} vùng chữ`;
el('overlay').setAttribute('viewBox',`0 0 ${page.width} ${page.height}`);
el('text').textContent=page.blocks.map(b=>b.text).join('\n') || 'Không phát hiện vùng chữ.';
el('version').textContent=page.ocr_version;
function choose(index){
 const block=page.blocks[index];
 shapes.forEach((shape,i)=>{if(shape){shape.style.display=i===index?'':'none';shape.classList.toggle('selected',i===index);}});
 buttons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
 el('selection').textContent=block.quad?`Đang chọn ${block.block_id}`:`${block.block_id}: không có tọa độ`;
 const pixels=block.quad?block.quad.map(([x,y])=>[+(x*page.width).toFixed(2),+(y*page.height).toFixed(2)]):null;
 el('details').textContent=JSON.stringify({block_id:block.block_id,text:block.text,quad_pixels:pixels,quad_normalized:block.quad,ocr_score:block.score,geometry_reason:block.geometry_reason},null,2);
}
page.blocks.forEach((block,index)=>{
 const button=document.createElement('button');button.type='button';button.className='block';button.setAttribute('aria-pressed','false');
 const title=document.createElement('strong');title.textContent=block.text;button.append(title);
 const caption=document.createElement('span');caption.className='muted';caption.textContent=`${block.block_id} · score ${block.score===null?'chưa có':block.score.toFixed(2)}${block.quad?'':' · không có tọa độ'}`;button.append(caption);
 button.addEventListener('click',()=>choose(index));el('blocks').append(button);buttons.push(button);
 let polygon=null;
 if(block.quad){polygon=document.createElementNS(ns,'polygon');polygon.setAttribute('points',block.quad.map(([x,y])=>`${x*page.width},${y*page.height}`).join(' '));polygon.setAttribute('tabindex','0');polygon.setAttribute('role','button');polygon.setAttribute('aria-label',`${block.block_id}: ${block.text}`);
  const tooltip=document.createElementNS(ns,'title');tooltip.textContent=block.text;polygon.append(tooltip);
  polygon.addEventListener('click',()=>choose(index));polygon.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(index);}});el('overlay').append(polygon);}
 shapes.push(polygon);
});
if(!page.blocks.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='Không phát hiện vùng chữ.';el('blocks').append(empty);}
el('all').addEventListener('click',()=>{shapes.forEach(shape=>{if(shape){shape.style.display='';shape.classList.remove('selected');}});buttons.forEach(button=>button.setAttribute('aria-pressed','false'));el('selection').textContent='Tất cả vùng OCR';el('details').textContent='Chọn một vùng để xem tọa độ.';});
el('visible').addEventListener('change',event=>{el('overlay').style.visibility=event.target.checked?'visible':'hidden';});
if(data.transcript===null){el('reference').hidden=true;}else{el('reference').open=true;el('transcript').textContent=data.transcript;const normalize=text=>text.trim().split(/\s+/u).join(' ');el('comparison').textContent=normalize(data.transcript)===normalize(page.blocks.map(b=>b.text).join(' '))?'Trùng transcript sau chuẩn hóa khoảng trắng.':'Có khác biệt với transcript. Prediction OCR được giữ nguyên.';}
</script>
</html>'''
