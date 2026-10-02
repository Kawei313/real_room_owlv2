# Hướng dẫn chạy OWLv2 từ đầu

Tài liệu này hướng dẫn toàn bộ quy trình từ lúc tải mã nguồn đến khi có video gắn bounding box và báo cáo. Các lệnh được chạy trên **Jetson AGX Orin** có camera Intel RealSense kết nối USB 3.x.

## 1. Tải mã nguồn

```bash
git clone https://github.com/Kawei313/real_room_owlv2.git
cd real_room_owlv2
```

Cấu trúc dữ liệu quan trọng:

```text
real_room_owlv2/
├── videos/
│   ├── room_val_raw.mp4       # video dùng chọn prompt/threshold
│   └── room_test_raw.mp4      # video đánh giá cuối
├── prompts/
│   ├── prompts_v1.txt
│   ├── prompts_v2.txt
│   └── synonym_mapping.csv
├── inventory/
├── configs/default.json
├── runs/                      # kết quả mỗi lần chạy
└── report/                    # báo cáo HTML
```

Video không được đưa lên GitHub vì `.gitignore` đã chặn các file dữ liệu lớn.

## 2. Cài môi trường

Kiểm tra Python:

```bash
python3 --version
```

Tạo môi trường ảo:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Trên Jetson, cần cài **PyTorch và torchvision tương thích đúng phiên bản JetPack** trước. Không nên cài ngẫu nhiên wheel CUDA dành cho máy tính desktop. Sau khi PyTorch hoạt động, cài các thư viện còn lại:

```bash
python -m pip install numpy opencv-python Pillow 'transformers>=4.40,<5'
```

`pyrealsense2`/librealsense cần được cài theo phiên bản JetPack và Ubuntu trên Jetson.

Kiểm tra CUDA:

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'Không có CUDA'); print('PyTorch CUDA:', torch.version.cuda)"
```

Kết quả bắt buộc phải có `CUDA: True` trước khi benchmark.

## 3. Kiểm tra Jetson và camera

Cắm RealSense trực tiếp vào cổng USB 3.x của Jetson rồi chạy:

```bash
python scripts/check_hardware.py
```

Chương trình tạo `hardware.json`. Kiểm tra:

- `cuda_available` là `true`.
- Có tên, serial và firmware RealSense.
- `usb_type` bắt đầu bằng `3`.
- Không có lỗi camera.

Nếu có giao diện màn hình, nên mở `realsense-viewer` để kiểm tra hình ảnh, exposure và profile `1280×720 @ 30 FPS` trước.

## 4. Chuẩn bị inventory và prompt

Mở `inventory/room_inventory.csv` và thay dữ liệu mẫu bằng danh sách vật thật trong phòng:

```csv
object_id,canonical_class,location,priority
chair_01,chair,near main desk,high
monitor_01,monitor,on main desk,high
```

Mở `prompts/prompts_v1.txt`, mỗi dòng ghi một class tiếng Anh:

```text
chair
monitor
keyboard
bottle
```

Không thêm quá nhiều synonym vào v1 vì mục tiêu là so sánh trước và sau khi bổ sung prompt.

## 5. Video phải để ở đâu?

Nếu đã có hai video MP4, chép hoặc đổi tên chúng thành:

```text
videos/room_val_raw.mp4
videos/room_test_raw.mp4
```

Ví dụ:

```bash
cp /đường/dẫn/video-thử-prompt.mp4 videos/room_val_raw.mp4
cp /đường/dẫn/video-đánh-giá.mp4 videos/room_test_raw.mp4
```

- `room_val_raw.mp4`: được phép xem kết quả rồi sửa prompt/threshold.
- `room_test_raw.mp4`: chỉ chạy sau khi đã khóa cấu hình; không sửa prompt dựa trên kết quả test.

Không dùng cùng một video cho cả `val` và `test`.

### Nếu chưa có video MP4

Ghi trực tiếp từ RealSense:

```bash
python scripts/record_room.py --name room_val --duration 60 --preview
python scripts/record_room.py --name room_test --duration 60 --preview
```

Qua SSH không có màn hình, bỏ `--preview`:

```bash
python scripts/record_room.py --name room_val --duration 60
python scripts/record_room.py --name room_test --duration 60
```

### Nếu video đang là file `.db3`

File `.db3` thường là dữ liệu ROS 2 bag, không phải video MP4 mà OpenCV có thể đọc trực tiếp. Một ROS 2 bag đầy đủ thường gồm:

```text
thu_muc_bag/
├── metadata.yaml
└── 20261002_144653.db3
```

Không đặt `.db3` trực tiếp vào `videos/room_val_raw.mp4` và không chỉ đổi phần mở rộng. Cần phát lại bag và xuất topic ảnh màu thành MP4 trước, sau đó đặt MP4 vào `videos/`. Đồng thời phải giữ `metadata.yaml`; chỉ có riêng `.db3` có thể không đủ để `ros2 bag play` nhận dạng bag.

Kiểm tra bag:

```bash
ros2 bag info /đường/dẫn/thu_muc_bag
```

Tên topic ảnh tùy cấu hình RealSense, thường gần giống `/camera/camera/color/image_raw`. Sau khi xuất được ảnh màu thành MP4, dùng MP4 đó cho pipeline OWLv2.

## 6. Kiểm tra nhanh 5 frame

Lần đầu chạy, Transformers sẽ tải checkpoint `google/owlv2-base-patch16-ensemble`. Jetson cần Internet hoặc checkpoint phải có trong cache.

```bash
python scripts/evaluate_recording.py \
  --video videos/room_val_raw.mp4 \
  --phase val_v1 \
  --prompts prompts/prompts_v1.txt \
  --max-frames 5
```

Nếu lệnh hoàn thành, kiểm tra thư mục mới trong `runs/`. Mỗi lần chạy có `run_id` riêng và không ghi đè kết quả cũ.

## 7. Chạy baseline trên toàn bộ room_val

```bash
python scripts/evaluate_recording.py \
  --video videos/room_val_raw.mp4 \
  --phase val_v1 \
  --prompts prompts/prompts_v1.txt
```

Kết quả nằm trong:

```text
runs/<run_id>/
├── config.json
├── prompts_v1.txt
├── original.mp4
├── overlay.mp4
├── detections.csv
└── frame_metrics.csv
```

Mở `overlay.mp4` để xem bbox. Dùng `detections.csv` và inventory để ghi vật phát hiện đúng, miss và false positive.

## 8. Thêm synonym và chạy val_v2

Sao chép/giữ toàn bộ class cần thiết trong `prompts/prompts_v2.txt`, rồi thêm synonym. Ví dụ:

```text
power strip
extension socket
extension cord
```

Ánh xạ chúng về cùng canonical class trong `prompts/synonym_mapping.csv`:

```csv
prompt,canonical_class
power strip,power strip
extension socket,power strip
extension cord,power strip
```

Chạy lại **đúng video room_val cũ**:

```bash
python scripts/evaluate_recording.py \
  --video videos/room_val_raw.mp4 \
  --phase val_v2 \
  --prompts prompts/prompts_v2.txt
```

So sánh v1 và v2. Có thể điều chỉnh `threshold`, `nms_iou`, `max_detections` và `precision` trong `configs/default.json` dựa trên `room_val`.

## 9. Khóa cấu hình và chạy room_test

Trước khi chạy test, không chỉnh tiếp:

- `configs/default.json`.
- `prompts/prompts_v2.txt`.
- `prompts/synonym_mapping.csv`.
- Model và phiên bản thư viện.

Chạy test:

```bash
python scripts/evaluate_recording.py \
  --video videos/room_test_raw.mp4 \
  --phase test \
  --prompts prompts/prompts_v2.txt
```

Không thay đổi cấu hình sau khi xem kết quả test. Nếu cần thay đổi, tạo một phiên bản thí nghiệm mới.

## 10. Tạo báo cáo

```bash
python scripts/build_report.py
```

Mở:

```text
report/real_room_owlv2_report.html
```

Báo cáo tự động tổng hợp latency, FPS, memory và số detection. Precision/recall/TP/FP/FN cần annotation hoặc đối chiếu inventory, không thể tính chính xác chỉ từ prediction.

## 11. Chạy live camera tùy chọn

Có màn hình:

```bash
python scripts/live_demo.py --prompts prompts/prompts_v1.txt --save-raw
```

Qua SSH/headless:

```bash
python scripts/live_demo.py \
  --prompts prompts/prompts_v1.txt \
  --headless --duration 60 --save-raw
```

Nhấn `q` hoặc `Ctrl+C` để dừng. Live mode dùng queue tối đa 2 frame và bỏ frame cũ khi model chậm hơn camera.

## 12. Chạy unit test

```bash
python -m unittest discover -s tests -v
```

Các test này không cần camera hoặc GPU.

## 13. Cập nhật code từ GitHub

```bash
git pull origin main
```

Video, model, môi trường ảo, `hardware.json`, `runs/` và báo cáo sinh ra không được đẩy lên GitHub. Muốn sao lưu kết quả lớn, hãy dùng Google Drive hoặc kho lưu trữ dữ liệu riêng.
