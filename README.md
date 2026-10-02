# OWLv2 + Intel RealSense + Jetson AGX Orin

Thư mục này là bộ chạy sẵn theo `KE_HOACH_THU_NGHIEM_OWLV2_CAMERA_GPU.md`. Pipeline dùng **OWLv2 Base Patch16 Ensemble**, ảnh màu RealSense và CUDA trên Jetson. Mã không train/fine-tune model.

Nếu bắt đầu từ một máy mới, xem hướng dẫn từng bước tại [`HUONG_DAN_CHAY_TU_DAU.md`](HUONG_DAN_CHAY_TU_DAU.md), bao gồm vị trí đặt video và lưu ý với ROS 2 bag `.db3`.

Repository có sẵn `scripts/convert_rosbag_to_mp4.py` để xuất topic ảnh màu từ ROS 2 bag `.db3` sang MP4 trước khi chạy OWLv2.

## Chạy nhanh

Các lệnh bên dưới đều chạy từ thư mục này:

```bash
cd /home/lyonel/Documents/analysis_VD/real_room_owlv2
```

### 1. Chuẩn bị môi trường trên Jetson

PyTorch/torchvision phải là bản tương thích với JetPack đang cài. Nên cài wheel NVIDIA dành cho đúng phiên bản JetPack trước; sau đó cài các gói còn lại. `pyrealsense2` nên được cài cùng librealsense theo cách phù hợp với Jetson.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# Cài torch + torchvision tương thích JetPack tại đây trước nếu máy chưa có.
python -m pip install numpy opencv-python Pillow 'transformers>=4.40,<5'
```

Nếu torch/torchvision phù hợp đã có sẵn trong môi trường Python, có thể dùng:

```bash
python -m pip install -r requirements.txt
```

Kiểm tra thiết bị và lưu snapshot vào `hardware.json`:

```bash
python scripts/check_hardware.py
```

Chỉ benchmark khi báo cáo cho thấy `cuda_available: true`, có RealSense và `usb_type` bắt đầu bằng `3`.

### 2. Sửa inventory và prompt

- Điền vật thật trong phòng vào `inventory/room_inventory.csv`.
- Sửa `prompts/prompts_v1.txt`, mỗi dòng một class tiếng Anh.
- Chưa thêm hàng loạt synonym ở v1.
- Có thể chỉnh threshold/NMS/precision/profile camera trong `configs/default.json`.

### 3. Ghi hai video gốc

File đã tồn tại sẽ **không bị ghi đè**. Mặc định camera warm-up 3 giây.

```bash
python scripts/record_room.py --name room_val --duration 60 --preview
python scripts/record_room.py --name room_test --duration 60 --preview
```

Trên máy headless/SSH, bỏ `--preview`. Video và metadata camera được lưu tại `videos/`.

### 4. Baseline trên room_val

Lần đầu model sẽ tải checkpoint Hugging Face, vì vậy Jetson cần Internet hoặc model phải có sẵn trong cache.

```bash
python scripts/evaluate_recording.py \
  --video videos/room_val_raw.mp4 \
  --phase val_v1 \
  --prompts prompts/prompts_v1.txt
```

Mỗi lần chạy tạo thư mục mới trong `runs/<run_id>/`, gồm cấu hình, prompt snapshot, video gốc, video bbox, `detections.csv` và `frame_metrics.csv`. Có 10 lượt warm-up mặc định; latency không tính tải model.

### 5. Thêm synonym rồi chạy lại đúng video val

Sửa `prompts/prompts_v2.txt` và ánh xạ synonym về canonical class trong `prompts/synonym_mapping.csv`, sau đó:

```bash
python scripts/evaluate_recording.py \
  --video videos/room_val_raw.mp4 \
  --phase val_v2 \
  --prompts prompts/prompts_v2.txt
```

So sánh v1/v2, chọn threshold bằng `room_val`, rồi khóa `configs/default.json`, `prompts_v2.txt` và `synonym_mapping.csv`. Không sửa chúng sau khi xem `room_test`.

### 6. Đánh giá cuối trên room_test

```bash
python scripts/evaluate_recording.py \
  --video videos/room_test_raw.mp4 \
  --phase test \
  --prompts prompts/prompts_v2.txt
```

### 7. Tạo báo cáo HTML

```bash
python scripts/build_report.py
```

Báo cáo nằm ở `report/real_room_owlv2_report.html`. Báo cáo tự động tổng hợp detection và timing; TP/FP/FN/recall cần ground truth hoặc đối chiếu inventory nên không được tự suy diễn từ prediction.

## Chạy live camera

```bash
python scripts/live_demo.py --prompts prompts/prompts_v1.txt --save-raw
```

Nhấn `q` để dừng. Khi chạy SSH không có màn hình:

```bash
python scripts/live_demo.py --prompts prompts/prompts_v1.txt --headless --duration 60 --save-raw
```

Capture và inference chạy riêng. Queue tối đa 2 frame; khi inference chậm, frame cũ bị bỏ để không tích lũy độ trễ. `frame_metrics.csv` ghi số frame capture, processed, dropped, queue size, model latency, end-to-end latency và bộ nhớ CUDA.

## Thử nhanh trước khi chạy đầy đủ

Chạy unit test không cần model/camera:

```bash
python -m unittest discover -s tests -v
```

Chạy đúng 5 frame để kiểm tra model/video:

```bash
python scripts/evaluate_recording.py \
  --video videos/room_val_raw.mp4 --phase val_v1 \
  --prompts prompts/prompts_v1.txt --max-frames 5
```

## Cấu trúc kết quả và lưu ý

- `runs/<run_id>/original.mp4`: bản sao video đầu vào của run offline, hoặc video capture nếu live có `--save-raw`.
- `runs/<run_id>/overlay.mp4`: video có bbox.
- `detections.csv`: đúng schema detection trong kế hoạch.
- `frame_metrics.csv`: timing/frame drop/memory theo frame.
- `config.json`: model, prompt, tensor shape, phần mềm và thống kê mean/median/p95/std.
- `events.csv`: sự kiện bắt đầu run live.

`allocated_vram_mb` là số bộ nhớ CUDA do PyTorch cấp phát, hữu ích để so run nhưng không đại diện toàn bộ unified memory của Jetson. Dùng thêm `tegrastats` hoặc `jtop` khi cần peak RAM/công suất toàn hệ thống. Video offline được copy vào mỗi run để bảo toàn khả năng tái lập; nếu video dài và thiếu dung lượng, có thể xóa bản sao sau khi đã kiểm tra checksum, nhưng không xóa video gốc trong `videos/`.

## Lỗi thường gặp

- **CUDA false:** torch không đúng bản JetPack hoặc đang dùng môi trường sai.
- **Không thấy RealSense:** kiểm tra cáp/cổng USB 3.x, `rs-enumerate-devices`, quyền udev và librealsense.
- **`torchvision::nms` lỗi:** mã tự fallback sang sắp xếp score; nên cài torchvision khớp torch để có class-aware NMS đúng cấu hình.
- **Không mở được cửa sổ:** dùng `--headless` hoặc bỏ `--preview` qua SSH.
- **Không ghi được MP4:** kiểm tra OpenCV/codec; bảo đảm thư mục còn dung lượng.
