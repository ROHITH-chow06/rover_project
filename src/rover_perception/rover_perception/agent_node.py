import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import TwistStamped
import json
import threading
import time
from google import genai

LABEL_SYNONYMS = [
    {"cup", "bottle", "vase", "wine glass", "bowl"},
    {"refrigerator", "microwave", "tv", "laptop", "oven"},
    {"chair", "bench", "couch"},
    {"person"},
    {"stop sign", "traffic light"},
]

SEARCH_TIMEOUT_SECONDS = 240

def target_is_detected(instruction, detections):
    instruction_lower = instruction.lower()
    for group in LABEL_SYNONYMS:
        if any(word in instruction_lower for word in group):
            matches = [d for d in detections if d['label'].lower() in group]
            if matches:
                best = max(matches, key=lambda d: d['size_fraction'])
                return best['label'], best['size_fraction']
    return None, 0


SYSTEM_PROMPT = """You are the decision-making layer for a small rover robot.
You receive: (1) an instruction from a human operator, (2) a list of objects
the robot's camera currently detects, (3) confirmation that the target has
been found.

Reply with ONLY a JSON object, no other text, in exactly this format:
{"action": "move_forward" | "turn_left" | "turn_right", "reason": "short explanation"}

Rules:
- The target has already been confirmed found, so normally choose "move_forward" to approach it.
- Only choose turn_left or turn_right if the target appears off to one side and needs realigning.
- Never choose "stop" — stopping is handled separately by the system, not by you.
- Always return valid JSON only. No markdown, no backticks, no extra text.
"""

class AgentNode(Node):
    def __init__(self):
        super().__init__('agent_node')
        self.latest_detections = []
        self.current_instruction = None
        self.lock = threading.Lock()

        self.target_confirmed = False
        self.misses_since_found = 0
        self.last_known_size = 0
        self.search_start_time = None
        self.search_tick_count = 0

        self.detection_sub = self.create_subscription(
            String, '/detected_objects', self.detection_callback, 10)
        self.cmd_pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)

        self.client = genai.Client()

        self.timer = self.create_timer(5.0, self.act)

        self.get_logger().info('Agent node started. Type an instruction and press Enter.')
        self.get_logger().info('Example: find a cup and go to it')
        self.get_logger().info('Type "stop" at any time to halt immediately.')

        input_thread = threading.Thread(target=self.input_loop, daemon=True)
        input_thread.start()

    def detection_callback(self, msg):
        with self.lock:
            self.latest_detections = json.loads(msg.data)

    def publish_stop(self):
        msg = TwistStamped()
        msg.header.frame_id = 'base_link'
        for _ in range(10):
            msg.header.stamp = self.get_clock().now().to_msg()
            self.cmd_pub.publish(msg)
            time.sleep(0.1)

    def input_loop(self):
        while True:
            try:
                text = input("Instruction> ")
            except EOFError:
                break
            text = text.strip()
            if not text:
                continue

            if text.lower() == "stop":
                with self.lock:
                    self.current_instruction = None
                    self.target_confirmed = False
                    self.misses_since_found = 0
                    self.search_start_time = None
                self.get_logger().info('STOP received — halting immediately.')
                self.publish_stop()
                continue

            with self.lock:
                self.current_instruction = text
                self.target_confirmed = False
                self.misses_since_found = 0
                self.search_start_time = time.time()
                self.search_tick_count = 0
            self.get_logger().info(f'New instruction set: "{text}"')

    def act(self):
        with self.lock:
            instruction = self.current_instruction
            detections = list(self.latest_detections)

        if not instruction:
            return

        matched_label, size_fraction = target_is_detected(instruction, detections)
        if matched_label is not None:
            self.target_confirmed = True
            self.misses_since_found = 0
            self.last_known_size = size_fraction
        elif self.target_confirmed:
            self.misses_since_found += 1
            if self.misses_since_found > 3:
                self.target_confirmed = False
        target_found = self.target_confirmed

        elapsed = time.time() - self.search_start_time if self.search_start_time else 0
        raw_labels = [d['label'] for d in detections]
        self.get_logger().info(
            f'[STATUS] Instruction: "{instruction}" | Found: {target_found} | '
            f'Matched(this tick): {matched_label} | Raw: {raw_labels} | '
            f'Size: {self.last_known_size:.3f} | Misses: {self.misses_since_found} | Elapsed: {elapsed:.0f}s'
        )

        if not target_found and elapsed > SEARCH_TIMEOUT_SECONDS:
            self.get_logger().warn(
                f'Search timed out after {SEARCH_TIMEOUT_SECONDS}s — target not found. Stopping.'
            )
            with self.lock:
                self.current_instruction = None
                self.search_start_time = None
            self.publish_stop()
            return

        CLOSE_ENOUGH_THRESHOLD = 0.10
        if target_found and self.last_known_size > CLOSE_ENOUGH_THRESHOLD:
            self.get_logger().info(
                f'Target close enough (size={self.last_known_size:.3f}), stopping.')
            with self.lock:
                self.current_instruction = None
                self.search_start_time = None
            self.target_confirmed = False
            self.publish_stop()
            return

        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        burst_duration = 10

        if not target_found:
            self.search_tick_count += 1
            if self.search_tick_count % 3 == 0:
                msg.twist.linear.x = 0.3
                burst_duration = 45
                self.get_logger().info('Searching (no LLM call): move_forward (exploring)')
            else:
                msg.twist.angular.z = 0.4
                burst_duration = 10
                self.get_logger().info('Searching (no LLM call): turn_left (scanning)')
        else:
            prompt = (
                f"Instruction: {instruction}\n"
                f"Currently detected objects: {json.dumps(detections)}\n"
                f"target_found: true (matched label: {matched_label})\n"
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
                action = decision.get("action", "move_forward")
                reason = decision.get("reason", "")
                self.get_logger().info(f'Agent decision (LLM): {action} — {reason}')
            except Exception as e:
                self.get_logger().warn(f'Agent call failed, defaulting to move_forward: {e}')
                action = "move_forward"

            # Ignore any "stop" the LLM might still return — only the
            # deterministic size-based check above is allowed to stop the robot.
            if action == "turn_left":
                msg.twist.angular.z = 0.4
            elif action == "turn_right":
                msg.twist.angular.z = -0.4
            else:
                msg.twist.linear.x = 0.3
            burst_duration = 45

        for _ in range(burst_duration):
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
