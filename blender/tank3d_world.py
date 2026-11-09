"""The open water behind the reef (shared by the tank scenes)."""
import bpy


def water_world():
    """Open water behind the reef: deep navy overhead, lighter toward the reef.
    The camera sees the full gradient; the light it casts is much dimmer, so
    the reef keeps dark crevices and strong shading."""
    w = bpy.data.worlds.new('tankwater')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    out = nt.nodes['World Output']
    bg = nt.nodes['Background']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    # (the camera sees directions only about 8 degrees above and below level)
    ramp.color_ramp.elements[0].position = 0.47
    ramp.color_ramp.elements[0].color = (0.025, 0.170, 0.360, 1)
    ramp.color_ramp.elements[1].position = 0.575
    ramp.color_ramp.elements[1].color = (0.002, 0.012, 0.065, 1)
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    dim = nt.nodes.new('ShaderNodeBackground')
    nt.links.new(ramp.outputs['Color'], dim.inputs['Color'])
    dim.inputs['Strength'].default_value = 0.16
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(dim.outputs['Background'], mix.inputs[1])
    nt.links.new(bg.outputs['Background'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
