# AutoCLP

---

## Installation



---

## 项目结构

```
autoclp/
├── config/               # 基础配置
├── core/                 # 核心代码
├── data/                 # 导入的对话文件目录
├── exp_result/           # 一些实验结果的存储目录
├── memory/               # faiss数据库的目录
├── rag/                  # RAG的实现
├── raw/                  # 原始数据集对话数据
├── test/                 # 一些测试脚本
├── test_data/            # 一些测试脚本用的数据
├── test_store/           # 测试用目录
├── utils/                # 辅助工具
├── main.py               # 主流程入口
├── requirements.txt
└── README.md
```

---

## Quick Start

```
python main.py --dialogue=data/1.txt
```

将`1.txt`中的对话传入进行处理

uvicorn server:app --host 0.0.0.0 --port 8000 --reload

---

from ambient import MultimodalAdapter

adapter = MultimodalAdapter()

# CLI模式（从文件读入）
raw = adapter.ingest_from_file(args.dialogue)

# Web模式（从前端API读入）
raw = adapter.ingest_from_string(request.dialogue)

# 批量实验模式（test_record.py）
for raw in adapter.ingest_batch_from_json(f"test_data/2020_{i*100}_{(i+1)*100}_100.txt"):
    time_cost, record = await exp_record(raw.content)

---


