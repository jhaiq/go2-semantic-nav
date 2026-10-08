import math, time
import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener
from geometry_msgs.msg import PoseStamped

rclpy.init()
n = Node('goal_sender')
tf = Buffer()
TransformListener(tf, n)

while rclpy.ok() and not tf.can_transform('map', 'base_link', rclpy.time.Time()):
    rclpy.spin_once(n, timeout_sec=0.1)

tr = tf.lookup_transform('map', 'base_link', rclpy.time.Time())
x = tr.transform.translation.x
y = tr.transform.translation.y
q = tr.transform.rotation
yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z))

goal = PoseStamped()
goal.header.frame_id = 'map'
goal.header.stamp = n.get_clock().now().to_msg()
goal.pose.position.x = x + 1.2 * math.cos(yaw)   # 正前方 1.2m
goal.pose.position.y = y + 1.2 * math.sin(yaw)
goal.pose.orientation = q                         # 保持当前朝向，避免末端旋转

pub = n.create_publisher(PoseStamped, '/goal_pose', 10)
time.sleep(0.5)
pub.publish(goal)
print(f'goal sent: ({goal.pose.position.x:.2f}, {goal.pose.position.y:.2f}), 1.2m ahead of robot')
time.sleep(0.5)