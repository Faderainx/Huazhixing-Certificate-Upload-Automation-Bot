# Huazhixing Certificate Upload Automation Bot

华之星系统证书上传机器人，支持读取任务包中的 Excel、截图压缩包和 WEEE / BAT 证书，按公司与证书编号匹配订单，并执行二级待办证书上传。一级截图上传流程保留为接口占位，待确认对应 API 后再启用。

## Repository contents

- `hzx_upload_standalone/`：当前独立版，支持 dry-run、断点重跑、GUI 和命令行入口。
- `legacy/`：旧版批量上传脚本和流程模型，便于追溯历史实现。
- `requirements.txt`：运行依赖。

仓库只保存源码和流程模型，不包含账号密码、客户名单、证书、截图、任务包、运行结果或打包程序。

## Local configuration

运行前在本机设置服务地址和登录凭据：

```text
HZX_BASE_URL=https://your-service.example
HZX_USERNAME=your-account
HZX_PASSWORD=your-password
```

也可以在命令行使用 `--username` / `--password`，或使用 `--save-cred` 将凭据加密保存到本机的 `credentials.enc`。这些文件已被 `.gitignore` 排除。

## Run

```bash
python -m pip install -r requirements.txt
python hzx_upload_standalone/main.py --task-package "任务包目录" --dry-run
```

确认 dry-run 输出无误后，再按需使用 `--level2` 执行证书上传。任务包应由使用者在本机准备，不能提交到仓库。
