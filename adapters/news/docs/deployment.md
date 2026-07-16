# Deployment

> 部署流程。上线前阅读。

## 前置条件
- 测试通过: `uv run pytest tests/ -v`
- lint 通过: `uv run ruff check src/`

## 步骤
1. 更新版本号
2. 构建: `docker build -t myapp:tag .`
3. 部署: `kubectl set image deployment/myapp myapp=myapp:tag`
4. 验证: curl /health 返回 200
