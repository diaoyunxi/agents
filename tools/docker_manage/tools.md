# docker_manage — Docker 管理

## 作用
管理 Docker 容器/镜像/Compose：查看运行中容器、镜像、日志，构建、运行、停止、删除，跑 Compose 子命令。

## 参数
- `action`（string, 必填）：`ps`/`images`/`logs`/`inspect`/`build`/`run`/`stop`/`remove`/`compose`。
- `args`（string, 可选）：附带参数。如 logs 给容器名；build 给 `-t 名 .`；run 给镜像名+命令；compose 给 `up -d` 等。
- `timeout`（integer, 可选）：默认 120 秒。

## 门控
声明 `REQUIRES=["cli:docker"]`：本机未装 Docker CLI 时自动停用；安装 Docker Desktop 后自动恢复。

## 注意事项
- `DANGEROUS`：build/run/stop/remove 有副作用；生产环境操作先 `request_approval`。
- 写 `compose` 文件本身请用 `write_to_file`。
