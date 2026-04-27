# POPO 看板助手

本地看板工具，AI 从 POPO 聊天记录中识别任务，统一管理。

## 快速启动

### 1. 安装依赖

```bash
cd ~/Projects/popo-task-kanban
pip install -r requirements.txt
```

### 2. 启动服务

OpenClaw Gateway 会自动注入 AI 配置（OPENCLAW_GATEWAY_URL / OPENCLAW_GATEWAY_TOKEN 环境变量），直接运行即可：

```bash
python app.py
```

启动成功后打开浏览器访问：

```
http://localhost:5151
```

### 3. 配置模型（可选）

默认使用 `gpt-4o`，可通过环境变量修改：

```bash
export MODEL="minimax-portal/MiniMax-M2.7-highspeed"
python app.py
```

## 功能说明

### AI 识别任务
1. 顶部文本框粘贴 POPO 聊天记录
2. 点击「🔍 AI 识别」
3. 逐条确认或一键批量确认
4. 任务自动进入「待办」列

### 看板操作
- 点击任务卡片 → 编辑详情（标题/详情/截止时间/优先级/来源）
- ✓ 按钮 → 标记完成（自动移入「已完成」列）
- ↩ 按钮 → 重新激活
- 鼠标悬停显示删除按钮

## 项目结构

```
popo-task-kanban/
├── app.py              # Flask 后端
├── kanban.db           # SQLite 数据库（自动创建）
├── templates/
│   └── index.html      # 前端看板页面
└── requirements.txt    # Python 依赖
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/tasks | 获取所有任务 |
| GET | /api/tasks/:id | 获取单个任务 |
| POST | /api/tasks | 创建任务 |
| PUT | /api/tasks/:id | 更新任务 |
| DELETE | /api/tasks/:id | 删除任务 |
| POST | /api/tasks/batch | 批量创建任务 |
| POST | /api/analyze | AI 分析聊天文本 |

---

## 🚀 部署到阿里云服务器

### 前置条件

- 阿里云服务器（Ubuntu 24.04）
- Docker 和 Docker Compose 已安装
- OpenClaw Gateway 已部署（默认端口 18789）

### 1. 上传代码到服务器

```bash
# 在本地打包代码（排除无关文件）
cd ~/Projects/popo-task-kanban
tar -czf popo-task-kanban.tar.gz --exclude='.venv' --exclude='venv' --exclude='__pycache__' --exclude='tasks.json' --exclude='kanban.db' --exclude='*.log' --exclude='*.err' .

# 上传到服务器
scp popo-task-kanban.tar.gz root@47.97.0.89:/opt/

# 在服务器上解压
ssh root@47.97.0.89
mkdir -p /opt/popo-task-kanban
cd /opt/popo-task-kanban
tar -xzf /opt/popo-task-kanban.tar.gz
```

### 2. 配置环境变量

```bash
# 创建 .env 文件
cat > .env << 'EOF'
OPENCLAW_GATEWAY_TOKEN=你的OpenClaw Gateway Token
EOF
```

### 3. 启动服务

```bash
cd /opt/popo-task-kanban
docker-compose up -d
```

### 4. 验证部署

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 测试访问
curl http://localhost:5151/api/tasks
```

访问 `http://47.97.0.89:5151` 即可使用看板。

---

## 🔧 环境变量说明

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PORT` | `5151` | 服务端口 |
| `FLASK_ENV` | `development` | 设为 `production` 关闭 debug |
| `DATA_DIR` | 项目目录 | 数据库存储目录 |
| `CORS_ORIGINS` | `*` | CORS 允许的域名，逗号分隔 |
| `OPENCLAW_GATEWAY_URL` | `http://localhost:18789` | OpenClaw Gateway 地址 |
| `OPENCLAW_GATEWAY_TOKEN` | 空 | OpenClaw Gateway Token |
| `MODEL` | `gpt-4o` | AI 模型名称 |

---

## 🐳 Docker 常用命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 重新构建并启动
docker-compose up -d --build
```
