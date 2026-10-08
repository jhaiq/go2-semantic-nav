import time, rclpy, cv2
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from ultralytics import YOLO

TOPIC = "/camera/camera/color/image_raw"
PROMPTS = ["chair","sofa","table","desk","window","door","person",
           "refrigerator","television","bed","lamp","potted plant",
           "bookshelf","cup","laptop","backpack"]
CONF = 0.3

rclpy.init()
n = Node('yoloe_test')
br = CvBridge()
state = {"img": None}
n.create_subscription(Image, TOPIC, lambda m: state.update(img=br.imgmsg_to_cv2(m, "bgr8")), 10)

print("等相机帧...")
while state["img"] is None:
    rclpy.spin_once(n, timeout_sec=0.1)
print("相机帧:", state["img"].shape)

model = YOLO("yoloe-26s-seg.pt")
model.set_classes(PROMPTS)
print("yoloe-26s 就绪，词表", len(PROMPTS), "类\n")

for i in range(50):
    while state["img"] is None:
        rclpy.spin_once(n, timeout_sec=0.05)
    img = state["img"]; state["img"] = None

    t0 = time.perf_counter()
    r = model.predict(img, conf=CONF, verbose=False, retina_masks=True)[0]
    dt = (time.perf_counter() - t0) * 1000

    if r.boxes is None or len(r.boxes) == 0:
        print(f"[{i:2d}] {dt:5.0f}ms  无检出"); continue
    items = ", ".join(f"{r.names[int(c)]}:{float(cf):.2f}"
                      for c, cf in zip(r.boxes.cls, r.boxes.conf))
    print(f"[{i:2d}] {dt:5.0f}ms  mask={'Y' if r.masks is not None else 'N'}  {items}")
    cv2.imwrite(f"/tmp/yoloe_test_{i%5}.jpg", r.plot())   # 标注图，肉眼验收用
print("\n标注图在 /tmp/yoloe_test_*.jpg")