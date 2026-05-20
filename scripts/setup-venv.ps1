# 自动创建 Python 虚拟环境并安装 backend 依赖
# 由根目录 package.json 的 postinstall 钩子触发，也可手动跑: pnpm setup:venv

$ErrorActionPreference = "Stop"

# 切换到脚本所在目录的上一级（项目根目录），确保相对路径正确
$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location $rootDir

# 1. 检查 Python 是否存在
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[setup] 未找到 python 命令，请先安装 Python 3.10+ 并加入 PATH" -ForegroundColor Red
    exit 1
}

# 2. 创建 venv（已存在则跳过）
if (-not (Test-Path ".venv")) {
    Write-Host "[setup] 创建 Python 虚拟环境 .venv ..." -ForegroundColor Green
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[setup] 创建虚拟环境失败" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[setup] .venv 已存在，跳过创建" -ForegroundColor Yellow
}

# 3. 安装 backend 依赖（用清华源加速）
Write-Host "[setup] 安装 Python 依赖（约 2-3 分钟，请耐心等待）..." -ForegroundColor Green
& ".\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    Write-Host "[setup] pip install 失败，可手动重跑: pnpm setup:venv" -ForegroundColor Red
    exit 1
}

# 4. 自动创建 backend/.env（如果不存在）
if (-not (Test-Path "backend\.env")) {
    if (Test-Path "backend\.env.example") {
        Copy-Item "backend\.env.example" "backend\.env"
        Write-Host "[setup] 已生成 backend\.env，请填入自己的 API Key" -ForegroundColor Yellow
    }
}

Write-Host "[setup] 完成 现在可以运行 pnpm dev 启动项目" -ForegroundColor Green