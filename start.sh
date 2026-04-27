#!/bin/zsh
cd ~/Projects/popo-task-kanban
source venv/bin/activate
nohup python3 app.py > app.log 2>&1 &
echo "✅ 看板已启动 (PID: $!)"
echo "访问地址: http://localhost:5151"
echo "日志: ~/Projects/popo-task-kanban/app.log"
echo "停止: kill $!"
