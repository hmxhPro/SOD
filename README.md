# 视频目标检测 Agent

基于 **FastAPI + Grounding DINO + ByteTrack + React** 的视频目标检测系统。  
用户上传视频，通过**自然语言**描述要检测的目标，系统逐帧检测并实时回传结果。

---

## 目录

- [技术方案](#技术方案)
- [项目目录结构](#项目目录结构)
- [各模块职责](#各模块职责)
- [快速启动](#快速启动)
- [API 接口说明](#api-接口说明)
- [示例请求与返回](#示例请求与返回)
- [检测可视化效果](#检测可视化效果)
- [扩展：多 GPU](#扩展多-gpu)
- [扩展：提升吞吐](#扩展提升吞吐)
- [扩展：接入 Redis / Celery](#扩展接入-redis--celery)

---

## 技术方案

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| 后端框架 | **FastAPI** | 异步高性能，原生支持 SSE / WebSocket |
| 检测模型 | **Grounding DINO** | 开放词汇目标检测，自然语言→检测框 |
| 备选模型 | **Florence-2** | 微软多模态大模型，同样支持 OVD |
| 目标跟踪 | **ByteTrack** | 无需重检测的多目标跟踪，大幅降低 GPU 开销 |
| 实时推送 | **Server-Sent Events (SSE)** | 逐帧推送，前端实时刷新 |
| 前端 | **React 18 + Vite** | 快速构建、热更新；Tailwind CSS 样式 |
| 部署环境 | Linux + NVIDIA GPU (CUDA) | 推荐 RTX 3090 / A100 或更高 |

### 检测 + 跟踪流程（速度优先）

```
视频帧序列
    │
    ├── 每隔 N 帧（默认 N=5）→ Grounding DINO 全量检测（GPU）
    │                           ↓
    │                        ByteTrack.update(detections)  ← 分配持久 track_id
    │
    └── 其余帧 → ByteTrack.update(last_detections)  ← Kalman 预测（纯 CPU）
                    ↓
              画框 + 保存 + SSE 推送
```

此策略带来约 **4~8×** 的吞吐提升（取决于 N 值和模型大小）。

---

## 项目目录结构

```
sod/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── upload.py          # POST /api/upload
│   │   │   └── detect.py          # POST /api/detect, GET /api/task, /stream, /download
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic Settings（读 .env）
│   │   │   └── logging.py         # Loguru 日志配置
│   │   ├── models/
│   │   │   └── schemas.py         # 所有 Pydantic 数据模型
│   │   ├── services/
│   │   │   ├── detector.py        # Grounding DINO / Florence-2 检测器抽象
│   │   │   ├── tracker.py         # ByteTrack 封装
│   │   │   ├── visualizer.py      # 框 + 标签绘制、base64 编码
│   │   │   ├── pipeline.py        # 主视频处理流水线
│   │   │   └── task_manager.py    # 任务注册表 + 异步队列
│   │   ├── utils/
│   │   │   └── video_utils.py     # 视频元数据读取、时间戳格式化
│   │   └── main.py                # FastAPI 入口 + 路由注册
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── VideoUploader.jsx  # 拖拽上传组件
│   │   │   ├── PromptInput.jsx    # 自然语言输入框 + 示例
│   │   │   ├── ProgressBar.jsx    # 进度条（上传/检测）
│   │   │   └── ResultViewer.jsx   # 实时帧展示 + 历史缩略图网格
│   │   ├── hooks/
│   │   │   └── useDetectionTask.js # 完整检测工作流 hook（上传→任务→SSE）
│   │   ├── services/
│   │   │   └── api.js             # Axios API 客户端
│   │   ├── App.jsx                # 根组件（左右双栏布局）
│   │   ├── main.jsx
│   │   └── index.css              # Tailwind + 自定义动画
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── example_pro.png                # 目标检测可视化效果参考图
└── Prompt.md                      # 原始需求文档
```

---

## 各模块职责

| 模块 | 职责 |
|------|------|
| `app/main.py` | 创建 FastAPI 实例，注册路由，启动/关闭钩子 |
| `app/core/config.py` | 统一配置（通过 `.env` 注入，支持多环境） |
| `app/api/upload.py` | 流式接收大视频文件，读取元数据，返回 `video_id` |
| `app/api/detect.py` | 创建检测任务、SSE 流、ZIP 下载 |
| `app/services/detector.py` | 封装 Grounding DINO / Florence-2，统一接口 |
| `app/services/tracker.py` | 封装 ByteTrack，提供持久 `track_id` |
| `app/services/visualizer.py` | 绘制高对比度检测框、标签、时间戳 |
| `app/services/pipeline.py` | 主流水线：读帧→检测→跟踪→画框→推送→ZIP |
| `app/services/task_manager.py` | 任务注册表，SSE 异步队列，GPU 并发控制 |
| `app/utils/video_utils.py` | `cv2` 读取视频信息、格式化时间戳 |
| `frontend/hooks/useDetectionTask.js` | 封装完整前端状态机（上传→任务→SSE→结果） |
| `frontend/components/ResultViewer.jsx` | 实时帧大图 + 历史缩略图网格，点击可查看任意帧 |

---

## 快速启动

### 1. 环境准备

```bash
# Python 3.10+，CUDA GPU
python -m venv venv
source venv/bin/activate
```

### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt

# 安装 Grounding DINO（二选一）
# 方式 A：官方源码安装（推荐，获得最新版本）
pip install git+https://github.com/IDEA-Research/GroundingDINO.git

# 方式 B：PyPI 包
pip install groundingdino-py

# 下载 Grounding DINO 权重
mkdir -p models/groundingdino/weights models/groundingdino/config
wget -q https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth \
     -O models/groundingdino/weights/groundingdino_swint_ogc.pth

# 安装 ByteTrack
pip install git+https://github.com/ifzhang/ByteTrack.git
# 或者
pip install bytetracker

# 复制并编辑配置
cp .env.example .env
# 编辑 .env 中 GDINO_CONFIG_PATH、GDINO_CHECKPOINT_PATH 等路径
```

### 3. 启动后端

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
# 访问 http://localhost:8000/docs 查看 Swagger 文档
```

### 4. 安装并启动前端

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

### 5. 使用 Florence-2（可选，替代 Grounding DINO）

编辑 `.env`：

```env
DETECTION_MODEL=florence2
FLORENCE2_MODEL_ID=microsoft/Florence-2-large
```

首次运行会从 HuggingFace 自动下载模型权重（约 1.5GB）。

---

## API 接口说明

### `POST /api/upload`

上传视频文件。

**请求**：`multipart/form-data`，字段 `file`

**响应**：
```json
{
  "video_id": "3f4a1b2c-...",
  "filename": "my_video.mp4",
  "size_bytes": 52428800,
  "duration_seconds": 30.5,
  "fps": 30.0,
  "total_frames": 915
}
```

---

### `POST /api/detect`

创建检测任务（立即返回，后台异步处理）。

**请求体**：
```json
{
  "video_id": "3f4a1b2c-...",
  "prompt": "帮我检测视频中的菜园",
  "detection_interval": 5
}
```

**响应** (`202 Accepted`)：
```json
{
  "task_id": "9a8b7c6d-...",
  "video_id": "3f4a1b2c-...",
  "prompt": "帮我检测视频中的菜园",
  "status": "pending"
}
```

---

### `GET /api/task/{task_id}`

查询任务状态（轮询备用接口）。

**响应**：
```json
{
  "task_id": "9a8b7c6d-...",
  "status": "running",
  "progress": 0.42,
  "total_frames": 915,
  "processed_frames": 385,
  "zip_ready": false,
  "results": [ ... ]
}
```

---

### `GET /api/stream/{task_id}`

Server-Sent Events 流，每处理完一帧推送一条消息。

**事件格式**：

```
data: {"event_type":"frame","task_id":"...","frame_result":{...},"progress":0.1,"processed_frames":10,"total_frames":100}

data: {"event_type":"done","task_id":"...","progress":1.0,"processed_frames":100,"total_frames":100}
```

---

### `GET /api/download/{task_id}`

下载 ZIP 结果包（任务状态为 `finished` 后可用）。

ZIP 内容：
```
results.zip
├── frame_000000_00-00-00-000.jpg
├── frame_000005_00-00-00-167.jpg
├── ...
├── results.json
└── results.csv
```

---

## 示例请求与返回

### cURL 示例

```bash
# 1. 上传视频
VIDEO_ID=$(curl -s -X POST http://localhost:8000/api/upload \
  -F "file=@my_garden.mp4" | jq -r '.video_id')

# 2. 开始检测
TASK_ID=$(curl -s -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d "{\"video_id\":\"$VIDEO_ID\",\"prompt\":\"帮我检测视频中的菜园\"}" \
  | jq -r '.task_id')

# 3. 订阅 SSE 流（实时查看结果）
curl -N http://localhost:8000/api/stream/$TASK_ID

# 4. 任务完成后下载 ZIP
curl -OJ http://localhost:8000/api/download/$TASK_ID
```

### FrameResult 示例

```json
{
  "frame_id": 125,
  "timestamp": "00:00:05.000",
  "timestamp_seconds": 5.0,
  "detections": [
    {
      "track_id": 3,
      "label": "临水菜园",
      "score": 0.847,
      "bbox": { "x1": 120.5, "y1": 80.2, "x2": 640.1, "y2": 350.7 }
    }
  ],
  "image_filename": "frame_000125_00-00-05-000.jpg",
  "image_b64": "/9j/4AAQSkZJRgAB..."
}
```

---

## 检测可视化效果

参考 `example_pro.png`，系统绘制效果：

- ✅ 高对比度矩形框（颜色随 `track_id` 轮换）
- ✅ 框上方：半透明标签背景 + 白色文字（标签 + 置信度）
- ✅ 右下角：时间戳水印（`HH:MM:SS.mmm`）
- ✅ 不同目标使用不同颜色，易于区分

---

## 扩展：多 GPU

当前设计：单 GPU，通过 `asyncio.Semaphore(MAX_CONCURRENT_TASKS)` 控制并发任务数。

### 方案 A：每 GPU 一个 Worker 进程

```bash
# GPU 0
DEVICE=cuda:0 uvicorn app.main:app --port 8000 &

# GPU 1
DEVICE=cuda:1 uvicorn app.main:app --port 8001 &

# Nginx 负载均衡
upstream backends {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
}
```

### 方案 B：Ray 任务调度

```python
import ray
ray.init()

@ray.remote(num_gpus=1)
def detect_on_gpu(video_path, prompt, gpu_id):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    # ... run pipeline
```

### 方案 C：Celery + 多 GPU Worker

见下一节。

---

## 扩展：提升吞吐

| 优化手段 | 预期收益 |
|---------|---------|
| 增大 `DETECTION_INTERVAL` (5→10) | 推理帧数减半，速度提升约 2× |
| 使用 `Florence-2-base` 代替 `-large` | 推理速度提升约 1.5~2×，精度稍降 |
| 使用 TensorRT 量化 Grounding DINO | 推理速度提升约 2~3× |
| 使用 `video/io` 异步解码（NVDEC） | 解码不占 CPU |
| 批量推理（batch > 1） | 对检测帧批量 forward |
| 半精度（fp16）推理 | 速度提升约 1.5×，显存占用减半 |

---

## 扩展：接入 Redis / Celery

1. **安装依赖**

```bash
pip install celery[redis] redis
```

2. **配置**（`.env`）

```env
REDIS_URL=redis://localhost:6379/0
```

3. **定义 Celery 任务**

```python
# app/tasks/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "video_detection",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

@celery_app.task(bind=True)
def run_detection_task(self, task_id, video_path, prompt):
    # 调用 pipeline._sync_pipeline(...)
    ...
```

4. **启动 Worker**

```bash
# GPU 0
DEVICE=cuda:0 celery -A app.tasks.celery_app worker --concurrency=1 -n worker0@%h

# GPU 1
DEVICE=cuda:1 celery -A app.tasks.celery_app worker --concurrency=1 -n worker1@%h
```

5. **修改 API 触发点**

在 `detect.py` 中将 `asyncio.create_task(...)` 替换为：

```python
run_detection_task.delay(task_id, str(video_path), prompt)
```

---

## 测试方法

### 后端单元测试

```bash
cd backend
pytest tests/ -v
```

### 手动端到端测试

```bash
# 准备一个测试视频
wget -O test.mp4 "https://your-test-video-url"

# 运行测试脚本
python -c "
import requests

# 上传
with open('test.mp4', 'rb') as f:
    r = requests.post('http://localhost:8000/api/upload', files={'file': f})
video_id = r.json()['video_id']
print('video_id:', video_id)

# 开始检测
r = requests.post('http://localhost:8000/api/detect', json={
    'video_id': video_id,
    'prompt': '帮我检测视频中的菜园',
})
task_id = r.json()['task_id']
print('task_id:', task_id)

# 轮询状态
import time
while True:
    r = requests.get(f'http://localhost:8000/api/task/{task_id}')
    d = r.json()
    print(f'status={d[\"status\"]} progress={d[\"progress\"]:.0%}')
    if d['status'] in ('finished', 'failed'):
        break
    time.sleep(2)
"
```

---

## 依赖版本要求

| 依赖 | 最低版本 |
|------|---------|
| Python | 3.10 |
| PyTorch | 2.1.0 |
| CUDA | 11.8 |
| FastAPI | 0.111.0 |
| transformers | 4.40.0 |
| groundingdino-py | latest |

---

*构建于开源模型之上，感谢 IDEA Research（Grounding DINO）、Microsoft（Florence-2）、ByteTrack 团队。*
