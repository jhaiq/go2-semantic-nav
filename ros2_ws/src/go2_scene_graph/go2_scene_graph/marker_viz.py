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


# 使用全局变量记录上一帧发布过的 marker id，用于检测哪些物体消失了
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

        # 用物体的唯一 ID (如 tracklet_id) 生成稳定的整数 marker id
        # 这样同一个物体每次都在同一个 id 上更新，不会闪烁
        try:
            # 如果 obj 有 tracklet_id (字符串)，用哈希转成整数
            obj_hash = int(hashlib.md5(str(obj.tracklet_id).encode()).hexdigest()[:8], 16) % 1000000
        except AttributeError:
            # 如果没有，退回到用坐标哈希
            coord_str = f"{obj.position_map[0]:.2f}_{obj.position_map[1]:.2f}_{obj.position_map[2]:.2f}"
            obj_hash = int(hashlib.md5(coord_str.encode()).hexdigest()[:8], 16) % 1000000

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
        sphere.lifetime = Duration(sec=0, nanosec=0)  # 0 表示永久有效，直到下一次更新
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
        text.lifetime = Duration(sec=0, nanosec=0)  # 0 表示永久有效
        arr.markers.append(text)

    # --- 删除已经不存在的物体（防止旧球残留） ---
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

    # 更新记录
    _prev_sphere_ids = current_sphere_ids
    _prev_text_ids = current_text_ids

    return arr