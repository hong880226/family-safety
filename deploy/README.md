# FamilySafety 部署

## 一键启动（开发）

```bash
cd deploy
cp .env.example .env
# 编辑 .env，至少填 JWT_SECRET 和 LLM_API_KEY

docker compose up -d
docker compose logs -f backend
```

浏览器访问：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/healthz

## 数据持久化

- PostgreSQL 数据：Docker volume `postgres_data`
- Redis 数据：Docker volume `redis_data`

## 升级

```bash
cd deploy
git pull
docker compose pull
docker compose up -d --build
```

## 备份

```bash
# 备份数据库
docker exec fs-postgres pg_dump -U familysafety familysafety > backup.sql

# 恢复
cat backup.sql | docker exec -i fs-postgres psql -U familysafety familysafety
```

## 卸载

```bash
docker compose down -v  # -v 会同时删除数据卷
```
