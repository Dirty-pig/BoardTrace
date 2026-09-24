# BoardTrace（板迹）

BoardTrace 是一个用于记录板卡调试过程的轻量工具：按板卡型号、PCB 序列号和项目整理问题，使用 Cell 时间线记录现象、测试、判断、待办和结论，并保存图片、附件、知识条目与工时。

## 快速开始：Docker

需要 Docker Desktop 或 Docker Engine。克隆仓库后，在项目目录运行：

```bash
docker compose up -d --build
```

打开 <http://127.0.0.1:5000>。第一次访问会引导创建 ROOT 账号；密码至少 10 位。没有预设账号或密码。

```bash
docker compose ps           # 查看状态
docker compose logs -f      # 查看日志
docker compose down         # 停止服务，保留数据
```

Docker 镜像只包含程序，不包含任何现有数据库、账号、密钥或附件。新环境会创建自己的空数据库。数据和备份分别保存在 Docker 卷 `boardtrace_data`、`boardtrace_backups`；重建镜像或执行 `docker compose down` 不会清空它们。**不要执行 `docker compose down -v`，除非确认要删除这些卷中的数据。** 建议定期把备份导出到另一块硬盘。

默认仅绑定本机 `127.0.0.1:5000`，不会直接开放给局域网。若要从其他设备访问，需要自行配置端口绑定和防火墙。不要把服务直接暴露到公网。

已有本机服务占用 5000 端口时，先停止其中一个版本；Docker 版和本机版不要同时争用该端口。

## Windows 本机运行（不使用 Docker）

安装 Python 3.12 后，可以在项目目录创建虚拟环境并安装依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

双击 `启动服务.cmd`：仅在后台启动服务，重复点击不会启动第二个服务器。然后双击 `打开板迹.cmd`：仅打开无普通浏览器地址栏的独立窗口，不会启动服务。关闭窗口不会停止服务。Windows 重启后需再次运行“启动服务”；脚本不会自行设置开机启动。

也可以直接用浏览器访问 <http://127.0.0.1:5000>。旧的 `scripts/start_server.ps1` 是占用当前终端的前台启动方式。

已有 Conda 环境时，可运行 `scripts/setup_env.ps1`，或通过环境变量 `BOARDTRACE_PYTHON` 指向该环境的 `python.exe`。两个 Windows 启动脚本会优先寻找 `.venv`，再寻找常见的 Miniconda/Anaconda `problem-system` 环境。

## 基本使用

1. 创建板卡，填写板卡型号和唯一的 PCB 序列号；型号是主要工作对象，序列号区分同型号实物板。
2. 按需创建项目，并关联多块板卡。项目、板卡和问题页面都可直接添加 Cell。
3. 在问题中记录现象、测试、判断、待办、结论，添加图片或附件。部分 Cell 类型会自动更新问题状态。
4. 使用知识库保存可复用的经验；工作记录和计时器单独统计投入时间。
5. Cell 和问题的删除先进入回收站，可恢复；系统生成的状态变化记录不可删除。

Cell 支持安全 Markdown、表格和图片。复制 Excel 单元格区域到编辑框会转换为 Markdown 表格；发送后的图片可点击预览。

## 数据、备份与安全

- 本机模式的数据位于 `data/`，其中包含 SQLite 数据库、密钥、附件和备份；该目录被 Git 和 Docker 构建排除。
- Docker 模式的数据位于独立 Docker 卷，不随镜像发布；重新部署时请保留对应卷。
- ROOT 可在“系统管理”中执行数据库与附件备份。备份使用 SQLite 在线备份，不直接复制运行中的数据库文件。
- 所有工作数据需要登录；密码以 Argon2 哈希保存。该工具面向可信本机或局域网，不应未经额外安全加固就开放公网。

## 开发检查

```bash
python -m pytest -q
python -m compileall -q app scripts mcp_server.py
```

主要目录：`app/` 为后端与模板，`prototype/` 为网页样式和脚本，`tests/` 为自动化测试，`scripts/` 为启动与维护脚本。`mcp_server.py` 提供独立的只读 MCP 接口，不包含写入工具。
