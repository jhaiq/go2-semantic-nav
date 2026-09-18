"""
deploy.launch.py: semantic navigation on the GO2 motion-authority stack.

    ros2 launch go2_semantic_bringup deploy.launch.py \\
        planner:=nav2 localization:=slam_mapping hardware_adapter:=dry_run

Brings up, in one graph:

* go2_bringup/system.launch.py (from GO2-seeing-eye-dog, built in an
  underlay): localization (odom/LiDAR relay, pointcloud_to_laserscan,
  slam_toolbox), the planner (Nav2, or the staged approach controller behind
  a NavigateToPose adapter), the LiDAR hazard source, and the motion
  authority (safety arbiter -> hardware bridge).
* semantic_nav.launch.py: detector, scene graph and grounding. Grounding
  dispatches NavigateToPose to whichever planner is running, so it never
  talks to the robot directly; every velocity passes the arbiter.

Motion requires ALL of: hardware_adapter:=unitree_sport, allow_goal_publication:=true,
and a GroundAndNavigate request with dry_run: false. The defaults are the
safe ones (dry_run adapter, interlock off).

Arguments
---------
planner                 nav2 | staged_nav   (default nav2)
localization            slam_mapping | slam_localization   (default slam_mapping)
map_file                serialized slam_toolbox pose graph for slam_localization
hardware_adapter        dry_run | unitree_sport   (default dry_run)
allow_goal_publication  semantic interlock, default false
enable_detector         false when no RGB-D camera is attached (default true)
enable_scene_graph      false when another node provides /semantic/scene_graph
cloud_in_topic          /utlidar/cloud_deskewed (default) or /utlidar/cloud
publish_lidar_extrinsic true only with the raw sensor-frame cloud
image_topic, depth_topic, camera_info_topic, profile: passed to semantic_nav
"""
from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

_ARGS = {
    "planner": "nav2",
    "localization": "slam_mapping",
    "map_file": "",
    "hardware_adapter": "dry_run",
    "dry_run_log_path": "",
    "allow_goal_publication": "false",
    "enable_detector": "true",
    "enable_scene_graph": "true",
    "cloud_in_topic": "/utlidar/cloud_deskewed",
    "publish_lidar_extrinsic": "false",
    "image_topic": "/camera/color/image_raw",
    "depth_topic": "/camera/aligned_depth_to_color/image_raw",
    "camera_info_topic": "/camera/color/camera_info",
    "use_sim_time": "false",
    "log_level": "info",
}


def generate_launch_description() -> LaunchDescription:
    cfg = {name: LaunchConfiguration(name) for name in _ARGS}

    base = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [PathJoinSubstitution([FindPackageShare("go2_bringup"), "launch", "system.launch.py"])]
        ),
        launch_arguments={
            # The seeing-eye-dog perception (mic, YOLO person detector, depth
            # safety monitor) is not part of this deployment; LiDAR provides
            # the hazard context instead.
            "perception": "none",
            "planner": cfg["planner"],
            "localization": cfg["localization"],
            "map_file": cfg["map_file"],
            "lidar_safety": "true",
            "cloud_in_topic": cfg["cloud_in_topic"],
            "publish_lidar_extrinsic": cfg["publish_lidar_extrinsic"],
            "hardware_adapter": cfg["hardware_adapter"],
            "dry_run_log_path": cfg["dry_run_log_path"],
            "use_sim_time": cfg["use_sim_time"],
            "log_level": cfg["log_level"],
        }.items(),
    )

    semantic = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [PathJoinSubstitution([FindPackageShare("go2_semantic_bringup"), "launch", "semantic_nav.launch.py"])]
        ),
        launch_arguments={
            "enable_detector": cfg["enable_detector"],
            "enable_scene_graph": cfg["enable_scene_graph"],
            "enable_grounding": "true",
            "allow_goal_publication": cfg["allow_goal_publication"],
            "navigation_backend": "nav2_action",
            "navigate_to_pose_action": "/navigate_to_pose",
            "image_topic": cfg["image_topic"],
            "depth_topic": cfg["depth_topic"],
            "camera_info_topic": cfg["camera_info_topic"],
            "use_slam_fallback": "false",
            "use_sim_time": cfg["use_sim_time"],
            "log_level": cfg["log_level"],
        }.items(),
    )

    return LaunchDescription(
        [DeclareLaunchArgument(name, default_value=default) for name, default in _ARGS.items()]
        + [base, semantic]
    )
