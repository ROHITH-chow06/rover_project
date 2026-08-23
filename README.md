# Autonomous Rover Project
## Week 1 — Environment Setup
- ROS2 Jazzy + Gazebo + Nav2 installed on Ubuntu 24.04
- TurtleBot3 sim running, keyboard teleop working
- Nav2 autonomous navigation working: AMCL localizes robot via particle
  filter matching lidar data to map, Nav2 plans path to clicked goal
----------------------------------------------------------------------------
## Week 2 — Perception
- Added custom ROS2 package `rover_perception`
- Camera feed confirmed working via rqt_image_view
- Built `detector_node`: subscribes to /camera/image_raw, runs YOLOv8 (pretrained,
  ultralytics), publishes detections as JSON on /detected_objects
- Applied confidence threshold (>0.5) to filter noisy low-confidence detections
- Resolved dependency conflicts: pinned numpy==1.26.4 and opencv-python==4.9.0.80
  (newer versions of both broke compatibility with cv_bridge/matplotlib)
----------------------------------------------------------------------------

## Week 3 — Agent Layer (interactive)

### Architecture
- `agent_node` subscribes to `/detected_objects`, accepts live typed instructions
  via terminal input (background thread, non-blocking against ROS2's event loop)
- Combines instruction + current detections, sends to Gemini (free tier,
  gemini-3.1-flash-lite) with a system prompt constraining output to structured
  JSON actions: move_forward / turn_left / turn_right / stop
- Publishes resulting velocity commands to /cmd_vel

### Problems encountered and how they were solved

**1. Message type mismatch (robot wouldn't move at all)**
Initial version published `geometry_msgs/Twist` to /cmd_vel, but the robot never
moved. Diagnosed with `ros2 topic info /cmd_vel --verbose`, which showed the
Gazebo bridge (`ros_gz_bridge`) subscribes to `TwistStamped`, not plain `Twist` —
a version-specific detail of this ROS2/Gazebo setup, not documented clearly
anywhere obvious. Fixed by switching the publisher and message construction to
`TwistStamped`, including a timestamp refreshed on every publish (stale
timestamps are sometimes silently ignored).
Verified the fix independently of the LLM using `ros2 topic pub` with a manual
command, to isolate "is it a code bug" from "is it a quota/API issue" before
re-testing the full pipeline.

**2. Perception noise on synthetic/simulated objects**
YOLOv8 (pretrained on real-world photos) gives unstable, low-confidence, and
often wrong labels on Gazebo's simplified 3D renders — a real, known problem in
robotics called the sim-to-real / domain gap. A single test object (a can)
was variously classified as cup, bottle, vase, refrigerator, stop sign,
airplane, and person across different frames and angles.
Addressed with:
  - A confidence threshold (>0.5) to cut obvious noise
  - A synonym-grouping system: labels that YOLO commonly confuses on similar-
    shaped objects (e.g. {cup, bottle, vase, bowl}) are treated as equivalent
    matches for a given instruction, rather than requiring an exact label match
  - Detection hysteresis: once a target is confirmed found, a few consecutive
    "missed" frames (label flicker) are tolerated before the robot resumes
    searching, rather than reacting to every single frame's noisy guess

**3. LLM API quota efficiency**
Initial version called the LLM every 5 seconds regardless of whether anything
had changed, burning through the free-tier daily quota (500 requests) quickly
during iterative testing.
Redesigned so the LLM is only called when the target is actually confirmed
found — while searching, the robot rotates using simple deterministic logic
(no API call, free and instant). This cut API usage dramatically and is also a
better architectural pattern in general: reasoning should be reserved for
genuinely ambiguous decisions, not repetitive/mechanical ones.

**4. Graceful degradation on API failure**
Added a try/except fallback: if the LLM call fails (quota exhausted, network
issue, malformed response), the agent defaults to a sensible action
(move_forward, if the target is already confirmed found) rather than crashing
or freezing. Verified this in practice when a live quota-exhaustion event
occurred mid-test — the robot continued behaving sensibly instead of stalling.

### Confirmed working end-to-end
Full cycle demonstrated live: typed instruction -> deterministic search
(rotating, no API calls) -> object detected -> LLM-driven approach decision ->
robot drives to the object and stops nearby.

## Known limitations / next steps
- No distance/proximity estimation yet — the robot currently loses sight of
  the target once very close (object exits camera frame), which then
  incorrectly triggers renewed searching. Planned fix: estimate distance from
  detection bounding box size, and stop once the box crosses a size threshold,
  rather than relying on continuous detection all the way to arrival.
- No obstacle-aware path planning yet — agent issues raw velocity commands,
  not full Nav2 goals (would need Nav2 integration for real path planning
  around obstacles)
- Perception is english-object-only; no attempt yet to handle instructions
  referring to objects not in YOLO's default training classes
