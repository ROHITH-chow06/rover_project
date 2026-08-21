import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import TwistStamped
import json
import threading
import time
from google import genai

SYSTEM_PROMPT = """You are the decision-making layer for a small rover robot.
You receive: (1) an instruction from a human operator, (2) a list of objects
the robot's camera currently detects (may be empty).

Reply with ONLY a JSON object, no other text, in exactly this format:
{"action": "move_forward" | "turn_left" | "turn_right" | "stop", "reason": "short explanation"}

Rules:
- If the instruction asks to find/approach something and it IS in the detected objects list, action should move toward it (move_forward if roughly centered, otherwise turn_left/turn_right to search).
- If the instruction asks to find something NOT in the detected list, pick turn_left or turn_right to search for it.
- If the instruction is to stop, or the object is found and centered, use "stop".
- Always return valid JSON only. No markdown, no backticks, no extra text.
"""

class AgentNode(Node):
    def __init__(self):
        super().__init__('agent_node')
        self.latest_detections = []
        self.current_instruction = None
        self.lock = threading.Lock()

        self.detection_sub = self.create_subscription(
            String, '/detected_objects', self.detection_callback, 10)
        self.cmd_pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)

        self.client = genai.Client()

        self.timer = self.create_timer(5.0, self.act)

        self.get_logger().info('Agent node started. Type an instruction and press Enter.')
        self.get_logger().info('Example: find a refrigerator and go to it')

        input_thread = threading.Thread(target=self.input_loop, daemon=True)
        input_thread.start()

    def detection_callback(self, msg):
        with self.lock:
            self.latest_detections = json.loads(msg.data)

    def input_loop(self):
        while True:
            try:
                text = input("Instruction> ")
            except EOFError:
                break
            if text.strip():
                with self.lock:
                    self.current_instruction = text.strip()
                self.get_logger().info(f'New instruction set: "{text.strip()}"')

    def act(self):
        with self.lock:
            instruction = self.current_instruction
            detections = list(self.latest_detections)

        if not instruction:
            return

        prompt = (
            f"Instruction: {instruction}\n"
            f"Currently detected objects: {json.dumps(detections)}\n"
        )
        full_prompt = SYSTEM_PROMPT + "\n\n" + prompt

        try:
            response = self.client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=full_prompt
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                raw = raw.replace("json", "", 1).strip()
            decision = json.loads(raw)
        except Exception as e:
            self.get_logger().warn(f'Agent call failed: {e}')
            return

        action = decision.get("action", "stop")
        reason = decision.get("reason", "")
        self.get_logger().info(f'Agent decision: {action} — {reason}')

        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        if action == "move_forward":
            msg.twist.linear.x = 0.15
        elif action == "turn_left":
            msg.twist.angular.z = 0.4
        elif action == "turn_right":
            msg.twist.angular.z = -0.4
        elif action == "stop":
            with self.lock:
                self.current_instruction = None

        for _ in range(10):
            msg.header.stamp = self.get_clock().now().to_msg()
            self.cmd_pub.publish(msg)
            time.sleep(0.1)


def main(args=None):
    rclpy.init(args=args)
    node = AgentNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

