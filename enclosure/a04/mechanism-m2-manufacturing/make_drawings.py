"""Two-sheet development drawing set; dimensions come from profiles.json only."""
import hashlib,json,math,textwrap
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parent;data=json.loads((ROOT/'profiles.json').read_text(encoding='utf-8'))
for name,file in [('Regular','arial.ttf'),('Bold','arialbd.ttf'),('Mono','consola.ttf')]:pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
OUT=ROOT/'m2-s1-steel-development-drawings.pdf';c=canvas.Canvas(str(OUT),pagesize=(297*mm,210*mm),pageCompression=1,invariant=1);c.setTitle('AURA A04 M2 S1 - steel development drawings');c.setAuthor('AURA engineering development');c.setSubject('Quote and unpowered fixture geometry, not fabrication release')
INK=(.12,.16,.20);MUTED=(.35,.40,.43);ACCENT=(.52,.25,.11)
def color(col):c.setStrokeColorRGB(*col);c.setFillColorRGB(*col)
def text(x,y,s,size=8,font='Regular',align='left',col=INK):
 color(col);c.setFont(font,size);fn=c.drawString if align=='left' else c.drawCentredString if align=='center' else c.drawRightString;fn(x*mm,y*mm,s)
def line(x1,y1,x2,y2,width=.18,col=INK):color(col);c.setLineWidth(width*mm);c.line(x1*mm,y1*mm,x2*mm,y2*mm)
def arrow(x,y,dx,dy):
 nx,ny=-dy,dx;p=c.beginPath();p.moveTo(x*mm,y*mm);p.lineTo((x+dx*1.5+nx*.45)*mm,(y+dy*1.5+ny*.45)*mm);p.lineTo((x+dx*1.5-nx*.45)*mm,(y+dy*1.5-ny*.45)*mm);p.close();c.drawPath(p,fill=1,stroke=0)
def dimh(x1,x2,y,edge1,edge2,label):
 line(x1,edge1,x1,y+1,.12,MUTED);line(x2,edge2,x2,y+1,.12,MUTED);line(x1,y,x2,y,.13);arrow(x1,y,1,0);arrow(x2,y,-1,0);text((x1+x2)/2,y+1.7,label,8,'Regular','center')
def dimv(y1,y2,x,edge1,edge2,label):
 line(edge1,y1,x-1,y1,.12,MUTED);line(edge2,y2,x-1,y2,.12,MUTED);line(x,y1,x,y2,.13);arrow(x,y1,0,1);arrow(x,y2,0,-1);c.saveState();c.translate((x-2)*mm,(y1+y2)/2*mm);c.rotate(90);text(0,0,label,8,'Regular','center');c.restoreState()
def para(x,y,txt,width=95,size=8,leading=3.65):
 words=txt.split();linewords=[]
 for word in words:
  test=' '.join(linewords+[word])
  if pdfmetrics.stringWidth(test,'Regular',size)>width*mm and linewords:text(x,y,' '.join(linewords),size);y-=leading;linewords=[word]
  else:linewords.append(word)
 if linewords:text(x,y,' '.join(linewords),size);y-=leading
 return y

def notes(part):
 x=184;y=172
 for title,body in [
  ('MATERIAL / CERTIFICATE','ASTM A666 Type 301 / UNS S30100, HALF-HARD. Explicit lot certificate: 0.2% yield >= 110 ksi (758 MPa). Temper or hardness alone is insufficient.'),
  ('THICKNESS / DEFINED ACCEPTANCE',('Actual incoming metal: 0.28-0.32 mm.' if part=='shoe' else 'Actual incoming metal: 0.95-1.00 mm; no plus tolerance beyond 1.00 mm.')+' Preserve this minimum finished metal thickness after processing. Mesh thickness is a geometry gauge.'),
  ('CUTTING / EDGES','Preserve the supplied cold-worked temper. Quote cold cutting or cool machining and deburring. No anneal, weld or hot straightening without requalification. Thermal-cut edges require retained-property qualification.'),
  ('PROFILE / FLATNESS','No kerf compensation is included. Exact source facets are retained; no fitted arcs, fillets or chamfers are authorized. Preserve net CAD section after finishing. Quote achievable XY tolerance, edge condition and flatness for review; no numeric limits are approved here.'),
  ('INSULATION / RELEASE GATES','No burr or sharp edge may damage fitted insulation. Complete metal work before adhesive/insulation assembly. Coverage, retention, dielectric adequacy and finished packet fit remain unqualified. Native PCB fit and physical strength are not approved.')]:
  text(x,y,title,8,'Bold',col=ACCENT);y-=4.5;y=para(x,y,body);y-=3
 text(x,y,'SUPPLIER DATA / NO STOCK CONFIRMATION',8,'Bold',col=ACCENT);y-=4.5;y=para(x,y,'0.02-1.57 mm strip capability covers these thicknesses. This does not establish stock, lot, width, MOQ or process acceptance.');
 links=[('R1 - Elgiloy 301 material data','https://www.elgiloy.com/wp-content/uploads/2024/06/301-Alloy-Stainless-Steel-Data-Sheet-06042024.pdf'),('R2 - Elgiloy strip capability','https://www.elgiloy.com/wp-content/uploads/2024/05/ESM-Stainless-Strip-LineCard-DIGITAL-5.30.2024-compressed-1.pdf')]
 for label,url in links:
  text(x,y,label,7.5,col=(.1,.3,.45));c.linkURL(url,(x*mm,(y-1)*mm,(x+95)*mm,(y+3)*mm),relative=0);y-=4
 return y

for i,p in enumerate(data['scenarios'][0]['parts'],1):
 shoe=p['object'].startswith('08_');short='shoe' if shoe else 'lower-support';name='METAL PLUNGER SHOE' if shoe else 'LOWER STEEL SUPPORT';pts=p['profileLocalXYMm'];w=max(x for x,y in pts);h=max(y for x,y in pts);t=p['nominalMeshThicknessMm'];scale=8
 color((.96,.96,.94));c.rect(0,181*mm,297*mm,29*mm,fill=1,stroke=0);text(12,198,'AURA / A04 M2 S1',15,'Bold');text(12,188,name+'  |  MFG-D01  |  SHEET '+str(i)+' OF 2',10,'Bold');text(285,199,'DEVELOPMENT',12,'Bold','right',ACCENT);text(285,189,'QUOTE / UNPOWERED FIXTURE ONLY',8,'Bold','right',ACCENT);line(12,180,285,180,.25)
 text(12,174,'TOP VIEW FROM +Z  /  CAD +Y UP  /  NO HOLES',8,'Bold');line(178,36,178,175,.15,(.72,.74,.74));notes(short)
 ox,oy=(58,91) if shoe else (43,53);path=c.beginPath();path.moveTo((ox+pts[0][0]*scale)*mm,(oy+pts[0][1]*scale)*mm)
 for x,y in pts[1:]:path.lineTo((ox+x*scale)*mm,(oy+y*scale)*mm)
 path.close();color((.17,.23,.26));c.setLineWidth(.3*mm);c.setFillColorRGB(.87,.91,.91);c.drawPath(path,fill=1,stroke=1)
 # Envelope dimensions use the displayed envelope origin, without inventing a physical datum.
 dimh(ox,ox+w*scale,oy+h*scale+(12 if shoe else 13),oy+h*scale,oy+h*scale,f'{w:.3f}')
 dimv(oy,oy+h*scale,ox-12,ox,ox,f'{h:.3f}')
 line(ox-2,oy,ox+3,oy,.12,MUTED);line(ox,oy-2,ox,oy+3,.12,MUTED);text(ox-1,oy-5,'O',7,'Bold');text(12,32,'O = lower-left envelope intersection; not a machined datum.',7.5)
 if not shoe:
  top=[(a,b) for a,b in zip(pts,pts[1:]+pts[:1]) if abs(a[1]-h)<1e-5 and abs(b[1]-h)<1e-5];assert len(top)==2
  tips=sorted((min(a[0],b[0]),max(a[0],b[0])) for a,b in top);centers=[sum(v)/2 for v in tips]
  for left,right in tips:dimh(ox+left*scale,ox+right*scale,oy+h*scale+4,oy+h*scale,oy+h*scale,f'{right-left:.3f}')
  y=oy+h*scale-9
  for xc in centers:
   c.setDash(1.2*mm,1.2*mm);line(ox+xc*scale,y-3,ox+xc*scale,oy+h*scale+1,.12,MUTED);c.setDash()
  dimh(ox+centers[0]*scale,ox+centers[1]*scale,y,y,y,f'{centers[1]-centers[0]:.3f} centres (REF)')
 # Edge view is the +X-width projection of a constant-thickness prism.
 by=45 if shoe else 40;color((.17,.23,.26));c.setLineWidth(.25*mm);c.setFillColorRGB(.87,.91,.91);c.rect(ox*mm,by*mm,w*scale*mm,t*scale*mm,fill=1,stroke=1)
 text(ox,by-4,'EDGE VIEW / NO BENDS',7,'Bold');text(ox+w*scale/2,by+t*scale+3,f't = {t:.3f} MESH REF',8,'Bold','center');
 text(12,28,'VIEW SCALE 8:1 AT A4 / 100%. NOMINAL DIMENSIONS IN mm; DO NOT SCALE FOR FABRICATION.',7.2,'Bold');line(12,25,285,25,.2)
 text(12,20,'Origin in assembly CAD XY: '+', '.join(f'{v:.6f}' for v in p['cadOriginXYMm'])+' mm. DXF is 1:1, INSUNITS = 4 (mm).',7.2)
 text(12,15,'BLEND SHA256 '+data['scenarios'][0]['blendSha256'],6.6,'Mono');dx=ROOT/p['profileFile'];text(12,11,'DXF SHA256   '+hashlib.sha256(dx.read_bytes()).hexdigest(),6.6,'Mono');text(12,6,'Frozen source profiles verified against both depth variants and STL caps. Full concordance: profiles.json / manufacturing-verification.json.',6.8);text(285,6,str(i)+'/2',7,'Bold','right')
 c.showPage()
c.save();print(OUT)
