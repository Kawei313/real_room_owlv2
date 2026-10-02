import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from convert_rosbag_to_mp4 import select_topic


class SelectTopicTests(unittest.TestCase):
    def test_prefers_raw_color(self):
        topics = {
            "/camera/depth/image_raw": "sensor_msgs/msg/Image",
            "/camera/color/image_raw": "sensor_msgs/msg/Image",
        }
        self.assertEqual(select_topic(topics, "auto")[0], "/camera/color/image_raw")

    def test_explicit_topic(self):
        topics = {"/rgb/compressed": "sensor_msgs/msg/CompressedImage"}
        self.assertEqual(select_topic(topics, "/rgb/compressed"),
                         ("/rgb/compressed", "sensor_msgs/msg/CompressedImage"))

    def test_rejects_missing_image_topic(self):
        with self.assertRaises(ValueError):
            select_topic({"/imu": "sensor_msgs/msg/Imu"}, "auto")


if __name__ == "__main__":
    unittest.main()
