"""Upper-body readiness decisions, independent of camera and ML dependencies."""

import math


JOINTS = {
    11: "L shoulder", 12: "R shoulder",
    13: "L elbow", 14: "R elbow",
    15: "L wrist", 16: "R wrist",
}
CONNECTIONS = ((11, 12), (11, 13), (13, 15), (12, 14), (14, 16))
STALE_SECONDS = 0.5


def reliable(landmark, threshold=0.6):
    """A confident prediction outside the image is still not a visible joint."""
    values = (landmark.x, landmark.y, landmark.visibility, landmark.presence)
    return (
        all(value is not None and math.isfinite(value) for value in values)
        and 0 <= landmark.x <= 1
        and 0 <= landmark.y <= 1
        and landmark.visibility >= threshold
        and landmark.presence >= threshold
    )


def assess(landmarks, age_seconds, threshold=0.6):
    """Return a status and visible required joints; never accept stale landmarks."""
    if not math.isfinite(age_seconds) or not 0 <= age_seconds <= STALE_SECONDS:
        return "TRACKING STALE", set()
    if not landmarks or len(landmarks) <= max(JOINTS):
        return "NO PERSON DETECTED", set()
    visible = {index for index in JOINTS if reliable(landmarks[index], threshold)}
    if len(visible) == len(JOINTS):
        return "UPPER BODY READY", visible
    return "PARTIAL UPPER BODY", visible


def joint_reason(point, threshold=0.6):
    """Describe an unreliable estimate without pretending we know an occlusion's cause."""
    if point is None:
        return "NOT FOUND"
    if not all(value is not None and math.isfinite(value) for value in (point.x, point.y)):
        return "NOT FOUND"
    if point.y > 1:
        return "BELOW FRAME"
    if point.y < 0:
        return "ABOVE FRAME"
    if not 0 <= point.x <= 1:
        return "OUTSIDE SIDE EDGE"
    if reliable(point, threshold):
        return "VISIBLE"
    return "LOW CONFIDENCE"


def framing_hints(landmarks, age_seconds, threshold=0.6):
    status, visible = assess(landmarks, age_seconds, threshold)
    if status == "TRACKING STALE":
        return ["Waiting for fresh tracking. Keep the camera connected."]
    if not landmarks or len(landmarks) <= max(JOINTS):
        return ["Sit facing the camera with your head and upper body in view.",
                "Start about 70-100 cm away; light your face from the front."]
    if len(visible) == len(JOINTS):
        return ["Good framing. Slowly lean and extend each arm.",
                "Keep both wrists and elbows inside the guide."]
    missing = set(JOINTS) - visible
    hints = []
    points = [landmarks[index] for index in JOINTS]
    if any(joint_reason(point, threshold) == "OUTSIDE SIDE EDGE" for point in points):
        hints.append("Move your chair back a little and centre your shoulders.")
    wrists = [landmarks[index] for index in (15, 16) if index in missing]
    if any(point.y is not None and math.isfinite(point.y) and point.y > 0.85 for point in wrists):
        hints.append("Raise your hands to chest height, above the table.")
    elbows = [landmarks[index] for index in (13, 14) if index in missing]
    if any(point.y is not None and math.isfinite(point.y) and point.y > 0.9 for point in elbows):
        hints.append("Aim the camera slightly down until both elbows fit.")
    if not hints:
        hints.append("Sit back a little so your head, shoulders and elbows fit.")
    hints.append("Hold a relaxed guard; separate your elbows from your ribs.")
    hints.append("Keep light in front of you and wrists clear of your face.")
    return hints[:3]


def tracking_label(visible, status):
    """Describe usable observations without requiring an artificial guard pose."""
    if status in ("NO PERSON DETECTED", "TRACKING STALE", "WAITING FOR TRACKER"):
        return status.capitalize()
    if set(JOINTS) <= visible:
        return "Upper body ready"
    if {11, 12, 15, 16} <= visible:
        return "Shoulders + wrists tracked; elbows uncertain"
    if {11, 12} <= visible:
        return "Shoulders tracked; keep your hands visible"
    return "Move your upper body into camera view"
