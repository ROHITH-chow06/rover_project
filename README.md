# Autonomous Rover Project
## Week 1 — Environment Setup
- ROS2 Jazzy + Gazebo + Nav2 installed on Ubuntu 24.04
- TurtleBot3 sim running, keyboard teleop working
- Nav2 autonomous navigation working: AMCL localizes robot via particle
  filter matching lidar data to map, Nav2 plans path to clicked goal
## Week 2 — Perception
- Added custom ROS2 package `rover_perception`
- Camera feed confirmed working via rqt_image_view
- Built `detector_node`: subscribes to /camera/image_raw, runs YOLOv8 (pretrained,
  ultralytics), publishes detections as JSON on /detected_objects
- Applied confidence threshold (>0.5) to filter noisy low-confidence detections
- Resolved dependency conflicts: pinned numpy==1.26.4 and opencv-python==4.9.0.80
  (newer versions of both broke compatibility with cv_bridge/matplotlib)

## Week 3 — Agent Layer (interactive)
- Built `agent_node`: takes live typed instructions via terminal, combines them
  with current detections, sends both to an LLM (Gemini 3.1 Flash Lite, free tier)
  with a system prompt constraining output to structured JSON actions
  (move_forward / turn_left / turn_right / stop)
- Debugged a real integration bug: /cmd_vel expected geometry_msgs/TwistStamped,
  not plain Twist, due to how the ROS2-Gazebo bridge (ros_gz_bridge) is wired in
  this Gazebo version — found via `ros2 topic info --verbose` rather than guessing
- Verified movement pipeline manually (via `ros2 topic pub`) independent of the
  LLM, to isolate the message-type bug from LLM/quota issues
- Confirmed working end-to-end: instruction -> LLM decision -> robot motion

## Known limitations / next steps
- Detections often misclassify objects (default TurtleBot3 world has no
  real-world objects for YOLO's training classes) — plan to add real object
  models to the Gazebo world
- No obstacle-aware path planning yet — agent currently issues raw velocity
  commands, not full Nav2 goals
- No failure-recovery logic yet if the LLM call fails or times out
