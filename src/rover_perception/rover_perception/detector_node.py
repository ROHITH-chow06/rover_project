import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
from ultralytics import YOLO
import json

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector_node')
        self.bridge = CvBridge()
        self.model = YOLO('yolov8n.pt')
        self.sub = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 10)
        self.pub = self.create_publisher(String, '/detected_objects', 10)
        self.get_logger().info('Detector node started, waiting for images...')

    def image_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        frame_area = frame.shape[0] * frame.shape[1]
        results = self.model(frame, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                cls_name = self.model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                if conf > 0.5:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    box_area = (x2 - x1) * (y2 - y1)
                    size_fraction = round(box_area / frame_area, 4)
                    detections.append({
                        'label': cls_name,
                        'confidence': round(conf, 2),
                        'size_fraction': size_fraction
                    })
                    self.get_logger().info(
                        f'Detected: {cls_name} ({conf:.2f}) size={size_fraction:.3f}')
        msg_out = String()
        msg_out.data = json.dumps(detections)
        self.pub.publish(msg_out)

def main(args=None):
    rclpy.init(args=args)
    node = DetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
