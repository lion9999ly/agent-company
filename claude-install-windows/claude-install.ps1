# ============================================
# Claude Code 一键安装脚本 (Windows)
# ============================================
#
# 无需代理，国内直连安装
#
# 使用方法：
#   .\claude-install.ps1 --anthropic-api-key sk-xxx
#   .\claude-install.ps1 --anthropic-api-key sk-xxx --anthropic-model MiniMax-M2.5
#   .\claude-install.ps1 --anthropic-api-key sk-xxx --anthropic-base-url https://xxx
#   .\claude-install.ps1 --restore
#   .\claude-install.ps1 --restore --restore-dir ~\claude_origin_config_xxx
#   （参数名大小写不敏感）
#
# 支持模型：
#   glm-5, glm-4.7, MiniMax-M2.5, k2.5 等
#
# ============================================

# ==================== 参数解析（手动，支持 -- 前缀与大小写不敏感）====================
$ANTHROPIC_API_KEY = ""
$ANTHROPIC_BASE_URL = "https://dashscope.aliyuncs.com/apps/anthropic"
$ANTHROPIC_MODEL    = "glm-5"
$Restore    = $false
$RestoreDir = ""

$i = 0
while ($i -lt $args.Count) {
    switch ($args[$i].ToLower()) {
        "--anthropic-api-key"  { $ANTHROPIC_API_KEY  = $args[$i+1]; $i += 2; break }
        "--anthropic-base-url" { $ANTHROPIC_BASE_URL = $args[$i+1]; $i += 2; break }
        "--anthropic-model"    { $ANTHROPIC_MODEL    = $args[$i+1]; $i += 2; break }
        "--restore"            { $Restore    = $true;         $i += 1; break }
        "--restore-dir"        { $RestoreDir = $args[$i+1];   $i += 2; break }
        "--help" {
            Write-Host ""
            Write-Host "用法: .\claude-install.ps1 --anthropic-api-key API_KEY [选项]" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "  --anthropic-api-key   (必填) API Key"
            Write-Host "  --anthropic-base-url  Base URL（默认: https://dashscope.aliyuncs.com/apps/anthropic）"
            Write-Host "  --anthropic-model     模型名称（默认: glm-5）"
            Write-Host "  --restore             还原安装前的原始 Claude 配置"
            Write-Host "  --restore-dir DIR     指定要还原的备份目录（默认使用最早的备份）"
            Write-Host "  --help                显示此帮助"
            Write-Host ""
            Write-Host "示例:"
            Write-Host "  .\claude-install.ps1 --anthropic-api-key sk-xxx"
            Write-Host "  .\claude-install.ps1 --anthropic-api-key sk-xxx --anthropic-model glm-5"
            Write-Host "  .\claude-install.ps1 --restore"
            Write-Host "  .\claude-install.ps1 --restore --restore-dir ~\claude_origin_config_<时间戳>"
            Write-Host ""
            Write-Host "  支持模型: glm-5, glm-4.7, MiniMax-M2.5, k2.5 等"
            Write-Host "  参数名大小写不敏感，以下写法均有效："
            Write-Host "    --anthropic-api-key  --ANTHROPIC-API-KEY  --Anthropic-Api-Key"
            Write-Host ""
            exit 0
            break
        }
        default { Write-Host "[ERR] 未知参数: $($args[$i])" -ForegroundColor Red; exit 1 }
    }
}

# ==================== 默认配置 ====================
# 版本配置（默认安装最新版，如需指定版本：NODE_VERSION="24.11.1", CLAUDE_VERSION="2.1.63"）
$NODE_VERSION = "lts"                                   # nvm install 的版本号，"lts" 为最新长期支持版
$CLAUDE_VERSION = ""                                    # claude-code 版本号，留空安装最新版

# ==================== 编码设置 ====================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

# ==================== 输出函数 ====================
function Write-Ok   { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Err  { param([string]$Msg) Write-Host "[ERR] $Msg" -ForegroundColor Red }
function Write-Info { param([string]$Msg) Write-Host "[INFO] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[WARN] $Msg" -ForegroundColor Yellow }

function Write-Banner {
    param([string]$Title)
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Magenta
    Write-Host " $Title" -ForegroundColor Magenta
    Write-Host "===========================================" -ForegroundColor Magenta
    Write-Host ""
}

# ==================== 7z 解压工具 ====================
# 启动时从同级目录的 7z-*-x64.zip 解压出 7z.exe，之后统一用它处理所有格式
$script:7zExe = ""

function Init-7zip {
    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
    $7zZip = Get-ChildItem -Path $scriptDir -Filter "7z-*-x64.zip" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $7zZip) {
        Write-Warn "未找到 7z 离线包，将使用 PowerShell 原生解压"
        return
    }
    $7zDir = "$env:TEMP\7z-bundle"
    if (Test-Path $7zDir) { Remove-Item $7zDir -Recurse -Force }
    Expand-Archive -Path $7zZip.FullName -DestinationPath $7zDir -Force
    # 优先找 7za.exe（独立版），其次 7z.exe（需配合 7z.dll）
    $exe = Get-ChildItem -Path $7zDir -Filter "7z*.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -imatch '^7z[ar]?\.exe$' } |
        Sort-Object Name | Select-Object -First 1
    if ($exe) {
        $script:7zExe = $exe.FullName
        Write-Ok "7z 已就绪: $($exe.Name) ($($7zZip.Name))"
    } else {
        Write-Warn "7z 可执行文件未找到，将使用 PowerShell 原生解压"
    }
}

function Invoke-Extract {
    param([string]$Archive, [string]$Destination)
    if ($script:7zExe -and (Test-Path $script:7zExe)) {
        & $script:7zExe x $Archive -o"$Destination" -y | Out-Null
    } else {
        Expand-Archive -Path $Archive -DestinationPath $Destination -Force
    }
}

# ==================== 刷新环境变量 ====================
function Refresh-Env {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    # NVM 环境变量可能在 User 或 Machine 级别
    $env:NVM_HOME = [System.Environment]::GetEnvironmentVariable("NVM_HOME","User")
    if (-not $env:NVM_HOME) { $env:NVM_HOME = [System.Environment]::GetEnvironmentVariable("NVM_HOME","Machine") }
    $env:NVM_SYMLINK = [System.Environment]::GetEnvironmentVariable("NVM_SYMLINK","User")
    if (-not $env:NVM_SYMLINK) { $env:NVM_SYMLINK = [System.Environment]::GetEnvironmentVariable("NVM_SYMLINK","Machine") }
}

# ==================== 加速下载 ====================
# PowerShell 5.1 的 Invoke-WebRequest 进度条会严重拖慢下载速度
$ProgressPreference = 'SilentlyContinue'

# ==================== 清除代理 ====================
function Clear-Proxy {
    $env:HTTP_PROXY = $null
    $env:HTTPS_PROXY = $null
    $env:http_proxy = $null
    $env:https_proxy = $null
    $env:ALL_PROXY = $null
    $env:all_proxy = $null
}

# ==================== 1. 安装 nvm ====================
function Install-Nvm {
    Write-Banner "安装 nvm"

    # 已有 node >= 18 则跳过 nvm 安装
    try {
        $nodeVer = node --version 2>$null
        if ($nodeVer) {
            $major = [int]($nodeVer -replace '^v','').Split('.')[0]
            if ($major -ge 18) {
                Write-Ok "Node.js 已安装: $nodeVer，跳过 nvm 安装"
                return $true
            }
        }
    } catch {}

    # 已有 nvm 则跳过安装
    $nvmInstalled = $false
    try {
        $nvmVer = nvm version 2>$null
        if ($nvmVer) {
            $nvmInstalled = $true
            Write-Ok "nvm-windows 已安装: $nvmVer，跳过安装"
        }
    } catch {}

    if (-not $nvmInstalled) {
        # 检查是否已安装但未生效（User 或 Machine 级别）
        $nvmHome = [System.Environment]::GetEnvironmentVariable("NVM_HOME","User")
        if (-not $nvmHome) {
            $nvmHome = [System.Environment]::GetEnvironmentVariable("NVM_HOME","Machine")
        }
        if ($nvmHome) {
            Write-Warn "检测到 nvm-windows 已安装但命令不可用"
            Write-Info "请关闭 PowerShell 重新打开后再运行此脚本"
            return $false
        }

        # 使用 noinstall 免安装版（无需管理员权限）
        Write-Info "安装 nvm-windows（免安装版，无需管理员权限）..."

        # 若用户名含空格，nvm.exe 无法处理含空格的路径（settings.txt root/path 均有问题），改用固定无空格路径
        if ($env:USERPROFILE -match ' ') {
            $nvmDir     = "C:\nvm"
            $nvmSymlink = "C:\nodejs"
            Write-Warn "检测到用户目录含空格，nvm 将安装到 $nvmDir，nodejs symlink 将使用 $nvmSymlink"
        } else {
            $nvmDir     = "$env:USERPROFILE\nvm"
            $nvmSymlink = "$env:USERPROFILE\nodejs"
        }
        $zipFile = "$env:TEMP\nvm-noinstall-windows.zip"
        $nvmUrl = "https://github.com/coreybutler/nvm-windows/releases/download/1.2.2/nvm-noinstall-windows.zip"

        # 优先检查脚本同级目录的离线包，再尝试在线下载
        $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
        $localZip = Join-Path $scriptDir "nvm-noinstall-windows.zip"

        if (Test-Path $localZip) {
            Write-Info "检测到脚本同级目录的离线包: $localZip"
            Copy-Item $localZip $zipFile -Force
            Write-Ok "使用离线包"
        } else {
            try {
                Write-Info "下载 nvm-noinstall-windows.zip（GitHub）..."
                Invoke-WebRequest -Uri $nvmUrl -OutFile $zipFile -UseBasicParsing -ErrorAction Stop
                Write-Ok "下载完成（GitHub）"
            } catch {
                Write-Err "nvm-windows 下载失败"
                Write-Info "请手动下载 nvm-noinstall-windows.zip 放到脚本同级目录，或访问: https://github.com/coreybutler/nvm-windows/releases"
                return $false
            }
        }

        # 解压
        try {
            if (Test-Path $nvmDir) { Remove-Item $nvmDir -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $nvmDir | Out-Null
            Invoke-Extract -Archive $zipFile -Destination $nvmDir
            Remove-Item $zipFile -Force -ErrorAction SilentlyContinue
            Write-Ok "解压到 $nvmDir"
        } catch {
            Write-Err "解压失败: $_"
            return $false
        }

        # 写入 settings.txt
        $nvmSettings = @"
root: $nvmDir
path: $nvmSymlink
arch: 64
proxy: none
"@
        $nvmSettings | Out-File -FilePath "$nvmDir\settings.txt" -Encoding ascii -Force
        Write-Ok "nvm settings.txt 已配置"

        # 确保 symlink 目标路径不存在（nvm use 需要自己创建 junction）
        if (Test-Path $nvmSymlink) {
            Remove-Item $nvmSymlink -Recurse -Force -ErrorAction SilentlyContinue
        }

        # 设置用户级环境变量
        [System.Environment]::SetEnvironmentVariable("NVM_HOME", $nvmDir, "User")
        [System.Environment]::SetEnvironmentVariable("NVM_SYMLINK", $nvmSymlink, "User")

        # 添加到用户 PATH
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $pathsToAdd = @($nvmDir, $nvmSymlink)
        foreach ($p in $pathsToAdd) {
            if ($userPath -notlike "*$p*") {
                $userPath = "$p;$userPath"
            }
        }
        [System.Environment]::SetEnvironmentVariable("Path", $userPath, "User")

        # 当前会话生效
        $env:NVM_HOME = $nvmDir
        $env:NVM_SYMLINK = $nvmSymlink
        $env:Path = "$nvmDir;$nvmSymlink;" + $env:Path

        Write-Ok "nvm-windows 免安装版配置完成"

        # 验证 nvm
        try {
            $nvmVer = & "$nvmDir\nvm.exe" version 2>$null
            if ($nvmVer) {
                Write-Ok "nvm 版本: $nvmVer"
                $nvmInstalled = $true
            }
        } catch {}

        if (-not $nvmInstalled) {
            Write-Err "nvm 安装后无法使用"
            return $false
        }
    }

    return $true
}

# ==================== 2. 安装 Node.js ====================
function Install-Node {
    Write-Banner "安装 Node.js"

    # 已有 node >= 18 则跳过
    try {
        $nodeVer = node --version 2>$null
        if ($nodeVer) {
            $major = [int]($nodeVer -replace '^v','').Split('.')[0]
            if ($major -ge 18) {
                Write-Ok "Node.js 已安装: $nodeVer，跳过安装"
                return $true
            }
        }
    } catch {}

    # 优先检查脚本同级目录的离线 Node.js zip
    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
    $localNodeZip = Get-ChildItem -Path $scriptDir -Filter "node-v*-win-x64.zip" -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($localNodeZip) {
        # 从文件名提取版本号，如 node-v22.22.0-win-x64.zip -> 22.22.0
        $localVer = $localNodeZip.Name -replace '^node-v',''-replace '-win-x64\.zip$',''
        Write-Info "检测到离线 Node.js 包: $($localNodeZip.Name)"

        $nvmHome = $env:NVM_HOME
        if (-not $nvmHome) { $nvmHome = "$env:USERPROFILE\nvm" }
        $nodeInstallDir = "$nvmHome\v$localVer"

        try {
            if (Test-Path $nodeInstallDir) { Remove-Item $nodeInstallDir -Recurse -Force }
            New-Item -ItemType Directory -Force -Path $nodeInstallDir | Out-Null

            # 解压到临时目录（zip 内有一层 node-v{ver}-win-x64 目录）
            $tmpExtract = "$env:TEMP\node-extract-$PID"
            Invoke-Extract -Archive $localNodeZip.FullName -Destination $tmpExtract
            $innerDir = Get-ChildItem -Path $tmpExtract -Directory | Select-Object -First 1
            if ($innerDir) {
                Copy-Item -Path "$($innerDir.FullName)\*" -Destination $nodeInstallDir -Recurse -Force
            } else {
                Copy-Item -Path "$tmpExtract\*" -Destination $nodeInstallDir -Recurse -Force
            }
            Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue
            Write-Ok "Node.js 解压到 $nodeInstallDir"

            $nvmExe = if ($env:NVM_HOME -and (Test-Path "$env:NVM_HOME\nvm.exe")) { "$env:NVM_HOME\nvm.exe" } else { "$env:USERPROFILE\nvm\nvm.exe" }
            Start-Process -FilePath $nvmExe -ArgumentList "use", $localVer -WindowStyle Hidden -Wait
        } catch {
            Write-Warn "离线安装失败: $_，回退在线安装..."
            $localNodeZip = $null
        }
    }

    if (-not $localNodeZip) {
        # 在线安装
        Write-Info "安装 Node.js $NODE_VERSION（首次下载约需 5-10 分钟）..."
        try {
            $nvmExe = "$env:NVM_HOME\nvm.exe"
            if (-not (Test-Path $nvmExe)) { $nvmExe = "$env:USERPROFILE\nvm\nvm.exe" }
            Start-Process -FilePath $nvmExe -ArgumentList "install", $NODE_VERSION -WindowStyle Hidden -Wait
            Start-Process -FilePath $nvmExe -ArgumentList "use", $NODE_VERSION -WindowStyle Hidden -Wait
        } catch {
            Write-Err "Node.js 安装失败: $_"
            return $false
        }
    }

    # 刷新 PATH 并验证
    try {
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $nvmSym = [System.Environment]::GetEnvironmentVariable("NVM_SYMLINK","User")
        if ($nvmSym -and ($env:Path -notlike "*$nvmSym*")) {
            $env:Path = "$nvmSym;" + $env:Path
        }

        $newVer = try { node --version 2>$null } catch { $null }

        # nvm use 在用户名含空格时可能无法创建 symlink，fallback: 直接将 node 目录加入 PATH
        if (-not $newVer) {
            $nvmHome = $env:NVM_HOME
            if (-not $nvmHome) { $nvmHome = "$env:USERPROFILE\nvm" }
            $nodeDirs = Get-ChildItem -Path $nvmHome -Directory -Filter "v*" -ErrorAction SilentlyContinue | Sort-Object Name -Descending
            foreach ($d in $nodeDirs) {
                $nodeExe = Join-Path $d.FullName "node.exe"
                if (Test-Path $nodeExe) {
                    $nodeDir = $d.FullName
                    Write-Warn "nvm use 未生效（用户名含空格时可能无法创建 symlink），直接使用 $nodeDir"
                    $env:Path = "$nodeDir;" + $env:Path
                    # 同时持久化到用户 PATH
                    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
                    if ($userPath -notlike "*$nodeDir*") {
                        $userPath = "$nodeDir;$userPath"
                        [System.Environment]::SetEnvironmentVariable("Path", $userPath, "User")
                    }
                    $newVer = & "$nodeExe" --version 2>$null
                    break
                }
            }
        }

        if ($newVer) {
            Write-Ok "Node.js $newVer 安装完成"
        } else {
            Write-Warn "Node.js 安装后命令未生效，请重启 PowerShell 后重试"
            return $false
        }
    } catch {
        Write-Err "Node.js 安装失败: $_"
        return $false
    }

    return $true
}

# ==================== 3. 安装 Git Bash ====================
function Install-GitBash {
    Write-Banner "安装 Git Bash"

    # 检查已有 Git Bash
    $bashPath = ""
    $commonPaths = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files (x86)\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe",
        "$env:USERPROFILE\Git\bin\bash.exe"
    )

    foreach ($p in $commonPaths) {
        if (Test-Path $p) {
            $bashPath = $p
            break
        }
    }

    if (-not $bashPath) {
        try {
            $gitVer = git --version 2>$null
            if ($gitVer) {
                $gitPath = (Get-Command git -ErrorAction SilentlyContinue).Source
                if ($gitPath) {
                    $candidate = Join-Path (Split-Path (Split-Path $gitPath)) "bin\bash.exe"
                    if (Test-Path $candidate) { $bashPath = $candidate }
                }
            }
        } catch {}
    }

    if ($bashPath) {
        Write-Ok "Git Bash 已找到: $bashPath，跳过安装"
        [System.Environment]::SetEnvironmentVariable("CLAUDE_CODE_GIT_BASH_PATH", $bashPath, "User")
        $env:CLAUDE_CODE_GIT_BASH_PATH = $bashPath
        return $true
    }

    # 使用 PortableGit 免安装版（无需管理员权限）
    Write-Info "安装 PortableGit（免安装版，无需管理员权限）..."

    $gitDir = "$env:USERPROFILE\Git"
    $exeFile = "$env:TEMP\PortableGit.exe"

    # 优先检查脚本同级目录的离线 PortableGit（支持 .zip / .7z.exe / .7z）
    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
    $localGitPkg = Get-ChildItem -Path $scriptDir -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -imatch 'git' -and $_.Name -imatch '\.(zip|exe|7z)$' } |
        Select-Object -First 1

    if ($localGitPkg) {
        Write-Info "检测到离线 PortableGit 包: $($localGitPkg.Name)"
        $exeFile = "$env:TEMP\$($localGitPkg.Name)"
        Copy-Item $localGitPkg.FullName $exeFile -Force
        Write-Ok "使用离线包"
    } else {
        # 在线下载：优先 npmmirror 国内镜像，回退 GitHub
        $gitUrlMirror = "https://registry.npmmirror.com/-/binary/git-for-windows/v2.53.0.windows.1/PortableGit-2.53.0-64-bit.7z.exe"
        $gitUrlGithub = "https://github.com/git-for-windows/git/releases/download/v2.53.0.windows.1/PortableGit-2.53.0-64-bit.7z.exe"

        $downloaded = $false
        try {
            Write-Info "下载 PortableGit（npmmirror 镜像）..."
            Invoke-WebRequest -Uri $gitUrlMirror -OutFile $exeFile -UseBasicParsing -ErrorAction Stop
            Write-Ok "下载完成（npmmirror）"
            $downloaded = $true
        } catch {
            Write-Warn "npmmirror 下载失败，尝试 GitHub..."
            try {
                Invoke-WebRequest -Uri $gitUrlGithub -OutFile $exeFile -UseBasicParsing -ErrorAction Stop
                Write-Ok "下载完成（GitHub）"
                $downloaded = $true
            } catch {
                Write-Err "PortableGit 下载失败（npmmirror 和 GitHub 均不可达）"
                Write-Info "请手动安装: https://git-scm.com/downloads/win"
                return $false
            }
        }
    }

    try {
        Write-Info "解压 PortableGit..."
        if (Test-Path $gitDir) { Remove-Item $gitDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $gitDir | Out-Null

        Invoke-Extract -Archive $exeFile -Destination $gitDir
        Remove-Item $exeFile -Force -ErrorAction SilentlyContinue

        $bashPath = "$gitDir\bin\bash.exe"
        if (Test-Path $bashPath) {
            Write-Ok "PortableGit 解压到 $gitDir"

            # 添加到用户 PATH
            $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
            $gitBinPath = "$gitDir\cmd"
            if ($userPath -notlike "*$gitBinPath*") {
                $userPath = "$gitBinPath;$userPath"
                [System.Environment]::SetEnvironmentVariable("Path", $userPath, "User")
                $env:Path = "$gitBinPath;" + $env:Path
            }

            [System.Environment]::SetEnvironmentVariable("CLAUDE_CODE_GIT_BASH_PATH", $bashPath, "User")
            $env:CLAUDE_CODE_GIT_BASH_PATH = $bashPath
            Write-Ok "Git Bash 路径: $bashPath"
            return $true
        } else {
            Write-Err "解压后未找到 bash.exe"
            return $false
        }
    } catch {
        Write-Err "PortableGit 解压失败: $_"
        Remove-Item $exeFile -Force -ErrorAction SilentlyContinue
        return $false
    }
}

# ==================== 4. 安装 Claude Code ====================
function Install-Claude {
    Write-Banner "安装 Claude Code"

    try {
        $ver = claude --version 2>$null
        if ($ver) {
            Write-Ok "Claude Code 已安装: $ver"
            return $true
        }
    } catch {}

    $pkg = "@anthropic-ai/claude-code"
    if ($CLAUDE_VERSION) { $pkg = "$pkg@$CLAUDE_VERSION" }
    Write-Info "npm install -g $pkg （npmmirror 镜像）..."

    # 用户名含空格时 npm 可能不在 PATH，尝试从已知 node 目录找 npm.cmd
    $npmCmd = try { (Get-Command npm -ErrorAction Stop).Source } catch {
        $nvmHome = $env:NVM_HOME
        if (-not $nvmHome) { $nvmHome = "$env:USERPROFILE\nvm" }
        $nodeDir = Get-ChildItem -Path $nvmHome -Directory -Filter "v*" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1 |
            ForEach-Object { $_.FullName }
        if ($nodeDir -and (Test-Path "$nodeDir\npm.cmd")) { "$nodeDir\npm.cmd" } else { "npm" }
    }

    try {
        & $npmCmd install -g $pkg --registry=https://registry.npmmirror.com/
        Refresh-Env
        $ver = try { claude --version 2>$null } catch { $null }
        if ($ver) {
            Write-Ok "Claude Code $ver 安装完成"
        } else {
            Write-Ok "Claude Code 安装完成（可能需要重启 PowerShell）"
        }
        return $true
    } catch {
        Write-Err "Claude Code 安装失败: $_"
        return $false
    }
}

# ==================== 5. 配置快捷方式 ====================
function Setup-Shortcuts {
    Write-Banner "配置快捷方式"

    # --- Git 右键菜单（HKCU，无需管理员权限）---
    $gitDir = "$env:USERPROFILE\Git"
    $gitBashExe = "$gitDir\git-bash.exe"
    $gitGuiExe  = "$gitDir\cmd\git-gui.exe"

    if (Test-Path $gitBashExe) {
        foreach ($location in @("Directory\shell", "Directory\Background\shell")) {
            # Git Bash Here
            $keyBase = "HKCU:\Software\Classes\$location\git_shell"
            New-Item -Path $keyBase -Force | Out-Null
            Set-ItemProperty $keyBase "(default)" "Git Bash Here"
            Set-ItemProperty $keyBase "Icon" $gitBashExe
            New-Item -Path "$keyBase\command" -Force | Out-Null
            $cdVar = if ($location -like "*Background*") { "%V" } else { "%1" }
            Set-ItemProperty "$keyBase\command" "(default)" "`"$gitBashExe`" `"--cd=$cdVar`""
        }
        Write-Ok "Git Bash Here 右键菜单已添加"

        # Git GUI Here
        if (Test-Path $gitGuiExe) {
            foreach ($location in @("Directory\shell", "Directory\Background\shell")) {
                $keyBase = "HKCU:\Software\Classes\$location\git_gui"
                New-Item -Path $keyBase -Force | Out-Null
                Set-ItemProperty $keyBase "(default)" "Git GUI Here"
                Set-ItemProperty $keyBase "Icon" $gitGuiExe
                New-Item -Path "$keyBase\command" -Force | Out-Null
                $cdVar = if ($location -like "*Background*") { "%V" } else { "%1" }
                Set-ItemProperty "$keyBase\command" "(default)" "`"$gitGuiExe`" `"--working-dir`" `"$cdVar`""
            }
            Write-Ok "Git GUI Here 右键菜单已添加"
        }
    } else {
        Write-Warn "未找到 git-bash.exe，跳过右键菜单"
    }

}

# ==================== 6. 配置 ====================
function Setup-Config {
    Write-Banner "配置 Claude Code"

    # 跳过引导 + 预批准 API Key（取 key 后20位作为标识）
    $claudeJson = "$env:USERPROFILE\.claude.json"
    $keySuffix = if ($ANTHROPIC_API_KEY.Length -gt 20) { $ANTHROPIC_API_KEY.Substring($ANTHROPIC_API_KEY.Length - 20) } else { $ANTHROPIC_API_KEY }
    $claudeJsonContent = @"
{
  "hasCompletedOnboarding": true,
  "customApiKeyResponses": {
    "approved": ["$keySuffix"],
    "rejected": []
  }
}
"@
    # 备份原有配置到目录（已有则备份）
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $configDir = "$env:USERPROFILE\.claude"
    $settingsFile = "$configDir\settings.json"
    $hasBackup = (Test-Path $claudeJson) -or (Test-Path $settingsFile)
    if ($hasBackup) {
        $backupDir = "$env:USERPROFILE\claude_origin_config_$timestamp"
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        $backupPairs = @()
        if (Test-Path $claudeJson) {
            Copy-Item $claudeJson "$backupDir\.claude.json" -Force
            $backupPairs += [PSCustomObject]@{ From = $claudeJson; To = "$backupDir\.claude.json" }
        }
        if (Test-Path $settingsFile) {
            Copy-Item $settingsFile "$backupDir\settings.json" -Force
            $backupPairs += [PSCustomObject]@{ From = $settingsFile; To = "$backupDir\settings.json" }
        }
        Write-Warn "已备份原有配置到: $backupDir"
        $backupPairs | ForEach-Object { Write-Warn "  $($_.From)  ->  $($_.To)" }
    }

    $claudeJsonContent | Out-File -FilePath $claudeJson -Encoding utf8 -Force
    Write-Ok "跳过登录引导 + 预批准 API Key"

    # 写入 settings.json
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    }

    $configContent = @"
{
  "env": {
    "ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL": "$ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL": "$ANTHROPIC_MODEL"
  },
  "alwaysThinkingEnabled": true,
  "permissions": {
    "allow": [
      "*"
    ]
  },
  "defaultMode": "bypassPermissions",
  "claude-code.dangerously": true,
  "skipDangerousModePermissionPrompt": true
}
"@
    $configContent | Out-File -FilePath "$configDir\settings.json" -Encoding utf8 -Force
    Write-Ok "API Key 已配置"
    Write-Ok "Base URL: $ANTHROPIC_BASE_URL"
    Write-Ok "默认模型: $ANTHROPIC_MODEL"

    # 打印配置文件内容
    Write-Host ""
    Write-Info "配置文件内容："
    Write-Host "  [$claudeJson]" -ForegroundColor DarkGray
    Get-Content $claudeJson | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    Write-Host ""
    Write-Host "  [$configDir\settings.json]" -ForegroundColor DarkGray
    Get-Content "$configDir\settings.json" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    Write-Host ""
}

# ==================== 恢复配置 ====================
function Restore-Config {
    Write-Banner "恢复 Claude Code 配置"

    # 确定备份目录
    $targetDir = ""
    if ($RestoreDir -ne "") {
        if (-not (Test-Path $RestoreDir)) {
            Write-Err "指定的备份目录不存在: $RestoreDir"
            return
        }
        $targetDir = $RestoreDir
        Write-Info "使用指定备份目录: $targetDir"
    } else {
        # 取最早的备份目录
        $backupDirs = Get-ChildItem -Path $env:USERPROFILE -Directory -Filter "claude_origin_config_*" -ErrorAction SilentlyContinue |
            Sort-Object Name | Select-Object -First 1
        if (-not $backupDirs) {
            Write-Warn "未找到任何备份目录（claude_origin_config_*），无法恢复"
            return
        }
        $targetDir = $backupDirs.FullName
        Write-Info "使用最早备份目录: $targetDir"
    }

    $restored = $false

    # 恢复 .claude.json
    $bakJson = "$targetDir\.claude.json"
    if (Test-Path $bakJson) {
        Copy-Item $bakJson "$env:USERPROFILE\.claude.json" -Force
        Write-Ok "已恢复 .claude.json <- $bakJson"
        $restored = $true
    } else {
        Write-Warn "备份目录中未找到 .claude.json，跳过"
    }

    # 恢复 settings.json
    $bakSettings = "$targetDir\settings.json"
    if (Test-Path $bakSettings) {
        $configDir = "$env:USERPROFILE\.claude"
        if (-not (Test-Path $configDir)) { New-Item -ItemType Directory -Force -Path $configDir | Out-Null }
        Copy-Item $bakSettings "$configDir\settings.json" -Force
        Write-Ok "已恢复 settings.json <- $bakSettings"
        $restored = $true
    } else {
        Write-Warn "备份目录中未找到 settings.json，跳过"
    }

    if ($restored) {
        Write-Host ""
        Write-Info "恢复后的配置文件内容："
        $claudeJson = "$env:USERPROFILE\.claude.json"
        if (Test-Path $claudeJson) {
            Write-Host "  [$claudeJson]" -ForegroundColor DarkGray
            Get-Content $claudeJson | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            Write-Host ""
        }
        $settingsFile = "$env:USERPROFILE\.claude\settings.json"
        if (Test-Path $settingsFile) {
            Write-Host "  [$settingsFile]" -ForegroundColor DarkGray
            Get-Content $settingsFile | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            Write-Host ""
        }
        Write-Ok "配置恢复完成"
    }
}

# ==================== 主流程 ====================
function Main {
    Write-Host ""
    Write-Host "  +=============================================+" -ForegroundColor Cyan
    Write-Host "  |  Claude Code 一键安装脚本                    |" -ForegroundColor Cyan
    Write-Host "  |  模型: $ANTHROPIC_MODEL$((' ' * (37 - $ANTHROPIC_MODEL.Length)))|" -ForegroundColor Cyan
    Write-Host "  |  无需代理，国内直连                          |" -ForegroundColor Cyan
    Write-Host "  +=============================================+" -ForegroundColor Cyan
    Write-Host ""

    Clear-Proxy

    Write-Info "步骤 [0/6] 初始化 7z"
    Init-7zip

    # 检测无效 Key
    $invalidKeys = @("sk-your-api-key", "sk-xxx", "sk-your", "")
    $keyLower = $ANTHROPIC_API_KEY.ToLower().Trim()
    if ($invalidKeys -contains $keyLower -or $keyLower -match '^sk-x+$' -or $keyLower.Length -lt 10) {
        Write-Err "API Key 无效: '$ANTHROPIC_API_KEY'"
        Write-Err "请提供真实的 API Key，从 https://bailian.console.aliyun.com/ 获取"
        return
    }

    Write-Info "步骤 [1/6] 安装 nvm"
    if (-not (Install-Nvm)) {
        Write-Err "nvm 安装失败，请按提示操作后重试"
        return
    }

    Write-Info "步骤 [2/6] 安装 Node.js"
    if (-not (Install-Node)) {
        Write-Err "Node.js 安装失败，请按提示操作后重试"
        return
    }

    Write-Info "步骤 [3/6] 安装 Git Bash"
    if (-not (Install-GitBash)) {
        Write-Err "Git Bash 安装失败，Claude Code 在 Windows 上需要 Git Bash"
        return
    }

    Write-Info "步骤 [4/6] 安装 Claude Code"
    if (-not (Install-Claude)) {
        Write-Err "Claude Code 安装失败"
        return
    }

    Write-Info "步骤 [5/6] 配置 Claude Code"
    Setup-Config

    Write-Info "步骤 [6/6] 配置快捷方式"
    Setup-Shortcuts

    Write-Banner "安装完成"
    Write-Host "  还原配置：如需还原安装前的原始 Claude 配置，执行：" -ForegroundColor White
    Write-Host "      .\claude-install.ps1 --restore" -ForegroundColor Yellow
    Write-Host "      .\claude-install.ps1 --restore --restore-dir ~\claude_origin_config_<时间戳>  # 指定备份目录" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host "  │  启动方式：打开终端（PowerShell），输入以下指令：           │" -ForegroundColor Cyan
    Write-Host "  │                                                             │" -ForegroundColor Cyan
    Write-Host "  │  开始会话：claude --dangerously-skip-permissions            │" -ForegroundColor Cyan
    Write-Host "  │  恢复会话：claude --dangerously-skip-permissions --resume   │" -ForegroundColor Cyan
    Write-Host "  └─────────────────────────────────────────────────────────────┘" -ForegroundColor Cyan
    Write-Host ""

}

if ($Restore) {
    Restore-Config
} else {
    Main
}
