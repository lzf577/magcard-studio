@echo off
chcp 65001 >nul
title 超市会员卡管理系统 - EXE打包工具
echo ==================================================
echo   超市会员卡管理系统 - 一键打包为 Windows EXE
echo ==================================================
echo.
echo [1/3] 正在检查并安装 PyInstaller 打包工具...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo.
    echo [错误] 安装 PyInstaller 失败，请检查网络连接或 Python 环境。
    pause
    exit /b
)

echo.
echo [2/3] 正在打包为单文件无黑框 EXE，请稍候约半分钟...
pyinstaller -F -w --clean --name "超市会员卡读写系统" GUI.py
if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包过程中出现错误，请查看上方提示。
    pause
    exit /b
)

echo.
echo [3/3] 打包完成！正在复制到当前目录...
if exist "dist\超市会员卡读写系统.exe" (
    copy /y "dist\超市会员卡读写系统.exe" ".\超市会员卡读写系统.exe" >nul
    echo.
    echo ==================================================
    echo  🎉 恭喜！打包成功！
    echo  可执行程序已生成在当前目录：
    echo  ▶ 超市会员卡读写系统.exe
    echo  (可单独复制到任意电脑双击运行，无需安装Python)
    echo ==================================================
) else (
    echo 请在 dist 文件夹下查看生成的 exe。
)

echo.
pause
