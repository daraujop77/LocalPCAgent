"""Blender integration skeleton. bpy/MCP automation is deferred to M5."""

from personal_ai.integration import SkeletonIntegration


class BlenderIntegration(SkeletonIntegration):
    provider_name = "blender"
    _capabilities = (
        "blender.status",
        "blender.inspect_scene",
        "blender.save_copy",
        "blender.execute_bpy",
        "blender.render.preview",
    )
