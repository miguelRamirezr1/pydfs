# Guía de pruebas — Issue #50 TSK 027: comando `rm`

Cubre la eliminación de un archivo del DFS: borrado de metadatos en
SQLite y notificación a los DataNodes para borrar los bloques físicos.

---

## 1. Comandos Docker

### Levantar el clúster
```bash
docker compose up --build -d
```

### Ver logs del NameNode (útil para ver notificaciones de borrado)
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

### Verificar bloques físicos en un DataNode
```bash
docker exec pydfs-datanode1-1 ls /app/blocks/
docker exec pydfs-datanode2-1 ls /app/blocks/
docker exec pydfs-datanode3-1 ls /app/blocks/
```

### Verificar estado de la base de datos
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
print('--- files ---')
for r in conn.execute('SELECT path, size FROM files WHERE is_dir=0').fetchall():
    print(dict(r))
print('--- blocks ---')
for r in conn.execute('SELECT block_id, file_id, seq, datanode FROM blocks').fetchall():
    print(dict(r))
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

### 2.2 Subir un archivo de prueba
```bash
printf "aaabbbccc" > /tmp/test.txt
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt
```

### 2.3 Verificar que el archivo está en el DFS
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
# Debe mostrar: FILE  test.txt  9 bytes  ...
```

---

## 3. CLI — comando `rm`

### Eliminar un archivo
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rm test.txt
```

**Salida esperada:**
```
Eliminado: test.txt
```

### Verificar que fue eliminado
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
# Debe mostrar: (vacío)
```

### Verificar que los bloques físicos fueron borrados de los DataNodes
```bash
docker exec pydfs-datanode1-1 ls /app/blocks/
docker exec pydfs-datanode2-1 ls /app/blocks/
docker exec pydfs-datanode3-1 ls /app/blocks/
# Todos deben estar vacíos
```

### Eliminar archivo dentro de un directorio
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rm docs/fileB.txt
```

### Ejecutar desde contenedor cliente
```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client rm test.txt
```

---

## 4. HTTP — protocolo con curl

### Eliminar un archivo
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X DELETE http://localhost:8000/files/test.txt \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP %{http_code}\n"
```

**Respuesta esperada:** HTTP 204 (sin body)

### Eliminar archivo en subdirectorio
```bash
curl -s -X DELETE "http://localhost:8000/files/docs/fileB.txt" \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP %{http_code}\n"
```

### Verificar eliminación con GET
```bash
curl -s http://localhost:8000/files/test.txt \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Respuesta: {"detail": "Archivo no encontrado"} con HTTP 404
```

### Flujo completo: subir → verificar → borrar → verificar
```bash
TOKEN=$(cat ~/.dfs_token)

# Subir
curl -s -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "temp.txt", "size": 3}' | python3 -m json.tool

# (completar pasos 2 y 3 del put — ver issue-47-put.md)

# Listar
curl -s http://localhost:8000/files \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Borrar
curl -s -X DELETE http://localhost:8000/files/temp.txt \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP %{http_code}\n"

# Verificar
curl -s http://localhost:8000/files \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 5. Postman

### DELETE /files/{path}
- **Método:** DELETE
- **URL:** `http://localhost:8000/files/test.txt`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** ninguno
- **Respuesta esperada:** 204 No Content (sin body)

Para archivos en subdirectorios:
- **URL:** `http://localhost:8000/files/docs/fileB.txt`

---

## 6. Swagger (http://localhost:8000/docs)

| Endpoint | Disponible | Notas |
|----------|-----------|-------|
| DELETE /files/{path} | ✅ | Ingresa el path del archivo en el campo `path` |

Pasos en Swagger:
1. Clic en `DELETE /files/{path}` → Try it out
2. Ingresar el path, ej. `test.txt` o `docs/fileB.txt`
3. Clic Execute
4. Respuesta 204 indica éxito

---

## 7. Verificar borrado en SQLite y volúmenes

### Antes del rm
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
files = conn.execute('SELECT path FROM files WHERE is_dir=0').fetchall()
blocks = conn.execute('SELECT COUNT(*) as n FROM blocks').fetchone()
print('Archivos:', [r['path'] for r in files])
print('Total bloques en BD:', blocks['n'])
"
```

### Después del rm
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
files = conn.execute('SELECT path FROM files WHERE is_dir=0').fetchall()
blocks = conn.execute('SELECT COUNT(*) as n FROM blocks').fetchone()
print('Archivos:', [r['path'] for r in files])
print('Total bloques en BD:', blocks['n'])
# Ambos deben reflejar la eliminación
"

# Verificar que los bloques físicos desaparecieron
for dn in pydfs-datanode1-1 pydfs-datanode2-1 pydfs-datanode3-1; do
  echo "=== $dn ==="
  docker exec $dn ls /app/blocks/ 2>/dev/null || echo "(vacío)"
done
```

---

## 8. Casos de error esperados

| Situación | Mensaje CLI | HTTP Status |
|-----------|------------|-------------|
| Archivo no existe | `Error: Archivo no encontrado` | 404 Not Found |
| Sin token / token inválido | `Error: Sesión expirada o inválida.` | 401 Unauthorized |
| Intentar borrar archivo de otro usuario | `Error: Archivo no encontrado` | 404 Not Found |

**Nota sobre idempotencia de DataNodes:** Si un DataNode está caído cuando
se ejecuta `rm`, el NameNode elimina los metadatos de SQLite de todas formas
y registra una advertencia en logs. El bloque físico huérfano quedará en
el DataNode pero no será accesible desde el DFS.
