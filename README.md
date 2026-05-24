# PyDFS — Sistema de Archivos Distribuido

DFS minimalista inspirado en HDFS/GFS. Almacena archivos dividiéndolos en bloques
y distribuyéndolos entre múltiples DataNodes con replicación automática (factor 2).
Un NameNode central coordina metadatos y autenticación.

```
Cliente (CLI)
    │
    ├──► NameNode :8000   (metadatos, auth, coordinación)
    │        └──► SQLite
    │
    ├──► DataNode1 :8001
    ├──► DataNode2 :8002
    └──► DataNode3 :8003
```

---

## Requisitos

- Docker >= 24
- Docker Compose >= 2.20

---

## Despliegue

### 1. Clonar el repositorio

```bash
git clone https://github.com/miguelRamirezr1/pydfs.git
cd pydfs
```

### 2. Construir imágenes y levantar el clúster

```bash
docker compose up --build -d
```

Esto construye las imágenes de `namenode`, `datanode` (×3) y `client`,
levanta los contenedores en la red `dfs-network` e inicializa automáticamente
el esquema SQLite con las tablas `users`, `files`, `blocks` y `datanodes`.

### 3. Verificar que el clúster está activo

```bash
curl -s http://localhost:8000/datanodes/status | python3 -m json.tool
```

Deben aparecer `dn1`, `dn2` y `dn3` con `"status": "active"`.

### 4. Detener el clúster

```bash
docker compose down
```

### 5. Detener y eliminar todos los datos (reset completo)

```bash
docker compose down -v
```

---

## Configuración

Variables de entorno definidas en `docker-compose.yml`:

| Variable | Servicio | Default | Descripción |
|---|---|---|---|
| `BLOCK_SIZE` | namenode | `67108864` | Tamaño de bloque en bytes (64 MB). Usar `3` para pruebas con archivos pequeños |
| `REPLICATION_FACTOR` | namenode | `2` | Copias por bloque |
| `HEARTBEAT_TIMEOUT` | namenode | `15` | Segundos para declarar un DataNode caído |
| `HEARTBEAT_INTERVAL` | datanodes | `5` | Segundos entre heartbeats |
| `JWT_SECRET` | todos | `changeme` | Clave de firma JWT — **cambiar en producción** |
| `ADMIN_SECRET` | namenode | `admin-secret` | Token para registrar usuarios adicionales |
| `NODE_ID` | datanodes | `dn1/dn2/dn3` | Identificador único del DataNode |

Para aplicar cambios de variables de entorno sin reconstruir imágenes:

```bash
docker compose up -d --force-recreate namenode
```

---

## Uso del CLI

El CLI se ejecuta desde el contenedor `client` o localmente con
`NAMENODE_URL=http://localhost:8000 python3 client/cli.py <comando>`.

Los ejemplos siguientes usan el contenedor cliente, que resuelve
los hostnames internos de Docker.

### Registro y login

```bash
# Registrar el primer usuario (no requiere token de administrador)
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "mipassword"}' | python3 -m json.tool

# Registrar usuarios adicionales (requiere X-Admin-Token)
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: admin-secret" \
  -d '{"username": "bob", "password": "otrapass"}' | python3 -m json.tool

# Guardar token JWT en ~/.dfs_token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "mipassword"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$TOKEN" > /tmp/.dfs_token
```

### `put` — subir un archivo

```bash
# Preparar archivo de prueba
printf "aaabbbccc" > /tmp/test.txt

# Subir (el nombre remoto por defecto es el nombre del archivo local)
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  -v /tmp/test.txt:/tmp/test.txt:ro \
  pydfs-client put /tmp/test.txt
```

```
Subido: test.txt (9 bytes, 1 bloque(s))
```

```bash
# Subir especificando ruta remota
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  -v /tmp/test.txt:/tmp/test.txt:ro \
  pydfs-client put /tmp/test.txt --remote-path docs/test.txt
```

```
Subido: docs/test.txt (9 bytes, 1 bloque(s))
```

### `ls` — listar archivos y directorios

```bash
# Listar todo
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client ls
```

```
FILE  test.txt      9 bytes  2026-05-24T14:30:00+00:00
DIR   docs          0 bytes  2026-05-24T14:29:00+00:00
FILE  docs/test.txt 9 bytes  2026-05-24T14:31:00+00:00
```

```bash
# Filtrar por directorio
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client ls --path docs
```

```
FILE  docs/test.txt  9 bytes  2026-05-24T14:31:00+00:00
```

### `get` — descargar un archivo

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  -v /tmp:/tmp \
  pydfs-client get test.txt -o /tmp/descargado.txt
```

```
Descargado: /tmp/descargado.txt
```

```bash
# Verificar integridad
diff /tmp/test.txt /tmp/descargado.txt && echo "OK"
```

### `rm` — eliminar un archivo

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client rm test.txt
```

```
Eliminado: test.txt
```

### `mkdir` — crear un directorio

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client mkdir docs
```

```
Directorio creado: docs
```

### `rmdir` — eliminar un directorio vacío

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client rmdir docs
```

```
Directorio eliminado: docs
```

---

## Documentación interactiva de la API

FastAPI genera automáticamente un Swagger UI para cada servicio:

| Servicio | URL |
|----------|-----|
| NameNode | http://localhost:8000/docs |
| DataNode 1 | http://localhost:8001/docs |
| DataNode 2 | http://localhost:8002/docs |
| DataNode 3 | http://localhost:8003/docs |

---

## Monitoreo del clúster

```bash
# Estado de los DataNodes (host, puerto, free_bytes, último heartbeat)
curl -s http://localhost:8000/datanodes/status | python3 -m json.tool

# Logs en tiempo real
docker compose logs -f namenode
docker compose logs -f datanode1

# Inspeccionar bloques en un DataNode
docker exec pydfs-datanode1-1 ls /app/blocks/

# Inspeccionar la base de datos del NameNode
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT owner, path, size, is_dir FROM files ORDER BY path').fetchall():
    print(dict(r))
"
```

---

## Prueba de tolerancia a fallos

```bash
# 1. Subir un archivo con BLOCK_SIZE=3 para obtener múltiples bloques
# (editar docker-compose.yml: BLOCK_SIZE=3, luego recrear namenode)

# 2. Verificar distribución de bloques
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT b.seq, b.datanode FROM blocks b
    JOIN files f ON f.file_id = b.file_id
    WHERE f.path = \"test.txt\" ORDER BY b.seq, b.datanode
''').fetchall()
for r in rows: print(dict(r))
"

# 3. Detener un DataNode
docker stop pydfs-datanode2-1

# 4. Esperar detección y re-replicación automática (≤15 segundos)
sleep 20

# 5. Verificar que el factor de replicación se restauró
# (los bloques de dn2 ahora están en otro nodo)

# 6. El sistema sigue operativo
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  -v /tmp:/tmp \
  pydfs-client get test.txt -o /tmp/post_fallo.txt

diff /tmp/test.txt /tmp/post_fallo.txt && echo "Sistema operativo ✓"

# 7. Restaurar el DataNode
docker start pydfs-datanode2-1
```

---

## Guías de prueba por comando

El directorio `tests/` contiene guías detalladas con comandos curl, Postman
y Swagger para cada funcionalidad:

| Archivo | Contenido |
|---------|-----------|
| `tests/issue-47-put.md` | Comando `put`: HTTP paso a paso, Postman, verificación en SQLite |
| `tests/issue-48-get.md` | Comando `get`: descarga por bloques, prueba con DataNode caído |
| `tests/issue-49-ls.md` | Comando `ls`: filtrado por directorio, aislamiento entre usuarios |
| `tests/issue-50-rm.md` | Comando `rm`: verificación de borrado en SQLite y volúmenes |
| `tests/issue-51-mkdir-rmdir.md` | Comandos `mkdir`/`rmdir`: directorios lógicos |
| `tests/issue-52-error-handling.md` | Todos los escenarios de error con comandos para reproducirlos |
