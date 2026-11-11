"""RViz MarkerArray generation for the scene graph."""

from __future__ import annotations

import hashlib
from typing import Iterable, Set

from builtin_interfaces.msg import Duration
from geometry_msgs.msg import Point, Quaternion, Vector3
from std_msgs.msg import ColorRGBA
from visualization_msgs.msg import Marker, MarkerArray

from .graph_store import TrackedObject


def _label_color(label: str) -> ColorRGBA:
    """Deterministic pleasant color per label."""
    h = hashlib.md5(label.encode("utf-8")).digest()
    r = (h[0] / 255.0) * 0.6 + 0.3
    g = (h[1] / 255.0) * 0.6 + 0.3
    b = (h[2] / 255.0) * 0.6 + 0.3
    return ColorRGBA(r=float(r), g=float(g), b=float(b), a=0.9)


# Track published marker IDs so removed objects can be deleted from RViz.
_prev_sphere_ids: Set[int] = set()
_prev_text_ids: Set[int] = set()


def build_object_markers(
    objects: Iterable[TrackedObject],
    map_frame: str,
    stamp,
    min_observations: int = 3,
) -> MarkerArray:
    """Emit one sphere + one label text marker per object in the map frame."""
    global _prev_sphere_ids, _prev_text_ids

    arr = MarkerArray()
    current_sphere_ids: Set[int] = set()
    current_text_ids: Set[int] = set()

    for obj in objects:
        if obj.observation_count < min_observations:
            continue

        obj_hash = int(
            hashlib.md5(str(obj.object_id).encode("utf-8")).hexdigest()[:8], 16
        ) % 1000000

        sphere_id = obj_hash * 2
        text_id = obj_hash * 2 + 1

        current_sphere_ids.add(sphere_id)
        current_text_ids.add(text_id)

        # --- 球体 ---
        sphere = Marker()
        sphere.header.frame_id = map_frame
        sphere.header.stamp = stamp
        sphere.ns = "go2_scene_graph/objects"
        sphere.id = sphere_id
        sphere.type = Marker.SPHERE
        sphere.action = Marker.ADD
        sphere.pose.position = Point(
            x=float(obj.position_map[0]),
            y=float(obj.position_map[1]),
            z=float(obj.position_map[2]),
        )
        sphere.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        size = max(0.15, float(min(obj.dimensions[0], obj.dimensions[1])))
        sphere.scale = Vector3(x=size, y=size, z=size)
        sphere.color = _label_color(obj.label)
        sphere.lifetime = Duration(sec=0, nanosec=0)
        arr.markers.append(sphere)

        # --- 文字 ---
        text = Marker()
        text.header.frame_id = map_frame
        text.header.stamp = stamp
        text.ns = "go2_scene_graph/labels"
        text.id = text_id
        text.type = Marker.TEXT_VIEW_FACING
        text.action = Marker.ADD
        text.pose.position = Point(
            x=float(obj.position_map[0]),
            y=float(obj.position_map[1]),
            z=float(obj.position_map[2] + size * 0.8),
        )
        text.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        text.scale = Vector3(x=0.0, y=0.0, z=0.15)
        text.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
        text.text = f"{obj.label} [{obj.confidence:.2f}]"
        text.lifetime = Duration(sec=0, nanosec=0)
        arr.markers.append(text)

    # Delete markers for objects that are no longer in the scene graph.
    for old_id in _prev_sphere_ids - current_sphere_ids:
        delete_sphere = Marker()
        delete_sphere.header.frame_id = map_frame
        delete_sphere.header.stamp = stamp
        delete_sphere.ns = "go2_scene_graph/objects"
        delete_sphere.id = old_id
        delete_sphere.action = Marker.DELETE
        arr.markers.append(delete_sphere)

    for old_id in _prev_text_ids - current_text_ids:
        delete_text = Marker()
        delete_text.header.frame_id = map_frame
        delete_text.header.stamp = stamp
        delete_text.ns = "go2_scene_graph/labels"
        delete_text.id = old_id
        delete_text.action = Marker.DELETE
        arr.markers.append(delete_text)

    _prev_sphere_ids = current_sphere_ids
    _prev_text_ids = current_text_ids

    return arr