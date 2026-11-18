@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  Push SelfMedia-Agent to GitHub
echo  Remote: https://github.com/quqi-ai/SelfMedia-Agent.git
echo ============================================================
echo.
echo  GitHub 已不再接受账号密码，需要用 Personal Access Token (PAT)。
echo  生成地址: https://github.com/settings/tokens  (勾选 repo 权限)
echo  首次推送时用户名填 GitHub 用户名，密码粘贴 PAT。
echo.
pause
git push -u origin main
echo.
if errorlevel 1 (
    echo 推送失败。请检查网络，或确认 PAT 是否勾选了 repo 权限。
) else (
    echo 推送成功: https://github.com/quqi-ai/SelfMedia-Agent
)
pause
