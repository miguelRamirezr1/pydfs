# Guía de pruebas — Issue #47 TSK 024: comando `put`

Cubre la partición de un archivo local en bloques, el envío a los
DataNodes asignados y la confirmación al NameNode.

---

## 1. Comandos Docker

### Construir imágenes
```bash
docker compose build
```

### Levantar el clúster completo
```bash
docker compose up -d
```

### Construir y levantar en un solo paso (recomendado tras cambios de código)
```bash
docker compose up --build -d
```

### Ver estado de los contenedores
```bash
docker compose ps
```

### Ver logs en tiempo real
```bash
# Todos los servicios
docker compose logs -f

# Solo NameNode
docker compose logs -f namenode

# Solo DataNode1
docker compose logs -f datanode1
```

### Detener el clúster
```bash
docker compose down
```

### Detener y eliminar volúmenes (reset completo)
```bash
docker compose down -v
```

### Recrear un servicio específico (para aplicar nuevas variables de entorno)
```bash
docker compose up -d --force-recreate namenode
```

### Abrir una shell dentro de un contenedor
```bash
docker exec -it pydfs-namenode-1 bash
docker exec -it pydfs-datanode1-1 bash
```

### Inspeccionar la base de datos SQLite directamente
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT * FROM files').fetchall():
    print(dict(r))
"
```

---

## 2. Preparación del entorno

### 2.1 Verificar que los DataNodes están activos
```bash
curl -s http://localhost:8000/datanodes/status | python3 -m json.tool
```
Deben aparecer dn1, dn2, dn3 con `"status": "active"`.

### 2.2 Registrar usuario (solo la primera vez — primer usuario no requiere token admin)
```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}' | python3 -m json.tool
```

### 2.3 Obtener token JWT y guardarlo
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "$TOKEN" > ~/.dfs_token
echo "Token guardado"
```

---

## 3. Crear archivos de prueba

### Archivo pequeño — 1 bloque con BLOCK_SIZE=67108864 (64 MB)
```bash
echo "Hola DFS" > /tmp/hola.txt
wc -c /tmp/hola.txt   # muestra el tamaño en bytes
```

### Archivo de 3 bloques — requiere BLOCK_SIZE=3
```bash
printf "aaa" > /tmp/bloque0.txt
printf "bbb" > /tmp/bloque1.txt
printf "ccc" > /tmp/bloque2.txt
cat /tmp/bloque0.txt /tmp/bloque1.txt /tmp/bloque2.txt > /tmp/test.txt
# test.txt = aaabbbccc (9 bytes)
# Con BLOCK_SIZE=3: ceil(9/3) = 3 bloques
```

### Cambiar BLOCK_SIZE para pruebas de partición
Editar `docker-compose.yml`:
```yaml
environment:
  - BLOCK_SIZE=3   # en lugar de 67108864
```
Luego recrear el namenode:
```bash
docker compose up -d --force-recreate namenode
```

---

## 4. CLI — comando `put`

### Subir con nombre de archivo como ruta remota (por defecto)
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt
# Ruta remota resultante: test.txt
```

### Subir especificando ruta remota
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt --remote-path docs/test.txt
```

### Subir desde el contenedor cliente (cuando los DataNodes son internos)
```bash
# El token debe estar en /tmp/.dfs_token en el host
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  -v /tmp/test.txt:/tmp/test.txt:ro \
  pydfs-client put /tmp/test.txt
```

### Salida esperada (éxito)
```
Subido: test.txt (9 bytes, 3 bloque(s))
```

---

## 5. HTTP — protocolo paso a paso con curl

El comando `put` realiza 3 llamadas HTTP. Aquí el equivalente manual:

### Paso 1: Planificar la subida (NameNode)
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "test.txt", "size": 9}' | python3 -m json.tool
```

**Respuesta:**
```json
{
  "file_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "block_size": 3,
  "blocks": [
    {
      "block_id": "aaaaaaaa-...",
      "seq": 0,
      "primary_node_id": "dn1",
      "primary_url": "http://datanode1:8001",
      "replica_node_id": "dn2",
      "replica_url": "http://datanode2:8001"
    },
    ...
  ]
}
```
Guarda `file_id` y los `block_id` de cada bloque.

### Paso 2: Enviar cada bloque al DataNode primario
```bash
# Bloque seq=0 → DataNode1 (localhost:8001 desde el host)
# replica_host usa el nombre interno Docker porque dn1 conecta a dn2 internamente
curl -s -X PUT \
  "http://localhost:8001/blocks/<block_id_seq0>?replica_host=datanode2&replica_port=8001" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/tmp/bloque0.txt | python3 -m json.tool

# Bloque seq=1 → DataNode2 (localhost:8002 desde el host)
curl -s -X PUT \
  "http://localhost:8002/blocks/<block_id_seq1>?replica_host=datanode3&replica_port=8001" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/tmp/bloque1.txt | python3 -m json.tool

# Bloque seq=2 → DataNode3 (localhost:8003 desde el host)
curl -s -X PUT \
  "http://localhost:8003/blocks/<block_id_seq2>?replica_host=datanode1&replica_port=8001" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/tmp/bloque2.txt | python3 -m json.tool
```

**Respuesta por bloque:**
```json
{"status": "ok", "block_id": "aaaaaaaa-..."}
```

### Paso 3: Confirmar al NameNode
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X POST http://localhost:8000/files/<file_id>/confirm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "test.txt",
    "size": 9,
    "blocks": [
      {"block_id": "<block_id_seq0>", "seq": 0, "primary_node_id": "dn1", "replica_node_id": "dn2"},
      {"block_id": "<block_id_seq1>", "seq": 1, "primary_node_id": "dn2", "replica_node_id": "dn3"},
      {"block_id": "<block_id_seq2>", "seq": 2, "primary_node_id": "dn3", "replica_node_id": "dn1"}
    ]
  }' | python3 -m json.tool
```

**Respuesta:**
```json
{"ok": true, "file_id": "xxxxxxxx-..."}
```

---

## 6. Postman

### Paso 1 — POST /files/upload
- **Método:** POST
- **URL:** `http://localhost:8000/files/upload`
- **Headers:**
  - `Authorization: Bearer <token>`
  - `Content-Type: application/json`
- **Body (raw JSON):**
```json
{"path": "test.txt", "size": 9}
```
- **Acción:** Copia `file_id` y todos los `block_id` de la respuesta.

### Paso 2 — PUT /blocks/{block_id} en cada DataNode
- **Método:** PUT
- **URL:** `http://localhost:8001/blocks/<block_id_seq0>?replica_host=datanode2&replica_port=8001`
- **Headers:** `Content-Type: application/octet-stream`
- **Body:** Binary → seleccionar el archivo desde disco
- Repetir para cada bloque ajustando puerto y `replica_host`.

### Paso 3 — POST /files/{file_id}/confirm
- **Método:** POST
- **URL:** `http://localhost:8000/files/<file_id>/confirm`
- **Headers:**
  - `Authorization: Bearer <token>`
  - `Content-Type: application/json`
- **Body (raw JSON):** array de bloques con `block_id`, `seq`, `primary_node_id`, `replica_node_id`.

---

## 7. Swagger (http://localhost:8000/docs)

| Paso | Endpoint | Disponible en Swagger |
|------|----------|-----------------------|
| 1    | POST /files/upload | ✅ — ingresa path y size manualmente |
| 2    | PUT /blocks/{id} DataNode | ⚠️ — Swagger no soporta envío de archivos binarios crudos |
| 3    | POST /files/{id}/confirm | ✅ — pega file_id y block_ids de la respuesta del paso 1 |

Para el paso 2 usa curl o Postman (Body → Binary).

---

## 8. Verificación post-put

### Confirmar bloques en SQLite
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT b.seq, b.block_id, b.datanode
    FROM blocks b JOIN files f ON f.file_id = b.file_id
    WHERE f.path = \"test.txt\" ORDER BY b.seq, b.datanode
''').fetchall()
for r in rows: print(dict(r))
"
```

### Confirmar archivos físicos en cada DataNode
```bash
docker exec pydfs-datanode1-1 ls /app/blocks/
docker exec pydfs-datanode2-1 ls /app/blocks/
docker exec pydfs-datanode3-1 ls /app/blocks/
```

---

## 9. Casos de error esperados

| Situación | Mensaje CLI | HTTP Status |
|-----------|------------|-------------|
| Archivo local no existe | `Error: Archivo local no encontrado: /ruta` | — (validación local) |
| Ruta remota ya existe | `Error: Ya existe un archivo en esa ruta` | 409 Conflict |
| Sin token / token inválido | `Error: Sesión expirada o inválida.` | 401 Unauthorized |
| Menos de 2 DataNodes activos | `Error: Se necesitan al menos 2 DataNodes activos` | 503 Service Unavailable |
| DataNode no responde al subir bloque | `Error: DataNode no disponible al subir bloque 0: ...` | — |
