# 劳动争议证据整理器 —— 绿色便携版技术说明

本文档面向需要修改、重建或排错此包的开发者。最终用户请读 README.txt。

## 一、这个包是怎么构建的

在 Linux 上执行：

```bash
bash scripts/build-portable.sh     # 产出 dist/labor-evidence-portable-<ver>-win64.zip
bash scripts/portable-smoke-test.sh # 冒烟（接管 8000/3000，结束自动恢复 dev 服务）
```

构建流水线（build-portable.sh）：

1. 下载并内置运行时（有本地缓存，`$TMPDIR/leo-portable-cache`）：
   - Python 3.11.9 embeddable（python.org 官方 zip，改 `python311._pth`
     启用 `Lib\site-packages` 与 `import site`）
   - Node.js v20.18.0 win-x64（官方 zip，取 node.exe 等）
2. 交叉安装后端依赖（Windows wheels，Linux 上执行）：

   ```bash
   pip install --platform win_amd64 --python-version 3.11 --implementation cp \
     --only-binary=:all: --target <site-packages> -r backend/requirements-portable.txt
   ```

   - `passlib` 在 PyPI 只有 sdist（pip 交叉模式禁止本地构建），因此先
     `pip wheel --no-deps` 构建成通用 wheel 再装。
   - `requirements-portable.txt` 与主 requirements 的差异：去 psycopg
     （SQLite 不需要）、去 alembic（首次启动 `create_all()` 建表）、
     去 pytest、去 `uvicorn[standard]`（uvloop 无 Windows 轮子，且 pip
     对环境标记按构建宿主求值）。版本全部 pin 为测试套件实际跑过的版本。
3. `next build`（`output: "standalone"`，`NEXT_DIST_DIR=.next-portable`
   与 dev server 的 `.next` 隔离），把 `standalone/` 与 `static/` 组装为
   `frontend/server/`。注意 server.js 内嵌构建时的 distDir，静态资源必须
   放在 `frontend/server/.next-portable/static/`。
4. 生成 `backend/.env`：`APP_ENV=production`、随机 SECRET_KEY、
   `DATABASE_URL=sqlite:///../data/leo.db`（相对路径，数据在包根 data/）、
   `AI_PROVIDER=mock`（离线演示，可自行改为 OpenAI 兼容接口）。
5. 打包 zip。

## 二、Windows 上的启动链路

```
start.bat
 ├─ stop.bat silent            # 幂等：先清掉上次残留进程（按端口杀）
 ├─ 首次运行: python -c "from app.db import create_all; create_all()"
 ├─ start-backend.bat  → python\python.exe -m uvicorn app.main:app (:8000)
 └─ start-frontend.bat → node node.exe server.js          (:3000)
     （HOSTNAME=127.0.0.1，仅本机；5 秒后自动打开浏览器）
```

stop.bat 用 `netstat -ano | findstr` 找 8000/3000 的 LISTENING PID 并
taskkill。start.bat 先调 stop，重复双击不会起重复实例。

## 三、SQLite 兼容改造（代码层，对 PostgreSQL 无行为影响）

测试套件在 SQLite 与 PostgreSQL 下均 275 全过。改造点：

| 位置 | 问题 | 处理 |
| --- | --- | --- |
| `app/db.py` | SQLite 默认关外键（级联删除会静默失效）、跨线程限制 | 连接级 PRAGMA：`foreign_keys=ON`、`busy_timeout=5000`、`journal_mode=WAL`；`check_same_thread=False` |
| `app/db.py create_schema()` | SQLite 不支持 `UNIQUE (...) DEFERRABLE`（材料包重排约束） | 仅 SQLite 建表时剥掉 deferrable 标志（PG 走 alembic 迁移，不受影响） |
| `app/services/material_packages.py save_items()` | SQLite 逐条语句即时检查 UNIQUE，编号互换中途撞车 | 两阶段编号：先全部挪到临时位（+1,000,000）再落到 1..N |
| `app/models/base.py TimestampMixin` | SQLite `CURRENT_TIMESTAMP` 只有秒级精度，同秒快照变更检测不出 CHANGED | 时间戳改为 Python 侧 `utcnow()`（微秒精度），`func.now()` 保留为 server_default 兜底 |
| `app/models/export.py` | `server_default="false"` 在 SQLite 会存成文本 | 改 `text("false")` 裸关键字（PG、SQLite 都接受） |
| `tests/conftest.py` | PG 专属 `TRUNCATE ... CASCADE` | SQLite 下改为按依赖逆序 DELETE |

## 四、冒烟测试

`scripts/portable-smoke-test.sh` 在构建宿主机用宿主 python+node 运行同一
份 stage 树（包内的 python/、node/ 是 Windows 构建，无法在 Linux 执行），
验证：首次建库 → API 健康 → 注册/登录/建案 → 登录页与 `_next/static`
资源 200。过程中会临时占用 8000/3000，结束时用 dev-restart-* 脚本恢复
开发服务。

## 五、已知边界 / 待办

- **Windows 实机未测**：bat 脚本、embeddable Python、任务管理（按端口
  taskkill）均按官方文档行为编写，需在真实 Windows 10/11 上跑一遍
  start.bat → 浏览器注册 → 上传 → 导出的完整链路。
- 仅监听 127.0.0.1，单机使用；局域网共享需另行改 NEXT_PUBLIC_API_BASE_URL
  重新构建并调整 CORS（不在支持范围）。
- 端口 8000/3000 需空闲；冲突时关闭占用程序。
- 升级版本：改 `backend/app/__init__.py` 的 `__version__` 后重跑两个脚本。
- 数据备份：stop 后整体拷贝 `data/` 目录。
