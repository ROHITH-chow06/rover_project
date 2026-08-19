import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from ultralytics import YOLO

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector_node')
        self.bridge = CvBridge()
        self.model = YOLO('yolov8n.pt')  # nano model, downloads automatically first run
        self.sub = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 10)
        self.get_logger().info('Detector node started, waiting for images...')

    def image_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        results = self.model(frame, verbose=False)
        for r in results:
            for box in r.boxes:
                cls_name = self.model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                if conf > 0.5:
                    self.get_logger().info(f'Detected: {cls_name} ({conf:.2f})')

def main(args=None):
    rclpy.init(args=args)
    node = DetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
