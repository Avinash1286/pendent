"""Generate the nominal A03 mechanical reference sheet as a standalone SVG."""
from pathlib import Path
root=Path(__file__).resolve().parent
out=['''<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1050" viewBox="0 0 1440 1050">
<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto-start-reverse"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#455267"/></marker></defs>
<rect width="1440" height="1050" fill="#fafbf9"/>
<style>text{font-family:Arial,sans-serif;fill:#1c2939}.title{font-size:31px;font-weight:700}.sub{font-size:14px;fill:#5f6e80}.label{font-size:15px}.small{font-size:12px}.dim{stroke:#455267;stroke-width:1;fill:none;marker-start:url(#arrow);marker-end:url(#arrow)}.guide{stroke:#a4adba;stroke-width:1;fill:none}.body{fill:#dce1e4;stroke:#253342;stroke-width:1.5}.line{stroke:#253342;stroke-width:1.3;fill:none}</style>
<text x="64" y="63" class="title">AURA / A03</text><text x="64" y="91" class="sub">CAPSULE PENDANT · NOMINAL MECHANICAL REFERENCE · UNITS mm · NOT TO SCALE FOR FABRICATION</text>
<text x="1376" y="63" text-anchor="end" class="label">28 × 48 × 10</text><text x="1376" y="88" text-anchor="end" class="sub">54 mm including integrated bail</text>
<path d="M64 115H1376" stroke="#b4bdc7"/>
''']
def text(x,y,s,cl='label',anchor='middle'):out.append(f'<text x="{x}" y="{y}" class="{cl}" text-anchor="{anchor}">{s}</text>')
def rect(x,y,w,h,r,fill,stroke='#253342',sw=1.3):out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def line(x,y,a,b,cl='guide'):out.append(f'<path d="M{x} {y}L{a} {b}" class="{cl}"/>')
def circle(x,y,r,fill):out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="#253342" stroke-width=".8"/>')
def dim(x,y,a,b,label,tx,ty):line(x,y,a,b,'dim');text(tx,ty,label,'small')
S=7;cy=395
for cx,label in [(210,'FRONT / RECORD FACE'),(570,'REAR / CHARGING')]:
    text(cx,158,label)
    rect(cx-98,cy-168,196,336,97.8,'#dce1e4')
    rect(cx-19.25,cy-210,38.5,50.4,7.4,'#c3cbd0')
    if cx==210:
        rect(cx-81.2,cy-151.2,162.4,302.4,81,'#101a23')
        for x in [-8.5,8.5]:circle(cx+x*S,cy-8.5*S,2.45,'#020508')
        circle(cx,cy+7,1.75,'#d5edff')
        rect(cx+95,cy-17.5,4,32.2,2,'#758492')
        text(cx,597,'Full face: 23.2 × 43.2; skin 0.9','small')
        text(cx,618,'0.20 radial gap · 0.35 travel target','small')
        dim(cx-98,654,cx+98,654,'28',cx,646)
        line(cx-98,cy+168,cx-98,664);line(cx+98,cy+168,cx+98,664)
        dim(71,cy-168,71,cy+168,'48',51,cy+4)
        line(71,cy-168,cx-98,cy-168);line(71,cy+168,cx-98,cy+168)
        dim(347,cy-210,347,cy+168,'54 incl. bail',350,cy-221)
    else:
        rect(cx-34.3,cy+19*S-10.15,68.6,20.3,8,'#333d44')
        for x in [-3,0,3]:circle(cx+x*S,cy+19*S,5.95,'#cba458')
        for y in [-22.5,22.5]:circle(cx,cy-y*S,6,'#a4afb8')
        text(cx,cy-4,'A U R A','small')
        text(cx,597,'3 × Ø1.70 contacts; 3.0 pitch','small')
        text(cx,618,'X −3 / 0 / +3; Y −19','small')
        text(cx,648,'Retainers (0, ±22.5)','small')

cx=866
text(cx,158,'RIGHT SIDE')
rect(cx-35,cy-168,70,336,29,'#cbd3d9')
line(cx-1,cy-168,cx-1,cy+168,'line')
rect(cx+5,cy-19,10,44,5,'#a8b4be')
dim(cx-35,654,cx+35,654,'10',cx,646)
line(cx-35,cy+168,cx-35,664);line(cx+35,cy+168,cx+35,664)
text(cx,597,'Mechanical privacy slide','small')
text(cx,618,'0.11 shell seam','small')

cx=1180
text(cx,158,'PACKAGING / REAR OPEN')
rect(cx-89.6,cy-159.6,179.2,319.2,89.4,'#edf0ed')
rect(cx-84,cy-147,168,294,70,'#bcd4c6')
rect(cx-71.75,cy-77,143.5,196,10,'#e9cf8b',sw=1)
out.append(f'<path d="M{cx-85} {cy-11.95*S}H{cx+85}" stroke="#ab615e" stroke-width="2" stroke-dasharray="5 4"/>')
text(cx,cy-100,'ANTENNA CLEAR','small')
text(cx,cy+8,'CELL ALLOWANCE','small')
text(cx,cy+28,'20.5 × 28 × 3.3','small')
for x in [-3,0,3]:circle(cx+x*S,cy+19*S,5.95,'#cba458')
text(cx,597,'PCB 24 × 42 × 0.8; R10','small')
text(cx,618,'Inner 25.6 × 45.6; R12.8','small')
text(cx,648,'Minimum nominal XY gap ≈0.564','small')

out.append('<path d="M64 700H1376" stroke="#b4bdc7"/>')
text(64,737,'Z STACK / FULL-FACE ACTUATION','label','start')
bands=[('FACE',4.05,4.95,'#8998a7'),('FRONT SPACE',.65,4.05,'#e2e8ed'),('PCB',-.15,.65,'#729e88'),('GAP',-.45,-.15,'#fafbf9'),('CELL',-3.75,-.45,'#d5b96c'),('GAP',-4,-3.75,'#fafbf9'),('REAR',-5,-4,'#9aa7b3')]
x=65;y=777;factor=53
for label,a,b,color in bands:
    w=(b-a)*factor;rect(x,y,w,43,0,color,'#576676',.7)
    if w>25:text(x+w/2,y+27,label,'small')
    x+=w
text(65,849,'Front +Z → rear −Z; body outer +5.00 / −5.00','small','start')
text(65,871,'PCB: −0.15..+0.65. Cell: −3.75..−0.45. Rear floor: −4.00.','small','start')
text(700,782,'Face underside: +4.05 rest / +3.70 fully pressed.','label','start')
text(700,810,'Motor + film max top: +3.45 → 0.25 nominal pressed clearance.','small','start')
text(700,835,'Cell upper Y+11 leaves 0.95 to RF exclusion Y+11.95.','small','start')
text(700,859,'Cell lower Y−17 leaves 0.55 to contact carrier edge Y−17.55.','small','start')
text(700,883,'150mAh target; cell size, swelling and thermal behavior unqualified.','small','start')
out.append('<path d="M64 921H1376" stroke="#b4bdc7"/>')
text(64,952,'PRINTABLE FIT PROTOTYPE / physical assembly not tested','label','start')
text(64,978,'Use the supplied STL files at100% in millimetres. See PRINTING.md for process, tolerances, fasteners and assembly.','small','start')
text(64,1000,'Black face is the record paddle. Side switch is privacy. Acoustic boots, return gasket, switch linkage and contact termination require engineering.','small','start')
out.append('</svg>')
(root/'aura-mechanical-drawing.svg').write_text('\n'.join(out),encoding='utf-8')
