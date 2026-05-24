# Guía de pruebas — Issue #49 TSK 026: comando `ls`

Cubre el listado de archivos y directorios del usuario autenticado,
con y sin filtro de directorio.

---

## 1. Comandos Docker

### Levantar el clúster
```bash
docker compose up --build -d
```

### Ver logs del NameNode
```bash
docker compose logs -f namenode
```

### Estado de los contenedores
```bash
docker compose ps
```

### Detener el clúster
```bash
docker compose down
```

### Abrir shell en el NameNode
```bash
docker exec -it pydfs-namenode-1 bash
```

### Inspeccionar la tabla files en SQLite
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT owner, path, size, is_dir, created_at FROM files ORDER BY owner, path').fetchall():
    tipo = 'DIR ' if r['is_dir'] else 'FILE'
    print(f'{tipo}  owner={r[\"owner\"]}  {r[\"path\"]}  {r[\"size\"]} bytes')
"
```

---

## 2. Preparación del entorno

### 2.1 Obtener token
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$TOKEN" > ~/.dfs_token
```

### 2.2 Crear estructura de prueba
```bash
# Crear directorios
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs/proyectos

# Crear archivos de prueba
printf "contenido A" > /tmp/fileA.txt
printf "contenido B" > /tmp/fileB.txt

# Subir archivos
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/fileA.txt
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/fileB.txt --remote-path docs/fileB.txt
```

---

## 3. CLI — comando `ls`

### Listar todos los archivos y directorios
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
```

**Salida esperada:**
```
FILE  fileA.txt         11 bytes  2026-05-24T...
DIR   docs              0 bytes   2026-05-24T...
DIR   docs/proyectos    0 bytes   2026-05-24T...
FILE  docs/fileB.txt    11 bytes  2026-05-24T...
```

### Listar filtrando por directorio
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls --path docs
```

**Salida esperada (solo contenido dentro de docs/):**
```
DIR   docs/proyectos    0 bytes   2026-05-24T...
FILE  docs/fileB.txt    11 bytes  2026-05-24T...
```

### Listar directorio vacío
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls --path docs/proyectos
```

**Salida esperada:**
```
(vacío)
```

### Ejecutar desde contenedor cliente
```bash
# Sin filtro
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client ls

# Con filtro de directorio
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client ls --path docs
```

---

## 4. HTTP — protocolo con curl

### Listar todos los archivos del usuario
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s http://localhost:8000/files \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Respuesta:**
```json
[
  {"file_id": "...", "owner": "testuser", "path": "fileA.txt", "size": 11, "is_dir": 0, "created_at": "..."},
  {"file_id": "...", "owner": "testuser", "path": "docs",      "size": 0,  "is_dir": 1, "created_at": "..."},
  {"file_id": "...", "owner": "testuser", "path": "docs/fileB.txt", "size": 11, "is_dir": 0, "created_at": "..."}
]
```

### Listar filtrando por directorio
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s "http://localhost:8000/files?directory=docs" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Nota:** el parámetro `directory` filtra rutas que empiezan con `docs/`.

### Listar directorio que no existe (devuelve lista vacía, no error)
```bash
curl -s "http://localhost:8000/files?directory=inexistente" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Respuesta: []
```

---

## 5. Postman

### GET /files (todos los archivos)
- **Método:** GET
- **URL:** `http://localhost:8000/files`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** ninguno

### GET /files con filtro de directorio
- **Método:** GET
- **URL:** `http://localhost:8000/files`
- **Params:** `directory = docs`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** ninguno

---

## 6. Swagger (http://localhost:8000/docs)

| Endpoint | Disponible | Notas |
|----------|-----------|-------|
| GET /files | ✅ | El parámetro `directory` aparece como query param opcional |

Pasos en Swagger:
1. Clic en `GET /files` → Try it out
2. Dejar `directory` vacío para listar todo, o ingresar `docs` para filtrar
3. Clic Execute
4. La respuesta muestra el JSON con todos los archivos del usuario autenticado

**Requisito:** tener el token en el candado de Authorize (Bearer token).

---

## 7. Verificar aislamiento entre usuarios

```bash
# Obtener token de user2
TOKEN2=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user2", "password": "pass2"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# ls como user2 — no debe ver archivos de testuser
curl -s http://localhost:8000/files \
  -H "Authorization: Bearer $TOKEN2" | python3 -m json.tool
```

---

## 8. Casos de error esperados

| Situación | Mensaje CLI | HTTP Status |
|-----------|------------|-------------|
| Sin token / token inválido | `Error: Sesión expirada o inválida.` | 401 Unauthorized |
| Directorio inexistente | lista vacía `(vacío)` | 200 OK (lista vacía `[]`) |
