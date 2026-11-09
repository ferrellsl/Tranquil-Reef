"""Shared Blender setup: render settings, underwater lighting, camera and
materials for the fish and the reef."""
import math

import bpy
from mathutils import Vector

WATER = (0.020, 0.105, 0.185)     # linear color of the open water


def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for b in list(block):
            block.remove(b)


def render_settings(samples, transparent=True):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for kind in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type == kind]
            if gpus:
                for d in prefs.devices:
                    d.use = d.type == kind
                sc.cycles.device = 'GPU'
                break
        except TypeError:
            continue
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.transparent_max_bounces = 24
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA' if transparent else 'RGB'
    sc.render.image_settings.color_depth = '8'
    sc.render.resolution_percentage = 100
    # Standard keeps the saturated reef-fish colors; AgX washed yellows out
    sc.view_settings.view_transform = 'Standard'
    try:
        sc.view_settings.look = 'High Contrast'
    except TypeError:
        pass


def sun(name, direction, strength, color, angle=2.0):
    ld = bpy.data.lights.new(name, 'SUN')
    ld.energy = strength
    ld.color = color
    ld.angle = math.radians(angle)
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.rotation_euler = Vector(direction).normalized().to_track_quat('-Z', 'Y').to_euler()
    return ob


def underwater_lights(world_strength=0.75):
    """Light from the surface above, blue water all around, a little warm
    bounce from the sand below."""
    w = bpy.data.worlds.new('water') if not bpy.context.scene.world else bpy.context.scene.world
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (0.05, 0.20, 0.32, 1)
    bg.inputs['Strength'].default_value = world_strength
    sun('key', (0.25, 0.45, -1.0), 4.2, (1.0, 0.98, 0.92), angle=4)
    sun('bounce', (-0.1, 0.3, 1.0), 0.55, (0.95, 0.88, 0.70), angle=30)
    sun('rim', (-0.3, -0.9, -0.5), 1.4, (0.65, 0.88, 1.0), angle=8)


def sprite_camera(center, ortho_width, res, pitch=0.0):
    cam = bpy.data.cameras.new('cam')
    cam.type = 'ORTHO'
    cam.ortho_scale = ortho_width
    ob = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(ob)
    d = 5.0
    ob.location = (center[0], -d * math.cos(pitch), center[1] + d * math.sin(pitch))
    ob.rotation_euler = (math.pi / 2 - pitch, 0, 0)
    bpy.context.scene.camera = ob
    bpy.context.scene.render.resolution_x = res[0]
    bpy.context.scene.render.resolution_y = res[1]
    return ob


# ------------------------------------------------------------ materials

def _nodes(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    return nt, out


def fish_body_material(name, tex, aspect, skin=None):
    skin = skin or {}
    mat = bpy.data.materials.new(name)
    nt, out = _nodes(mat)
    L = nt.links
    uvn = nt.nodes.new('ShaderNodeUVMap')
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = tex
    img.interpolation = 'Cubic'
    L.new(uvn.outputs['UV'], img.inputs['Vector'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(img.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = skin.get('rough', 0.42)
    bsdf.inputs['Coat Weight'].default_value = skin.get('coat', 0.35)
    bsdf.inputs['Coat Roughness'].default_value = 0.12
    bsdf.inputs['Subsurface Weight'].default_value = skin.get('sss', 0.10)
    bsdf.inputs['Specular IOR Level'].default_value = skin.get('spec', 0.5)
    bsdf.inputs['Subsurface Scale'].default_value = 0.01
    L.new(img.outputs['Color'], bsdf.inputs['Subsurface Radius'])
    # scales: a fine Voronoi relief across the skin
    mapn = nt.nodes.new('ShaderNodeMapping')
    bs = skin.get('bumpscale', 150.0)
    mapn.inputs['Scale'].default_value = (bs, bs * aspect, 1.0)
    L.new(uvn.outputs['UV'], mapn.inputs['Vector'])
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.feature = 'F1'
    L.new(mapn.outputs['Vector'], vor.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = skin.get('bump', 0.18)
    bump.inputs['Distance'].default_value = 0.0015
    L.new(vor.outputs['Distance'], bump.inputs['Height'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def fish_fin_material(name, tex, skin=None):
    skin = skin or {}
    mat = bpy.data.materials.new(name)
    nt, out = _nodes(mat)
    L = nt.links
    uvn = nt.nodes.new('ShaderNodeUVMap')
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = tex
    img.interpolation = 'Cubic'
    L.new(uvn.outputs['UV'], img.inputs['Vector'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(img.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.35
    bsdf.inputs['Coat Weight'].default_value = 0.2
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent')
    L.new(img.outputs['Color'], tr.inputs['Color'])
    m1 = nt.nodes.new('ShaderNodeMixShader')
    m1.inputs['Fac'].default_value = skin.get('translucency', 0.40)
    if 'rough' in skin:
        bsdf.inputs['Roughness'].default_value = skin['rough']
        bsdf.inputs['Coat Weight'].default_value = skin.get('coat', 0.2)
    L.new(bsdf.outputs['BSDF'], m1.inputs[1])
    L.new(tr.outputs['BSDF'], m1.inputs[2])
    tp = nt.nodes.new('ShaderNodeBsdfTransparent')
    m2 = nt.nodes.new('ShaderNodeMixShader')
    L.new(img.outputs['Alpha'], m2.inputs['Fac'])
    L.new(tp.outputs['BSDF'], m2.inputs[1])
    L.new(m1.outputs['Shader'], m2.inputs[2])
    L.new(m2.outputs['Shader'], out.inputs['Surface'])
    return mat


def flat_fin_material(name, color, alpha, dark=False):
    mat = bpy.data.materials.new(name)
    nt, out = _nodes(mat)
    L = nt.links
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*srgb_to_lin(color), 1)
    bsdf.inputs['Roughness'].default_value = 0.4
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent')
    tr.inputs['Color'].default_value = (*srgb_to_lin(color), 1)
    m1 = nt.nodes.new('ShaderNodeMixShader')
    m1.inputs['Fac'].default_value = 0.45
    L.new(bsdf.outputs['BSDF'], m1.inputs[1])
    L.new(tr.outputs['BSDF'], m1.inputs[2])
    tp = nt.nodes.new('ShaderNodeBsdfTransparent')
    m2 = nt.nodes.new('ShaderNodeMixShader')
    m2.inputs['Fac'].default_value = alpha
    L.new(tp.outputs['BSDF'], m2.inputs[1])
    L.new(m1.outputs['Shader'], m2.inputs[2])
    L.new(m2.outputs['Shader'], out.inputs['Surface'])
    return mat


def eye_material(name, iris):
    mat = bpy.data.materials.new(name)
    nt, out = _nodes(mat)
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['Object'], sep.inputs['Vector'])
    comb = nt.nodes.new('ShaderNodeCombineXYZ')
    L.new(sep.outputs['X'], comb.inputs['X'])
    L.new(sep.outputs['Z'], comb.inputs['Z'])
    ln = nt.nodes.new('ShaderNodeVectorMath')
    ln.operation = 'LENGTH'
    L.new(comb.outputs['Vector'], ln.inputs[0])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.0, (0.005, 0.005, 0.005, 1)
    el[1].position, el[1].color = 1.0, (0.02, 0.02, 0.02, 1)
    ic = srgb_to_lin(iris)
    for pos, col in ((0.42, (0.005, 0.005, 0.005)), (0.50, ic), (0.80, tuple(c * 0.55 for c in ic)), (0.92, (0.03, 0.03, 0.03))):
        e = el.new(pos)
        e.color = (*col, 1)
    L.new(ln.outputs['Value'], ramp.inputs['Fac'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.3
    bsdf.inputs['Coat Weight'].default_value = 1.0
    bsdf.inputs['Coat Roughness'].default_value = 0.03
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def srgb_to_lin(c):
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c)
