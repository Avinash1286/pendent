"""Preserve analytic capsule normals around boolean apertures, without changing solids."""
from math import hypot
from mathutils import Vector

def refine_capsule_normals(front,rear):
    profiles=[(front,[(.055,14),(3.45,13.975),(4.4,13.625),(4.88,13.125),(5,12.75)]),(rear,[(-5,13.25),(-4.8,13.6),(-4.2,13.925),(-3.2,14),(-.055,14)])]
    for ob,rings in profiles:
        def radius(z):
            if z<=rings[0][0]:return rings[0][1]
            if z>=rings[-1][0]:return rings[-1][1]
            for (z0,r0),(z1,r1) in zip(rings,rings[1:]):
                if z0<=z<=z1:return r0+(r1-r0)*(z-z0)/(z1-z0)
        normals=[(0,0,0)]*len(ob.data.loops)
        for poly in ob.data.polygons:
            for li in poly.loop_indices:
                p=ob.data.vertices[ob.data.loops[li].vertex_index].co*1000
                if p.y>24 and abs(poly.normal.x)>.98:
                    normals[li]=tuple(poly.normal);continue
                if abs(poly.normal.z)>.98:continue
                yy=max(abs(p.y)-10,0)*(1 if p.y>=0 else -1)
                rho=hypot(p.x,yy)
                if rho<1 or not rings[0][0]-.001<=p.z<=rings[-1][0]+.001:continue
                if abs(rho-radius(p.z))>.065:continue
                lo=max(rings[0][0],p.z-.18);hi=min(rings[-1][0],p.z+.18)
                slope=(radius(hi)-radius(lo))/(hi-lo) if hi>lo else 0
                n=Vector((p.x/rho,yy/rho,-slope)).normalized()
                if poly.normal.dot(n)>.55:normals[li]=tuple(n)
        ob.data.normals_split_custom_set(normals)
