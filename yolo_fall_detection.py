import cv2
import math
from ultralytics import YOLO
from fall_tracking import FallTracker


class FallDetector:
    """A class for detecting people and identifying potential falls using YOLO."""

    def __init__(self, model_path="yolo_weights/yolo11n-pose.pt", conf_threshold=0.3):
        """
        Initializes the FallDetector class.

        :param model_path: Path to the YOLO pose detection model.
        :param conf_threshold: Confidence threshold for detecting people.
        """
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.UKBlue = (160, 51, 0)  # IN BGR
        self.Bluegrass = (255, 138, 30)
        self.White = (255, 255, 255)
        self.Golenrod = (0, 220, 255)
        self.Sunset = (96, 163, 255)
        self.Red = (0, 0, 255)
        self.classNames = ["person"]  # Only tracking people
        self.keypoints_labels = [
            "Nose", "Left Eye", "Right Eye", "Left Ear", "Right Ear",
            "Left Shoulder", "Right Shoulder", "Left Elbow", "Right Elbow",
            "Left Wrist", "Right Wrist", "Left Hip", "Right Hip",
            "Left Knee", "Right Knee", "Left Ankle", "Right Ankle"
        ]
        self.fall_tracker = FallTracker(cooldown=1.0, persistence=1.0)


    def test_process_frame_box(self, img):
        results = self.model(img, stream=True, conf=self.conf_threshold, verbose=False)
        centroids_fallen = []
        height, width, _ = img.shape
        person_count = 0

        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) == 0:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    person_count += 1

                    confidence = math.ceil((box.conf[0] * 100)) / 100
                    cv2.rectangle(img, (x1, y1), (x2, y2), self.UKBlue, 3)
                    cv2.putText(img, f"Person {confidence:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.Bluegrass, 2)

                    # Determine if this box is a fall
                    w, h = x2 - x1, y2 - y1
                    is_fallen = h < w  # horizontal aspect → fallen
                    if is_fallen:
                        cv2.putText(img, "Fall Detected", (20, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 2)

                    centroids_fallen.append((cx, cy, is_fallen))

        # === Update tracker
        triggered_ids = self.fall_tracker.update(centroids_fallen)

        return img, len(triggered_ids) > 0, person_count, self.fall_tracker.get_unique_faller_count()
    
    def test_process_frame_pose(self, img):
        """
        Processes a single frame and plots pose keypoints detected by YOLO.

        :param img: The input frame (numpy array).
        :return: Frame with keypoints plotted.
        """
        results = self.model(img, stream=True, conf=self.conf_threshold, verbose=False)

        # Iterate over the detection results
        for result in results:
            keypoints = result.keypoints

            if keypoints is not None:
                for person_keypoints in keypoints.xy:
                    for idx, keypoint in enumerate(person_keypoints):
                        x, y = map(int, keypoint[:2])
                        # Plot keypoints on the image
                        cv2.circle(img, (x, y), 5, self.UKBlue, -1)

                        # # Optionally label keypoints
                        # joint_name = [
                        #     "Nose", "Left Eye", "Right Eye", "Left Ear", "Right Ear",
                        #     "Left Shoulder", "Right Shoulder", "Left Elbow", "Right Elbow",
                        #     "Left Wrist", "Right Wrist", "Left Hip", "Right Hip",
                        #     "Left Knee", "Right Knee", "Left Ankle", "Right Ankle"
                        # ][idx]
                        # cv2.putText(img, joint_name, (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 1)

        return img
    
    def test_process_frame_pose_fall(self, img):
        results = self.model(img, stream=True, conf=self.conf_threshold, verbose=False)
        fallen = False
        height, width, _ = img.shape

        for r in results:
            for keypoints in r.keypoints.xy:
                points = keypoints.cpu().numpy()
                if len(points) < 17:
                    continue  # Skip if insufficient keypoints

                # Plot keypoints
                for idx, (x, y) in enumerate(points):
                    if x == 0 and y == 0:
                        continue
                    cv2.circle(img, (int(x), int(y)), 5, self.Bluegrass, -1)
                    
                    # Print keypoints body labels
                    # cv2.putText(img, self.keypoints_labels[idx], (int(x) + 5, int(y) - 5), 
                    #             cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                # Fall detection logic with error handling
                required_points_indices = [5, 6, 11, 12, 15, 16]
                if len(points) <= max(required_points_indices) or any(points[idx][0] == 0 and points[idx][1] == 0 for idx in required_points_indices):
                    continue  # Skip detection if critical points are missing or out of bounds

                required_points = {
                    "LShoulder": points[5],
                    "RShoulder": points[6],
                    "LHip": points[11],
                    "RHip": points[12],
                    "LAnkle": points[15],
                    "RAnkle": points[16]
                }

                shoulder_avg = (required_points["LShoulder"] + required_points["RShoulder"]) / 2
                hip_avg = (required_points["LHip"] + required_points["RHip"]) / 2

                # Vertical distances (y-axis)
                dist_shoulder_ankle_L = abs(required_points["LAnkle"][1] - required_points["LShoulder"][1])
                dist_shoulder_ankle_R = abs(required_points["RAnkle"][1] - required_points["RShoulder"][1])

                # True (Euclidean) distance between shoulders and hips
                dist_shoulder_hip = math.sqrt((shoulder_avg[0] - hip_avg[0])**2 + (shoulder_avg[1] - hip_avg[1])**2)

                # Visualization lines
                cv2.line(img, tuple(shoulder_avg.astype(int)), tuple(hip_avg.astype(int)), self.Golenrod, 2)
                cv2.putText(img, f"S-H: {dist_shoulder_hip:.1f}", (int(shoulder_avg[0]), int(shoulder_avg[1]-40)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.Golenrod, 2)


                # #line from ankle to shoulder
                # cv2.line(img, tuple(required_points["LShoulder"].astype(int)), tuple(required_points["LAnkle"].astype(int)), (0, 255, 255), 2)
                # cv2.line(img, tuple(required_points["RShoulder"].astype(int)), tuple(required_points["RAnkle"].astype(int)), (0, 255, 255), 2)

                #line from ankle to vertical distance up calculated above to shoulder
                cv2.line(img, tuple(required_points["LAnkle"].astype(int)), (int(required_points["LAnkle"][0]), int(required_points["LAnkle"][1] - dist_shoulder_ankle_L)), self.UKBlue, 2)
                cv2.line(img, tuple(required_points["RAnkle"].astype(int)), (int(required_points["RAnkle"][0]), int(required_points["RAnkle"][1] - dist_shoulder_ankle_R)), self.UKBlue, 2)



                cv2.putText(img, f"LS-LA: {dist_shoulder_ankle_L:.1f}", (int(required_points["LShoulder"][0]), int(required_points["LShoulder"][1]-10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 2)
                cv2.putText(img, f"RS-RA: {dist_shoulder_ankle_R:.1f}", (int(required_points["RShoulder"][0]), int(required_points["RShoulder"][1]+20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 2)

                # Determine fall
                if (dist_shoulder_ankle_L < dist_shoulder_hip) or (dist_shoulder_ankle_R < dist_shoulder_hip):
                    fallen = True
                    x1, y1 = int(shoulder_avg[0]), int(shoulder_avg[1])
                    
                    # # Text on top of person
                    # cv2.putText(img, "Fall Detected", (x1, y1 - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 3)
                    
                    # Text in top right
                    cv2.putText(img, "Fall Detected", (width - 120, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 3)


        return img, fallen

    def bottom_frac_fall_detection(self, img):
        height, width, _ = img.shape
        line_height = int(height * 1 / 2)

        cv2.line(img, (0, line_height), (width, line_height), self.UKBlue, 2)

        results = self.model(img, conf=self.conf_threshold, verbose=False)
        fallen = False

        for r in results:
            for keypoints in r.keypoints.xy:
                points = keypoints.cpu().numpy()
                valid_points = [(x, y) for x, y in points if x != 0 or y != 0]

                if valid_points and all(y > line_height for x, y in valid_points):
                    fallen = True
                    # #Text above line
                    # cv2.putText(img, "Fall Detected", (30, line_height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 3)
                    
                    #Text in bottom left
                    cv2.putText(img, "Fall Detected", (20, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.UKBlue, 3)


                for x, y in valid_points:
                    cv2.circle(img, (int(x), int(y)), 4, self.Bluegrass, -1)

        return img, fallen

    def combined_frame(self, img):
        fallen = False

        height, width, _ = img.shape
        box_img, box_fallen, _, _ = self.test_process_frame_box(img.copy())
        pose_img, pose_fallen = self.test_process_frame_pose_fall(img.copy())
        bottom_img, bottom_fallen = self.bottom_frac_fall_detection(img.copy())

        combined_img = cv2.addWeighted(box_img, 0.33, pose_img, 0.33, 0)
        combined_img = cv2.addWeighted(combined_img, 1, bottom_img, 0.34, 0)

        if box_fallen and pose_fallen and bottom_fallen:
            fallen = True
            cv2.putText(combined_img, "PERSON IS FALLEN", (35, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, self.Red, 3)

        return combined_img, fallen

    def draw_glasses_mustache(self, img):
        BLACK = (0, 0, 0)
        results = self.model(img, stream=True, conf=self.conf_threshold, verbose=False)

        for r in results:
            if hasattr(r, "keypoints"):
                for keypoints in r.keypoints.xy:
                    keypoints_list = keypoints.cpu().numpy().tolist()

                    if len(keypoints_list) >= 5 and all(kp != [0.0, 0.0] for kp in keypoints_list[:5]):
                        nose = tuple(map(int, keypoints_list[0]))
                        left_eye = tuple(map(int, keypoints_list[1]))
                        right_eye = tuple(map(int, keypoints_list[2]))
                        left_ear = tuple(map(int, keypoints_list[3]))
                        right_ear = tuple(map(int, keypoints_list[4]))

                        eye_distance = math.sqrt((right_eye[0] - left_eye[0]) ** 2 + (right_eye[1] - left_eye[1]) ** 2)
                        lens_radius = int(eye_distance * 0.4)
                        frame_size = int(lens_radius / 4)

                        cv2.circle(img, left_eye, lens_radius, BLACK, -1)
                        cv2.circle(img, right_eye, lens_radius, BLACK, -1)

                        left_frame_start = (left_eye[0] + lens_radius, left_eye[1])
                        left_frame_end = (left_ear[0], left_ear[1] - lens_radius)
                        right_frame_start = (right_eye[0] - lens_radius, right_eye[1])
                        right_frame_end = (right_ear[0], right_ear[1] - lens_radius)

                        cv2.line(img, left_frame_start, left_frame_end, BLACK, frame_size)
                        cv2.line(img, right_frame_start, right_frame_end, BLACK, frame_size)
                        cv2.line(img, left_frame_start, right_frame_start, BLACK, frame_size)

                        mustache_length = int(eye_distance * 0.48)
                        mustache_offset_y = int(eye_distance * 0.32)
                        mustache_y = nose[1] + int(mustache_offset_y * 1.2)

                        cv2.line(img, (nose[0], mustache_y), (nose[0] - mustache_length, mustache_y + int(mustache_length * 0.3)), BLACK, frame_size)
                        cv2.line(img, (nose[0], mustache_y), (nose[0] + mustache_length, mustache_y + int(mustache_length * 0.3)), BLACK, frame_size)
                    else:
                        cv2.putText(img, "Missing Face Keypoints", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

        return img


    def reset(self):
        # Reset any internal state, clear caches, etc.
        pass