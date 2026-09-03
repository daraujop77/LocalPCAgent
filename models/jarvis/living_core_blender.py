"""Live parametric energy core for Blender 4.2+.

This is a Blender scene generator, not a video or image-sequence player.  It
creates a dedicated ``LivingCore`` collection and a ``LivingCore_CTRL`` Empty
whose custom properties drive the animation at run time:

* ``energy``: 0.0 .. 1.2, a persistent driver input
* ``shock``: 0.0 .. 1.0, a persistent manual shock baseline
* ``mode``: ``idle``, ``alert`` or ``overload``

The visual brief and original paste-ready script were supplied in the Drive
folder linked in the project request.  This implementation keeps that
interface while correcting the Blender-version-sensitive parts and filling in
the requested dotted rings, orbital dust, irregular halo, and shockwave.

Run from Blender's Text Editor, or headlessly from a shell::

    blender --background --python integrations/blender/living_core_blender.py

The script is intentionally safe to run repeatedly. It rebuilds only its
owned scene/collection and removes its own tagged frame handler; it does not
remove handlers belonging to other add-ons or alter the user's other scenes.
"""

import math

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

bl_info = {
    "name": "Personal AI Living Core",
    "author": "Personal AI Platform",
    "version": (3, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Living Core",
    "description": "Live parametric energy core with persistent Blender drivers",
    "category": "3D View",
}

COLLECTION_NAME = "LivingCore"
CONTROL_NAME = "LivingCore_CTRL"
SCENE_NAME = "LivingCore_Scene"
SCRIPT_VERSION = "3.1.0"
HANDLER_TAG = "_living_core_handler_v3"

CORE_CYAN = (0.306, 0.784, 1.0, 1.0)  # #4EC8FF
EDGE_BLUE = (0.039, 0.165, 0.290, 1.0)  # #0A2A4A
WHITE_CYAN = (0.820, 0.970, 1.0, 1.0)

MODES = {
    "idle": {"energy": 0.34, "speed": 1.00},
    "alert": {"energy": 0.64, "speed": 1.55},
    "overload": {"energy": 1.00, "speed": 2.35},
}

# radius, bevel/torus width, spin direction and rate, dotted, base emission
RING_DEFS = (
    (0.30, 0.011, 0.72, False, 5.0),
    (0.40, 0.008, -0.56, True, 4.2),
    (0.50, 0.015, 0.43, False, 5.8),
    (0.60, 0.009, -0.34, True, 4.8),
    (0.72, 0.013, 0.26, False, 4.5),
    (0.83, 0.007, -0.20, True, 3.8),
)

# rx, ry, initial phase, speed multiplier, z offset, material strength
ORB_DEFS = (
    (0.42, 0.42, 0.15, 1.13, 0.015, 8.5),
    (0.52, 0.52, 1.55, -0.78, -0.015, 7.2),
    (0.62, 0.62, 2.65, 0.61, 0.020, 6.5),
    (0.72, 0.72, 3.64, -0.49, -0.020, 7.7),
    (0.80, 0.80, 4.46, 0.38, 0.010, 5.9),
    (0.54, 0.54, 5.16, -0.69, -0.010, 6.8),
    (0.78, 0.52, 5.80, 0.31, 0.018, 5.2),
    (0.44, 0.76, 0.82, 0.54, -0.018, 6.1),
)

# dust entries are generated into a small number of meshes, keeping the scene
# comfortably below the requested 50k vertex budget.
DUST_DEFS = tuple(
    (
        0.34 + (index % 6) * 0.085,
        0.30 + ((index * 3) % 7) * 0.070,
        (index * 0.91) % (math.tau),
        (-1.0 if index % 3 == 0 else 1.0) * (0.28 + (index % 5) * 0.07),
        0.004 + (index % 4) * 0.0015,
    )
    for index in range(24)
)

LEGACY_GENERATED_OBJECT_NAMES = {
    "LivingCore_CTRL",
    "LC_Core",
    "LC_CoreGlow",
    "LC_Spokes",
    "LC_Halo",
    "LC_Halo_Wisp",
    "LC_Shockwave",
    "LC_Camera",
    *(f"LC_Ring_{index}" for index in range(6)),
    *(f"LC_Orb_{index}" for index in range(8)),
    *(f"LC_Dust_{index:02d}" for index in range(24)),
}


def _remove_owned_handlers() -> None:
    """Remove only handlers installed by this script."""

    for handler in list(bpy.app.handlers.frame_change_pre):
        if any(getattr(handler, tag, False) for tag in (HANDLER_TAG, "_living_core_handler_v2")):
            bpy.app.handlers.frame_change_pre.remove(handler)


def _is_generated_object(obj: bpy.types.Object) -> bool:
    return obj.get("lc_generated") is True or obj.name in LEGACY_GENERATED_OBJECT_NAMES


def _material_has_object_reference(material: bpy.types.Material) -> bool:
    for obj in bpy.data.objects:
        if not hasattr(obj.data, "materials"):
            continue
        if any(slot.name == material.name for slot in obj.data.materials):
            return True
    return False


def _purge_previous_build(scene: bpy.types.Scene | None = None) -> None:
    """Delete generated content without touching unrelated user objects."""

    _remove_owned_handlers()
    collection_names = {COLLECTION_NAME}
    if scene is not None:
        stored_name = scene.get("lc_collection_name")
        if isinstance(stored_name, str) and stored_name:
            collection_names.add(stored_name)
    for collection_name in collection_names:
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            continue
        owned = collection.get("lc_generated") is True
        legacy_only = len(collection.objects) > 0 and all(
            _is_generated_object(obj) for obj in collection.objects
        )
        if not owned and not legacy_only:
            continue
        for obj in list(collection.objects):
            if _is_generated_object(obj):
                bpy.data.objects.remove(obj, do_unlink=True)
        if len(collection.objects) == 0:
            bpy.data.collections.remove(collection)

    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras):
        for datablock in list(datablocks):
            if datablock.get("lc_generated") and datablock.users == 0:
                datablocks.remove(datablock, do_unlink=True)

    for material in list(bpy.data.materials):
        generated_or_legacy = material.get("lc_generated") or material.name.startswith("LC_")
        if generated_or_legacy and (
            material.users == 0 or not _material_has_object_reference(material)
        ):
            bpy.data.materials.remove(material, do_unlink=True)


def _ensure_scene() -> bpy.types.Scene:
    """Return an owned showcase scene without overwriting a user scene."""

    global COLLECTION_NAME, SCENE_NAME
    scene = bpy.data.scenes.get(SCENE_NAME)
    if scene is not None and scene.get("lc_generated") is not True:
        suffix = 1
        base_name = SCENE_NAME
        while bpy.data.scenes.get(f"{base_name}_{suffix}") is not None:
            suffix += 1
        SCENE_NAME = f"{base_name}_{suffix}"
        scene = None
    if scene is None:
        scene = bpy.data.scenes.new(SCENE_NAME)
    stored_collection_name = scene.get("lc_collection_name")
    if isinstance(stored_collection_name, str) and stored_collection_name:
        if bpy.data.collections.get(stored_collection_name) is not None:
            COLLECTION_NAME = stored_collection_name
    scene["lc_generated"] = True
    scene["lc_script_version"] = SCRIPT_VERSION
    scene["lc_purpose"] = "isolated live energy-core showcase"
    return scene


def _ensure_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    global COLLECTION_NAME

    existing = bpy.data.collections.get(COLLECTION_NAME)
    if existing is not None:
        # A non-empty collection that survived cleanup contains user content;
        # keep it intact and reserve a new generated name beside it.
        contains_user_objects = any(not _is_generated_object(obj) for obj in existing.objects)
        if existing.get("lc_generated") is not True or contains_user_objects:
            suffix = 1
            base_name = COLLECTION_NAME
            while bpy.data.collections.get(f"{base_name}_{suffix}") is not None:
                suffix += 1
            COLLECTION_NAME = f"{base_name}_{suffix}"
            existing = None
    if existing is None:
        existing = bpy.data.collections.new(COLLECTION_NAME)
    if existing.name not in {item.name for item in scene.collection.children}:
        scene.collection.children.link(existing)
    collection = existing
    collection["lc_generated"] = True
    collection["lc_script_version"] = SCRIPT_VERSION
    collection["lc_vertex_budget"] = "under 50k by construction"
    return collection


def _link(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    """Move an object into the generated collection without losing datablocks."""

    for owner in list(obj.users_collection):
        if owner != collection:
            owner.objects.unlink(obj)
    if not any(item is obj for item in collection.objects):
        collection.objects.link(obj)


def _parent(obj: bpy.types.Object, control: bpy.types.Object) -> None:
    obj.parent = control
    obj["lc_generated"] = True


def _set_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    if hasattr(obj.data, "materials"):
        obj.data.materials.clear()
        obj.data.materials.append(material)


def _emission_material(
    name: str,
    color: tuple[float, float, float, float],
    strength: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color
    material["lc_material"] = "emission_only"
    material["lc_generated"] = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.name = "LC_Emission"
    emission.label = "Emission only"
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "LC_MaterialOutput"
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _copy_material(material: bpy.types.Material, suffix: str) -> bpy.types.Material:
    copy = material.copy()
    copy.name = f"{material.name}_{suffix}"
    copy["lc_generated"] = True
    return copy


def _add_driver(
    owner,
    data_path: str,
    expression: str,
    variables: tuple[tuple[str, bpy.types.ID, str], ...],
    *,
    index: int | None = None,
) -> None:
    """Attach a version-stable scripted driver to an object or node socket."""

    if index is None:
        fcurve = owner.driver_add(data_path)
    else:
        fcurve = owner.driver_add(data_path, index)
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    driver.expression = expression
    for name, target_id, target_path in variables:
        variable = driver.variables.new()
        variable.name = name
        variable.type = "SINGLE_PROP"
        variable.targets[0].id = target_id
        variable.targets[0].data_path = target_path


def _driver_variables(
    control: bpy.types.Object,
    scene: bpy.types.Scene,
    *,
    owner: bpy.types.Object | None = None,
) -> tuple[tuple[str, bpy.types.ID, str], ...]:
    variables = [
        ("energy", control, '["energy"]'),
        ("shock", control, '["shock"]'),
        ("mode_speed", control, '["_mode_speed"]'),
        ("speed_mul", control, '["speed_mul"]'),
        # ``frame`` is a Blender driver builtin. DriverTarget.id is Object-
        # typed on Blender 5.x, so the portable FPS input is mirrored on the
        # controller rather than targeting a Scene ID directly.
        ("fps", control, '["fps"]'),
        ("start_frame", control, '["_start_frame"]'),
        ("pulse_strength", control, '["_pulse_strength"]'),
        ("pulse_frame", control, '["_pulse_frame"]'),
    ]
    if owner is not None:
        owner_properties = (
            ("base", "base_strength"),
            ("initial", "initial_angle"),
            ("spin", "spin"),
            ("rx", "rx"),
            ("ry", "ry"),
            ("phase0", "phase0"),
            ("orb_speed", "orb_speed"),
            ("z_offset", "z_offset"),
            ("halo_rate", "halo_rate"),
            ("duration", "duration"),
        )
        for variable_name, property_name in owner_properties:
            if property_name in owner:
                variables.append((variable_name, owner, f'["{property_name}"]'))
    return tuple(variables)


def _add_emission_driver(
    material: bpy.types.Material,
    expression: str,
    variables: tuple[tuple[str, bpy.types.ID, str], ...],
) -> None:
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeEmission":
            _add_driver(node.inputs["Strength"], "default_value", expression, variables)
            return


def _set_emission_strength(obj: bpy.types.Object, strength: float) -> None:
    material = obj.active_material
    if material is None or material.node_tree is None:
        return
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeEmission" and "Strength" in node.inputs:
            node.inputs["Strength"].default_value = max(0.0, float(strength))
            return


def _tag(obj: bpy.types.Object, role: str) -> bpy.types.Object:
    obj["lc_role"] = role
    obj["lc_script_version"] = SCRIPT_VERSION
    if obj.data is not None:
        obj.data["lc_generated"] = True
    return obj


def _smooth_mesh(obj: bpy.types.Object) -> None:
    if hasattr(obj.data, "polygons"):
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def _make_control(collection: bpy.types.Collection, scene: bpy.types.Scene) -> bpy.types.Object:
    control = bpy.data.objects.new(CONTROL_NAME, None)
    control.empty_display_type = "PLAIN_AXES"
    control.empty_display_size = 0.28
    _link(control, collection)
    control["energy"] = MODES["idle"]["energy"]
    control["shock"] = 0.0
    control["mode"] = "idle"
    control["speed_mul"] = 1.0
    control["fps"] = max(float(scene.render.fps), 1.0)
    control["_mode_speed"] = MODES["idle"]["speed"]
    control["_energy_smooth"] = MODES["idle"]["energy"]
    control["_time"] = 0.0
    control["_last_frame"] = scene.frame_current
    control["_start_frame"] = scene.frame_start
    control["_pulse_strength"] = 0.0
    control["_pulse_frame"] = -1.0
    control["lc_script_version"] = SCRIPT_VERSION

    id_properties_ui = getattr(control, "id_properties_ui", None)
    if callable(id_properties_ui):
        energy_ui = id_properties_ui("energy")
        energy_ui.update(
            min=0.0,
            max=1.2,
            soft_min=0.0,
            soft_max=1.2,
            default=MODES["idle"]["energy"],
            description="Smoothed energy target for the live core",
        )
        shock_ui = id_properties_ui("shock")
        shock_ui.update(
            min=0.0,
            max=1.0,
            soft_min=0.0,
            soft_max=1.0,
            default=0.0,
            description="Manual shock baseline; Pulse uses the private persistent pulse state",
        )
        mode_ui = id_properties_ui("mode")
        mode_ui.update(
            default="idle",
            description="Current mode label; use the Living Core panel buttons for presets",
        )
    return _tag(control, "controller")


def _prepare_operator_context() -> tuple[
    bpy.types.Object | None, tuple[bpy.types.Object, ...], str
]:
    """Put mesh operators in Object Mode without losing the user's selection."""

    active = bpy.context.view_layer.objects.active
    selected = tuple(bpy.context.selected_objects)
    mode = active.mode if active is not None else "OBJECT"
    if active is not None and mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in selected:
        obj.select_set(False)
    return active, selected, mode


def _restore_operator_context(
    state: tuple[bpy.types.Object | None, tuple[bpy.types.Object, ...], str],
) -> None:
    active, selected, mode = state
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in selected:
        try:
            obj_name = obj.name
        except ReferenceError:
            continue
        if bpy.data.objects.get(obj_name) is not None and bpy.context.view_layer.objects.get(
            obj_name
        ):
            obj.select_set(True)
    try:
        active_name = active.name if active is not None else None
    except ReferenceError:
        active_name = None
    if active_name is not None and bpy.context.view_layer.objects.get(active_name):
        bpy.context.view_layer.objects.active = active
        if mode != "OBJECT":
            active.select_set(True)
            bpy.ops.object.mode_set(mode=mode)


def _new_uv_sphere(
    name: str,
    radius: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    control: bpy.types.Object,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32,
        ring_count=16,
        radius=radius,
        location=(0.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    _link(obj, collection)
    _parent(obj, control)
    _smooth_mesh(obj)
    _set_material(obj, material)
    return _tag(obj, "orbital_sphere")


def _make_curve(
    name: str,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    *,
    bevel_depth: float,
    bevel_resolution: int = 1,
) -> tuple[bpy.types.Object, bpy.types.Curve]:
    data = bpy.data.curves.new(f"{name}_DATA", type="CURVE")
    data.dimensions = "3D"
    data.resolution_u = 1
    data.bevel_depth = bevel_depth
    data.bevel_resolution = bevel_resolution
    obj = bpy.data.objects.new(name, data)
    _link(obj, collection)
    _parent(obj, control)
    _set_material(obj, material)
    return _tag(obj, "curve"), data


def _make_core(
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    core_material: bpy.types.Material,
    glow_material: bpy.types.Material,
) -> tuple[bpy.types.Object, bpy.types.Object]:
    core = _new_uv_sphere("LC_Core", 0.235, core_material, collection, control)
    glow = _new_uv_sphere("LC_CoreGlow", 0.30, glow_material, collection, control)
    glow.scale = (1.12, 1.12, 1.12)

    spokes, data = _make_curve(
        "LC_Spokes",
        core_material,
        collection,
        control,
        bevel_depth=0.006,
        bevel_resolution=1,
    )
    for index in range(12):
        angle = math.tau * index / 12.0
        spline = data.splines.new("POLY")
        spline.points.add(1)
        spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
        spline.points[1].co = (0.37 * math.cos(angle), 0.37 * math.sin(angle), 0.0, 1.0)
    spokes["lc_role"] = "radial_spokes"
    return core, glow


def _make_solid_ring(
    name: str,
    radius: float,
    width: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    control: bpy.types.Object,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=radius,
        minor_radius=width,
        major_segments=96,
        minor_segments=8,
        location=(0.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    _link(obj, collection)
    _parent(obj, control)
    _smooth_mesh(obj)
    _set_material(obj, material)
    return _tag(obj, "solid_ring")


def _make_dotted_ring(
    name: str,
    radius: float,
    width: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    control: bpy.types.Object,
) -> bpy.types.Object:
    # Separate short curve splines are actual geometry, rather than a texture
    # trick, so the dotted ring remains crisp at any render resolution.
    obj, data = _make_curve(
        name,
        material,
        collection,
        control,
        bevel_depth=width * 0.82,
        bevel_resolution=1,
    )
    dot_count = 48
    visible_arc = math.tau / dot_count * 0.34
    for index in range(dot_count):
        start = math.tau * index / dot_count
        end = start + visible_arc
        spline = data.splines.new("POLY")
        spline.points.add(1)
        spline.points[0].co = (radius * math.cos(start), radius * math.sin(start), 0.0, 1.0)
        spline.points[1].co = (radius * math.cos(end), radius * math.sin(end), 0.0, 1.0)
    obj["lc_role"] = "dotted_ring"
    obj["dot_count"] = dot_count
    return obj


def _make_rings(
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    core_material: bpy.types.Material,
    edge_material: bpy.types.Material,
) -> list[bpy.types.Object]:
    rings = []
    for index, (radius, width, spin, dotted, strength) in enumerate(RING_DEFS):
        source_material = core_material if index % 2 == 0 else edge_material
        material = _copy_material(source_material, f"Ring{index}")
        name = f"LC_Ring_{index}"
        if dotted:
            ring = _make_dotted_ring(name, radius, width, material, collection, control)
        else:
            ring = _make_solid_ring(name, radius, width, material, collection, control)
        ring["radius"] = radius
        ring["spin"] = spin
        ring["dotted"] = dotted
        ring["base_strength"] = strength
        ring["_angle"] = (index % 2) * 0.15
        ring["initial_angle"] = ring["_angle"]
        rings.append(ring)
    return rings


def _make_orbs(
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    orb_material: bpy.types.Material,
) -> list[bpy.types.Object]:
    orbs = []
    for index, (rx, ry, phase, speed, z_offset, strength) in enumerate(ORB_DEFS):
        material = _copy_material(orb_material, f"Orb{index}")
        orb = _new_uv_sphere(
            f"LC_Orb_{index}",
            0.025 + (index % 3) * 0.006,
            material,
            collection,
            control,
        )
        orb["lc_role"] = "orbital_orb"
        orb["rx"] = rx
        orb["ry"] = ry
        orb["phase"] = phase
        orb["phase0"] = phase
        orb["orb_speed"] = speed
        orb["z_offset"] = z_offset
        orb["base_strength"] = strength
        orb.location = (
            rx * math.cos(phase),
            ry * math.sin(phase),
            z_offset + math.sin(phase * 2.0) * 0.02,
        )
        orbs.append(orb)
    return orbs


def _make_dust(
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    dust_material: bpy.types.Material,
) -> list[bpy.types.Object]:
    dust = []
    for index, (rx, ry, phase, speed, size) in enumerate(DUST_DEFS):
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=1,
            radius=size,
            location=(0.0, 0.0, 0.0),
        )
        particle = bpy.context.object
        particle.name = f"LC_Dust_{index:02d}"
        _link(particle, collection)
        _parent(particle, control)
        _set_material(particle, dust_material)
        particle["lc_role"] = "orbital_dust"
        particle["rx"] = rx
        particle["ry"] = ry
        particle["phase"] = phase
        particle["phase0"] = phase
        particle["orb_speed"] = speed
        particle["z_offset"] = (index % 5 - 2) * 0.008
        particle.location = (
            rx * math.cos(phase),
            ry * math.sin(phase),
            particle["z_offset"],
        )
        dust.append(particle)
    return dust


def _make_irregular_halo(
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    halo_material: bpy.types.Material,
) -> tuple[bpy.types.Object, bpy.types.Object]:
    halo, data = _make_curve(
        "LC_Halo",
        halo_material,
        collection,
        control,
        bevel_depth=0.013,
        bevel_resolution=2,
    )
    sample_count = 96
    spline = data.splines.new("POLY")
    spline.points.add(sample_count - 1)
    for index in range(sample_count):
        angle = math.tau * index / sample_count
        radius = (
            0.94
            + 0.031 * math.sin(angle * 7.0 + 0.4)
            + 0.020 * math.sin(angle * 13.0 - 0.9)
            + 0.013 * math.cos(angle * 21.0)
        )
        spline.points[index].co = (
            radius * math.cos(angle),
            radius * math.sin(angle),
            0.0,
            1.0,
        )
    spline.use_cyclic_u = True
    halo["lc_role"] = "irregular_outer_halo"
    halo["noise_source"] = "deterministic_sine_layers"

    wisp, wisp_data = _make_curve(
        "LC_Halo_Wisp",
        halo_material,
        collection,
        control,
        bevel_depth=0.006,
        bevel_resolution=1,
    )
    wisp_spline = wisp_data.splines.new("POLY")
    wisp_spline.points.add(sample_count - 1)
    for index in range(sample_count):
        angle = math.tau * index / sample_count
        radius = 1.01 + 0.055 * math.sin(angle * 5.0 - 1.1)
        wisp_spline.points[index].co = (
            radius * math.cos(angle),
            radius * math.sin(angle),
            0.0,
            1.0,
        )
    wisp_spline.use_cyclic_u = True
    wisp["lc_role"] = "halo_wisp"
    halo["initial_angle"] = 0.0
    halo["halo_rate"] = -0.027
    wisp["initial_angle"] = 0.0
    wisp["halo_rate"] = 0.05
    return halo, wisp


def _make_shockwave(
    collection: bpy.types.Collection,
    control: bpy.types.Object,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.34,
        minor_radius=0.008,
        major_segments=96,
        minor_segments=6,
        location=(0.0, 0.0, 0.0),
    )
    wave = bpy.context.object
    wave.name = "LC_Shockwave"
    _link(wave, collection)
    _parent(wave, control)
    _smooth_mesh(wave)
    _set_material(wave, material)
    wave.hide_viewport = True
    wave.hide_render = True
    wave["lc_role"] = "shockwave"
    wave["base_strength"] = 11.0
    wave["duration"] = 0.95
    return wave


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _make_camera(scene: bpy.types.Scene, collection: bpy.types.Collection) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("LC_Camera_DATA")
    camera = bpy.data.objects.new("LC_Camera", camera_data)
    _link(camera, collection)
    camera.location = (0.06, -0.10, 3.35)
    camera_data.lens = 52.0
    camera_data.clip_start = 0.01
    camera_data.clip_end = 100.0
    _look_at(camera, Vector((0.0, 0.0, 0.0)))
    scene.camera = camera
    return _tag(camera, "camera")


def _activate_scene(scene: bpy.types.Scene, control: bpy.types.Object) -> None:
    window = getattr(bpy.context, "window", None)
    if window is None:
        return
    try:
        window.scene = scene
        for selected in list(bpy.context.selected_objects):
            selected.select_set(False)
        control.select_set(True)
        bpy.context.view_layer.objects.active = control
    except (AttributeError, RuntimeError):
        # Background validation has no window, and unusual editor contexts can
        # reject selection changes. The saved scene and drivers remain valid.
        return


def _pulse_signal_expression() -> str:
    return "max(shock,pulse_strength*exp(-max(0.0,frame-pulse_frame)/max(fps,1.0)*2.2))"


def _motion_expression() -> str:
    elapsed = "max(0.0,frame-start_frame)/max(fps,1.0)"
    return f"mode_speed*(0.7+energy*0.8)*speed_mul*{elapsed}"


def _install_persistent_drivers(
    scene: bpy.types.Scene,
    control: bpy.types.Object,
    white_material: bpy.types.Material,
    glow_material: bpy.types.Material,
    halo_material: bpy.types.Material,
    shock_material: bpy.types.Material,
) -> None:
    """Make the saved .blend animate without relying on this Python session.

    The frame handler remains useful for smoothing diagnostics and interactive
    sessions, but all visible motion and pulse envelopes are Blender drivers.
    Drivers are stored in the .blend and therefore survive reopening it.
    """

    variables = _driver_variables(control, scene)
    motion = _motion_expression()
    pulse = _pulse_signal_expression()
    core_factor = f"1.0+sin(({motion})*0.7)*0.015+energy*0.04+({pulse})*0.06"
    glow_factor = f"1.12*(1.0+0.025*energy+({pulse})*0.08)"

    for name in ("LC_Core", "LC_CoreGlow"):
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        factor = core_factor if name == "LC_Core" else glow_factor
        for axis in range(3):
            _add_driver(obj, "scale", factor, variables, index=axis)

    _add_emission_driver(
        white_material,
        f"18.0*(0.68+energy*0.82+({pulse})*1.55)",
        variables,
    )
    _add_emission_driver(
        glow_material,
        f"2.8*(0.72+energy*0.65+({pulse})*1.5)",
        variables,
    )

    for ring in _find_generated("solid_ring") + _find_generated("dotted_ring"):
        ring_variables = _driver_variables(control, scene, owner=ring)
        _add_driver(
            ring,
            "rotation_euler",
            f"initial+spin*({motion})",
            ring_variables,
            index=2,
        )
        material = ring.active_material
        if material is not None:
            _add_emission_driver(
                material,
                f"base*(0.68+energy*0.82+({pulse})*1.55)",
                ring_variables,
            )

    for orb in _find_generated("orbital_orb"):
        orb_variables = _driver_variables(control, scene, owner=orb)
        phase = f"phase0+orb_speed*({motion})"
        _add_driver(orb, "location", f"rx*cos({phase})", orb_variables, index=0)
        _add_driver(orb, "location", f"ry*sin({phase})", orb_variables, index=1)
        _add_driver(
            orb,
            "location",
            f"z_offset+sin(({phase})*2.0)*0.02",
            orb_variables,
            index=2,
        )
        material = orb.active_material
        if material is not None:
            _add_emission_driver(
                material,
                f"base*(0.72+energy*0.65+({pulse})*1.5)",
                orb_variables,
            )

    for particle in _find_generated("orbital_dust"):
        particle_variables = _driver_variables(control, scene, owner=particle)
        phase = f"phase0+orb_speed*({motion})"
        _add_driver(
            particle,
            "location",
            f"rx*cos({phase})",
            particle_variables,
            index=0,
        )
        _add_driver(
            particle,
            "location",
            f"ry*sin({phase})",
            particle_variables,
            index=1,
        )
        _add_driver(
            particle,
            "location",
            f"z_offset+sin(({phase})*2.0)*0.02",
            particle_variables,
            index=2,
        )

    halo_scale = f"1.0+energy*0.045+({pulse})*0.18"
    for halo in _find_generated("irregular_outer_halo") + _find_generated("halo_wisp"):
        halo_variables = _driver_variables(control, scene, owner=halo)
        for axis in (0, 1):
            _add_driver(halo, "scale", halo_scale, halo_variables, index=axis)
        _add_driver(
            halo,
            "rotation_euler",
            f"initial+halo_rate*({motion})",
            halo_variables,
            index=2,
        )
    _add_emission_driver(
        halo_material,
        f"1.3+energy*2.4+({pulse})*7.0",
        variables,
    )

    shockwave = bpy.data.objects.get("LC_Shockwave")
    if shockwave is not None:
        wave_variables = _driver_variables(control, scene, owner=shockwave)
        progress = "min(1.0,max(0.0,frame-pulse_frame)/(max(fps,1.0)*max(duration,0.01)))"
        for axis in (0, 1, 2):
            _add_driver(shockwave, "scale", f"1.0+({progress})*2.9", wave_variables, index=axis)
        hide = (
            "min(1.0,max(0.0,1.0-pulse_strength)+max(0.0,"
            "frame-(pulse_frame+max(fps,1.0)*max(duration,0.01))))"
        )
        _add_driver(shockwave, "hide_viewport", hide, wave_variables)
        _add_driver(shockwave, "hide_render", hide, wave_variables)
        _add_emission_driver(
            shock_material,
            f"base*pulse_strength*max(0.0,1.0-({progress}))**1.5",
            wave_variables,
        )

    scene["lc_animation"] = "blender_drivers_persistent"


def _set_first_supported_engine(scene: bpy.types.Scene) -> str:
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = engine
            return engine
        except (TypeError, ValueError):
            continue
    return str(scene.render.engine)


def _ensure_compositor_bloom(scene: bpy.types.Scene) -> bool:
    """Use native Eevee bloom when available, otherwise wire compositor glare."""

    eevee = getattr(scene, "eevee", None)
    if eevee is not None and hasattr(eevee, "use_bloom"):
        try:
            eevee.use_bloom = True
            return True
        except (AttributeError, TypeError):
            pass

    # Blender 4.2 exposes the compositor as ``scene.node_tree``. Blender 5.2
    # keeps ``use_nodes`` for compatibility but moves the actual tree to
    # ``scene.compositing_node_group`` and uses a node-group output instead of
    # the removed Composite node. Resolve both surfaces without relying on a
    # version number, because patched builds can backport either API.
    tree = getattr(scene, "node_tree", None)
    legacy_compositor = tree is not None
    if tree is None:
        tree = getattr(scene, "compositing_node_group", None)
    if tree is None:
        if hasattr(scene, "compositing_node_group"):
            tree = bpy.data.node_groups.new("LivingCore_Compositor", "CompositorNodeTree")
            scene.compositing_node_group = tree
        elif hasattr(scene, "use_nodes"):
            scene.use_nodes = True
            tree = scene.node_tree
        else:
            return False
    tree["lc_generated"] = True
    render_layers = tree.nodes.get("Render Layers")
    if render_layers is None:
        render_layers = tree.nodes.new("CompositorNodeRLayers")
        render_layers.name = "Render Layers"
    try:
        render_layers.scene = scene
    except (AttributeError, TypeError):
        pass
    if legacy_compositor:
        composite = tree.nodes.get("Composite")
        if composite is None:
            composite = tree.nodes.new("CompositorNodeComposite")
            composite.name = "Composite"
        composite_input = composite.inputs.get("Image")
    else:
        output_socket = next(
            (
                item
                for item in tree.interface.items_tree
                if item.item_type == "SOCKET" and item.in_out == "OUTPUT" and item.name == "Image"
            ),
            None,
        )
        if output_socket is None:
            tree.interface.new_socket(
                name="Image",
                in_out="OUTPUT",
                socket_type="NodeSocketColor",
            )
        composite = tree.nodes.get("LC_CompositorOutput")
        if composite is None:
            composite = tree.nodes.new("NodeGroupOutput")
            composite.name = "LC_CompositorOutput"
        composite_input = composite.inputs.get("Image")
        if composite_input is None and composite.inputs:
            composite_input = composite.inputs[0]
    glare = tree.nodes.get("LC_Bloom")
    if glare is None:
        glare = tree.nodes.new("CompositorNodeGlare")
        glare.name = "LC_Bloom"
        glare.label = "Living Core bloom fallback"
    if hasattr(glare, "glare_type"):
        # Blender 4.2's legacy compositor exposes glare settings as node
        # properties.
        glare.glare_type = "BLOOM"
        try:
            glare.quality = "HIGH"
        except (AttributeError, TypeError, ValueError):
            pass
        glare.threshold = 0.7
        glare.size = 7
        glare.mix = -0.86
    else:
        # Blender 5.2 exposes the same settings as menu/value sockets on the
        # compositor node. "Bloom" and "High" are the new enum spellings.
        for socket_name, value in (
            ("Type", "Bloom"),
            ("Quality", "High"),
            ("Threshold", 0.7),
            ("Size", 0.8),
            ("Strength", 1.0),
        ):
            socket = glare.inputs.get(socket_name)
            if socket is not None:
                try:
                    socket.default_value = value
                except (AttributeError, TypeError, ValueError):
                    pass

    image_output = render_layers.outputs.get("Image")
    image_input = glare.inputs.get("Image")
    glare_output = glare.outputs.get("Image")
    if image_output is not None and image_input is not None:
        for link in list(image_input.links):
            tree.links.remove(link)
        tree.links.new(image_output, image_input)
    if glare_output is not None and composite_input is not None:
        for link in list(composite_input.links):
            tree.links.remove(link)
        tree.links.new(glare_output, composite_input)
    return False


def _setup_scene(scene: bpy.types.Scene) -> None:
    engine = _set_first_supported_engine(scene)
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = "//living-core-preview.png"
    scene["lc_render_engine"] = engine
    scene["lc_bloom"] = "native_eevee" if _ensure_compositor_bloom(scene) else "compositor_glare"

    world = scene.world or bpy.data.worlds.new("LivingCore_World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        background.inputs["Strength"].default_value = 0.0

    # Prefer a neutral filmic/high-contrast look where the current build offers
    # it, but never make the scene depend on a renamed view-transform option.
    for value in ("AgX", "Filmic"):
        try:
            scene.view_settings.view_transform = value
            break
        except (AttributeError, TypeError, ValueError):
            continue


def _find_generated(role: str) -> list[bpy.types.Object]:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        return []
    return [obj for obj in collection.objects if obj.get("lc_role") == role]


def _scene_for_control(control: bpy.types.Object) -> bpy.types.Scene:
    for scene in bpy.data.scenes:
        if scene.objects.get(control.name) is control:
            return scene
    return bpy.context.scene


def _refresh_control_drivers(control: bpy.types.Object, scene: bpy.types.Scene) -> None:
    """Tag ID-property edits so non-active scenes recalculate their drivers."""

    try:
        control.update_tag()
    except (AttributeError, RuntimeError):
        pass
    for view_layer in scene.view_layers:
        try:
            view_layer.update()
        except (AttributeError, RuntimeError):
            pass


def _tick(scene: bpy.types.Scene, _depsgraph=None, *, forced_dt: float | None = None) -> None:
    control = scene.objects.get(CONTROL_NAME)
    if control is None:
        return

    fps = max(float(scene.render.fps), 1.0)
    frame = int(scene.frame_current)
    last_frame = int(control.get("_last_frame", -1))
    if forced_dt is not None:
        dt = max(0.0, float(forced_dt))
    elif last_frame < 0:
        dt = 1.0 / fps
    else:
        dt = abs(frame - last_frame) / fps
        dt = dt if dt > 0.0 else 1.0 / fps
    dt = min(dt, 0.25)
    control["_last_frame"] = frame

    target_energy = min(1.2, max(0.0, float(control.get("energy", 0.34))))
    energy = float(control.get("_energy_smooth", target_energy))
    smoothing = min(1.0, dt * 5.5)
    energy += (target_energy - energy) * smoothing
    shock = min(1.0, max(0.0, float(control.get("shock", 0.0))))
    control["_energy_smooth"] = energy
    control["shock"] = shock

    mode = str(control.get("mode", "idle")).lower()
    mode_speed = float(control.get("_mode_speed", MODES.get(mode, MODES["idle"])["speed"]))
    speed_mul = min(4.0, max(0.1, float(control.get("speed_mul", 1.0))))
    speed = mode_speed * (0.7 + energy * 0.8) * speed_mul
    time_value = float(control.get("_time", 0.0)) + speed * dt
    control["_time"] = time_value


@persistent
def _living_core_frame_change(scene: bpy.types.Scene, depsgraph=None) -> None:
    _tick(scene, depsgraph)


setattr(_living_core_frame_change, HANDLER_TAG, True)


def _install_handler() -> None:
    _remove_owned_handlers()
    bpy.app.handlers.frame_change_pre.append(_living_core_frame_change)


class LC_OT_Build(bpy.types.Operator):
    bl_idname = "living_core.build"
    bl_label = "Build / Rebuild Living Core"
    bl_description = "Build the isolated live Living Core scene"

    def execute(self, _context):
        try:
            build(register_ui=False)
        except Exception as exc:  # Blender should report a failed build in the UI.
            self.report({"ERROR"}, f"Living Core build failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Living Core built in its isolated scene")
        return {"FINISHED"}


class LC_OT_Pulse(bpy.types.Operator):
    bl_idname = "living_core.pulse"
    bl_label = "Pulse"
    bl_description = "Trigger a transient shock impulse and expanding shockwave"

    def execute(self, context: bpy.types.Context):
        control = bpy.data.objects.get(CONTROL_NAME)
        if control is None:
            self.report({"WARNING"}, "LivingCore_CTRL does not exist; run the builder first")
            return {"CANCELLED"}
        scene = _scene_for_control(control)
        control["_pulse_strength"] = 1.0
        control["_pulse_frame"] = scene.frame_current
        _refresh_control_drivers(control, scene)
        _tick(scene, forced_dt=0.0)
        if context.scene == scene:
            context.view_layer.update()
        return {"FINISHED"}


class LC_OT_Mode(bpy.types.Operator):
    bl_idname = "living_core.mode"
    bl_label = "Set Living Core mode"

    mode: bpy.props.StringProperty(default="idle")

    def execute(self, context: bpy.types.Context):
        control = bpy.data.objects.get(CONTROL_NAME)
        if control is None:
            self.report({"WARNING"}, "LivingCore_CTRL does not exist; run the builder first")
            return {"CANCELLED"}
        selected = self.mode.lower()
        if selected not in MODES:
            self.report({"WARNING"}, f"Unknown Living Core mode: {selected}")
            return {"CANCELLED"}
        control["mode"] = selected
        control["energy"] = MODES[selected]["energy"]
        control["_mode_speed"] = MODES[selected]["speed"]
        scene = _scene_for_control(control)
        _refresh_control_drivers(control, scene)
        _tick(scene, forced_dt=0.0)
        if context.scene == scene:
            context.view_layer.update()
        return {"FINISHED"}


class LC_PT_Panel(bpy.types.Panel):
    bl_label = "Living Core"
    bl_idname = "LC_PT_living_core"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Living Core"

    def draw(self, context):
        layout = self.layout
        layout.operator("living_core.build", icon="FILE_REFRESH")
        control = bpy.data.objects.get(CONTROL_NAME)
        if control is None:
            layout.label(text="Build the isolated scene to begin")
            return
        layout.prop(control, '["energy"]', text="Energy", slider=True)
        layout.prop(control, '["shock"]', text="Shock", slider=True)
        layout.label(text=f"Mode: {str(control.get('mode', 'idle')).title()}")
        row = layout.row(align=True)
        for mode in MODES:
            operator = row.operator("living_core.mode", text=mode.title())
            operator.mode = mode
        layout.separator()
        layout.operator("living_core.pulse", icon="LIGHT")
        layout.label(text=f"Live scene v{SCRIPT_VERSION}")


CLASSES = (LC_OT_Build, LC_OT_Pulse, LC_OT_Mode, LC_PT_Panel)


def _unregister_existing_classes() -> None:
    for cls in reversed(CLASSES):
        candidates = (cls, getattr(bpy.types, cls.bl_idname, None))
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                bpy.utils.unregister_class(candidate)
                break
            except (RuntimeError, ValueError):
                continue


def register() -> None:
    # Re-register on every build so rerunning the Text Editor script also
    # refreshes operator behavior from the current source text.
    _unregister_existing_classes()
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except (RuntimeError, ValueError):
            # A second execution can encounter a stale class from a prior
            # text-block run.  Unregister the visible Blender type and retry.
            existing = getattr(bpy.types, cls.__name__, None)
            if existing is not None:
                bpy.utils.unregister_class(existing)
            bpy.utils.register_class(cls)


def unregister() -> None:
    _remove_owned_handlers()
    _unregister_existing_classes()


def build(*, register_ui: bool = True) -> bpy.types.Object:
    """Build and return the controller Empty for the live energy core."""

    operator_state = _prepare_operator_context()
    target_scene = _ensure_scene()
    _purge_previous_build(target_scene)
    collection = _ensure_collection(target_scene)
    target_scene["lc_collection_name"] = collection.name

    core_material = _emission_material("LC_CoreEmission", CORE_CYAN, 12.0)
    edge_material = _emission_material("LC_EdgeEmission", EDGE_BLUE, 5.0)
    white_material = _emission_material("LC_WhiteCoreEmission", WHITE_CYAN, 18.0)
    glow_material = _emission_material("LC_GlowEmission", CORE_CYAN, 2.8)
    orb_material = _emission_material("LC_OrbEmission", WHITE_CYAN, 8.0)
    halo_material = _emission_material("LC_HaloEmission", CORE_CYAN, 1.8)
    shock_material = _emission_material("LC_ShockwaveEmission", WHITE_CYAN, 11.0)

    control = _make_control(collection, target_scene)
    _make_core(collection, control, white_material, glow_material)
    _make_rings(collection, control, core_material, edge_material)
    _make_orbs(collection, control, orb_material)
    _make_dust(collection, control, halo_material)
    _make_irregular_halo(collection, control, halo_material)
    _make_shockwave(collection, control, shock_material)
    _make_camera(target_scene, collection)
    _setup_scene(target_scene)
    _install_persistent_drivers(
        target_scene,
        control,
        white_material,
        glow_material,
        halo_material,
        shock_material,
    )
    if register_ui:
        register()
    _install_handler()
    _refresh_control_drivers(control, target_scene)
    _tick(target_scene, forced_dt=0.0)
    try:
        target_scene.frame_set(target_scene.frame_current)
    except (AttributeError, RuntimeError):
        pass
    _restore_operator_context(operator_state)
    _activate_scene(target_scene, control)

    print(
        f"Living Core {SCRIPT_VERSION} built for Blender "
        f"{bpy.app.version_string}; scene={target_scene.name}; "
        f"controller={CONTROL_NAME}; "
        f"objects={len(collection.objects)}"
    )
    return control


if __name__ == "__main__":
    build()
