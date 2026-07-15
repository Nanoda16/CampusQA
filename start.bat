@echo off
chcp 65001 >nul 2>&1
title CampusQA 一键启动

echo ============================================
echo   CampusQA 河海大学校园问答助手
echo   后端: http://localhost:8002
echo   前端: http://localhost:5173
echo ============================================
echo.

echo [1/3] 启动后端...
start "CampusQA-Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8002"

echo [2/3] 启动前端...
start "CampusQA-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo [3/3] 等待服务就绪后打开浏览器...
timeout /t 8 /nobreak >nul
start http://localhost:5173

echo.
echo ============================================
echo   启动完成！浏览器已打开
echo   关闭后端/前端窗口即可停止服务
echo ============================================
pause