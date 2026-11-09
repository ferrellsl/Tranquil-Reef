"""Shared by the photo-based models: a two-sided mesh from an inflate.py grid,
with the photo as its skin."""
import bmesh
import bpy
import numpy as np


def build(G, mirror=False):
    NAME = G['key']
    cols, rows = G['cols'], G['rows']
    asp = G['aspect']
    inside = np.array(G['inside'], bool).reshape(rows, cols)
    z = np.array(G['z'], np.float32).reshape(rows, cols)
    fin = np.array(G['fin'], np.float32).reshape(rows, cols)
    idx = -np.ones((2, rows, cols), int)
    verts, uvs, fins, rest = [], [], [], []
    for side, sgn in ((0, -1), (1, 1)):          # front faces the camera (at -y)
        for j in range(rows):
            for i in range(cols):
                if not inside[j, i]:
                    continue
                u = i / (cols - 1)
                if mirror:
                    u = 1 - u
                y = (0.5 - j / (rows - 1)) * asp
                idx[side, j, i] = len(verts)
                rest.append((u, sgn * float(z[j, i]), y))
                verts.append((u, sgn * float(z[j, i]), y))
                uvs.append((u, 1 - j / (rows - 1)))
                fins.append(float(fin[j, i]))
    faces = []
    for j in range(rows - 1):
        for i in range(cols - 1):
            q = [idx[0, j, i], idx[0, j, i + 1], idx[0, j + 1, i + 1], idx[0, j + 1, i]]
            if min(q) < 0:
                continue
            b = [idx[1, j, i], idx[1, j, i + 1], idx[1, j + 1, i + 1], idx[1, j + 1, i]]
            if mirror:      # mirrored: keep the faces pointing outward
                faces.append((q[0], q[1], q[2], q[3]))
                faces.append((b[0], b[3], b[2], b[1]))
            else:
                faces.append((q[0], q[3], q[2], q[1]))
                faces.append((b[0], b[1], b[2], b[3]))
    me = bpy.data.meshes.new(NAME)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    at = me.attributes.new('fin', 'FLOAT', 'POINT')
    at.data.foreach_set('value', fins)
    me.shade_smooth()
    ob = bpy.data.objects.new(NAME, me)
    bpy.context.collection.objects.link(ob)
    sub = ob.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1
    # seal front and back along the edge, then read the rest shape back
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(ob.data)
    bm.free()
    n = len(ob.data.vertices)
    co = np.zeros(n * 3, np.float32)
    ob.data.vertices.foreach_get('co', co)
    fv = np.zeros(n, np.float32)
    ob.data.attributes['fin'].data.foreach_get('value', fv)
    return ob, co.reshape(n, 3), fv


def material(tex_path):
    mat = bpy.data.materials.new('skin')
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    L = nt.links
    uvn = nt.nodes.new('ShaderNodeUVMap')
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(tex_path)
    img.image.alpha_mode = 'STRAIGHT'
    img.interpolation = 'Cubic'
    L.new(uvn.outputs['UV'], img.inputs['Vector'])
    attr = nt.nodes.new('ShaderNodeAttribute')
    attr.attribute_name = 'fin'
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(img.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.45
    # wet sheen on the body, less on the fins
    inv = nt.nodes.new('ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    L.new(attr.outputs['Fac'], inv.inputs[1])
    coat = nt.nodes.new('ShaderNodeMath')
    coat.operation = 'MULTIPLY'
    coat.inputs[1].default_value = 0.30
    L.new(inv.outputs['Value'], coat.inputs[0])
    L.new(coat.outputs['Value'], bsdf.inputs['Coat Weight'])
    bsdf.inputs['Coat Roughness'].default_value = 0.15
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    # fins let light through
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent')
    L.new(img.outputs['Color'], tr.inputs['Color'])
    fmix = nt.nodes.new('ShaderNodeMath')
    fmix.operation = 'MULTIPLY'
    fmix.inputs[1].default_value = 0.45
    L.new(attr.outputs['Fac'], fmix.inputs[0])
    m1 = nt.nodes.new('ShaderNodeMixShader')
    L.new(fmix.outputs['Value'], m1.inputs['Fac'])
    L.new(bsdf.outputs['BSDF'], m1.inputs[1])
    L.new(tr.outputs['BSDF'], m1.inputs[2])
    tp = nt.nodes.new('ShaderNodeBsdfTransparent')
    m2 = nt.nodes.new('ShaderNodeMixShader')
    L.new(img.outputs['Alpha'], m2.inputs['Fac'])
    L.new(tp.outputs['BSDF'], m2.inputs[1])
    L.new(m1.outputs['Shader'], m2.inputs[2])
    L.new(m2.outputs['Shader'], out.inputs['Surface'])
    return mat


