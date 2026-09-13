# Agentic Autonomous Rover

## Project Brief
A simulated rover that combines classical robotics perception/control with an
LLM-based reasoning layer, so it can carry out plain-language instructions
("find a cup and go to it") rather than pre-programmed waypoints.

## Tech Stack
- **OS / middleware:** Ubuntu 24.04, ROS2 Jazzy
- **Simulation:** Gazebo Sim (via ros_gz)
- **Perception:** YOLOv8 (Ultralytics), OpenCV, cv_bridge
- **Reasoning layer:** Google Gemini API (gemini-3.1-flash-lite, free tier)
- **Language:** Python 3.12
- **Version control:** Git / GitHub

## Architecture
1. **Perception** (`detector_node`) — subscribes to the robot's camera feed,
   runs YOLOv8 object detection, publishes structured JSON (label,
   confidence, bounding-box size as a distance proxy) on `/detected_objects`
2. **Reasoning** (`agent_node`) — accepts live typed instructions, tracks
   current detections, and calls an LLM only when a target is genuinely
   found (not on every tick) to decide how to approach it
3. **Exploration** — deterministic scan-and-advance search pattern when no
   target is in view (no LLM call, free and instant)
4. **Control** — decisions converted to `TwistStamped` velocity commands
   published to `/cmd_vel`, driving the robot in Gazebo

## Week 1 — Environment Setup
- ROS2 Jazzy + Gazebo + Nav2 installed on Ubuntu 24.04
- TurtleBot3 sim running, keyboard teleop working
- Nav2 autonomous navigation confirmed working: AMCL localizes the robot via
  particle-filter matching of lidar data to a map, Nav2 plans a path to a
  clicked goal

## Week 2 — Perception
- Added custom ROS2 package `rover_perception`
- Camera feed confirmed working via rqt_image_view
- Built `detector_node`: YOLOv8 (pretrained) on live camera feed, publishing
  detections as JSON on `/detected_objects`
- Applied confidence threshold (>0.5) to filter noisy low-confidence
  detections
- Resolved dependency conflicts: pinned numpy==1.26.4 and
  opencv-python==4.9.0.80 (newer versions broke compatibility with
  cv_bridge/matplotlib)

## Week 3 — Agent Layer (interactive)
Built `agent_node`: live typed instructions, combined with current
detections, sent to an LLM with a system prompt constrained to structured
JSON actions.

**Problems encountered and solutions:**
- **Message type mismatch:** `/cmd_vel` expected `TwistStamped`, not plain
  `Twist`, due to how this Gazebo version's ROS2 bridge is wired. Diagnosed
  with `ros2 topic info --verbose` rather than guessing; verified the fix
  independently via `ros2 topic pub` before re-testing the full pipeline.
- **Perception noise on synthetic objects:** YOLOv8 (trained on real photos)
  gives unstable labels on Gazebo's simplified renders — a known sim-to-real
  gap. Addressed with confidence filtering, a synonym-grouping system
  (labels YOLO commonly confuses on similar shapes, e.g.
  {cup, bottle, vase, bowl}, treated as equivalent matches), and detection
  hysteresis (a target stays "confirmed" through a few missed frames before
  the robot resumes searching).
- **LLM API quota efficiency:** redesigned so the LLM is only called once a
  target is confirmed found, not on every decision tick — search/explore
  behavior is fully deterministic and free. Reduced real-world API usage
  from one call every 5 seconds to roughly one call per successful find.
- **Graceful degradation:** try/except fallback defaults to a sensible
  action if the LLM call fails (quota exhaustion, network issue), verified
  live during an actual quota-exhaustion event.

## Week 4 — Hardening, distance estimation, and demo
- Added bounding-box-size-based distance estimation (`size_fraction`) so the
  robot can judge proximity to its target from a 2D camera alone
- Added a stop-when-close-enough condition, and a direct "stop" text command
  that bypasses all other logic for immediate halt
- Added a search timeout (robot gives up and stops after an extended,
  unsuccessful search rather than running indefinitely)
- Added a live status line each decision tick (instruction, found/not,
  matched label, size, elapsed time) for easier debugging and demo clarity
- **Bug found and fixed:** the LLM occasionally decided to "stop" on its own
  reasoning before the robot was actually close, based on flawed inference
  from the instruction wording. Fixed by removing the LLM's ability to
  trigger a stop entirely — stopping is now controlled only by the
  deterministic size-threshold check, with the LLM restricted to
  approach/realignment decisions.
- **Simulation performance constraint identified:** on this hardware (8GB
  RAM), Gazebo's simulated clock runs meaningfully slower than real-time
  under full load (perception + LLM + physics running together), making
  long-distance approaches very slow in wall-clock time. Addressed
  pragmatically for demo purposes by starting the robot at a realistic
  working distance from the target, rather than chasing simulation
  performance tuning under time constraints — documented here rather than
  hidden.
- **Confirmed working end-to-end and recorded on video:** full cycle —
  search (scan + explore) → detect → approach → stop on arrival — working
  correctly from a real starting position.

## Known Limitations
- Exploration is a simple fixed scan-and-advance pattern, not real
  frontier-based exploration — effective within a limited search radius,
  not general-purpose maze solving
- No obstacle-avoidance during search or approach (would require Nav2
  costmap integration)
- Distance estimation is a rough 2D proxy (bounding-box size), not true
  depth sensing
- Perception limited to YOLO's default training classes; no custom/
  fine-tuned model yet
- Gazebo's simulated clock runs below real-time under full system load on
  this hardware, affecting demo pacing (see Week 4 notes above)

## Future Plans / Continuation
This project is intended to continue past the application deadline:
- **Nav2 integration:** replace raw velocity commands with full Nav2 goals
  for real obstacle-aware path planning
- **Frontier-based exploration:** proper unknown-space exploration instead
  of the current fixed scan pattern
- **Depth/distance:** move from bounding-box-size proxy to real depth
  sensing (stereo camera or depth sensor) for accurate proximity estimation
- **Sim-to-real:** move from Gazebo simulation to a physical platform
  (Raspberry Pi/Jetson Nano + RC chassis) to validate the pipeline on real
  hardware
- **Structured trial logging:** CSV-based logging of trial outcomes
  (success/fail, time, distance) for rigorous performance reporting
- **Fine-tuned perception:** train YOLO on a small custom dataset to fix the
  sim-to-real detection noise documented in Week 3
- **Terramechanics integration:** connect a parallel MATLAB-based tire/
  terrain analysis project (tread design for low-traction surfaces, modeled
  via Bekker terramechanics) to Gazebo's terrain physics, testing navigation
  performance across simulated soft/firm terrain — bridging automobile
  engineering coursework with the robotics stack built here

## Why This Project
Robotics and autonomous-vehicle research increasingly combines classical
perception/control pipelines with AI-driven decision-making — vision-
language-action models, agentic navigation, and LLM-assisted robot control
are active areas across mechanical and robotics engineering labs. This
project was built to gain hands-on experience with that exact pattern:
implementing it from scratch surfaces the real engineering tradeoffs —
perception noise, decision latency, API cost/efficiency, graceful failure
handling — that matter in this kind of system. 

## Demo
[Link to demo video to be added]

Full working cycle demonstrated: typed instruction -> deterministic search
(scan + explore, no API calls) -> object detected -> LLM-driven approach
decision -> robot drives to the object and stops on arrival.
