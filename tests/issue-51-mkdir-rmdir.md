# Guía de pruebas — Issue #51 TSK 028: comandos `mkdir` y `rmdir`

Cubre la creación y eliminación de directorios lógicos en el DFS.
Los directorios son entradas en SQLite con `is_dir=1` — no tienen
bloques ni ocupan espacio en los DataNodes.

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

### Inspeccionar directorios en SQLite
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
dirs = conn.execute(
    'SELECT owner, path, created_at FROM files WHERE is_dir=1 ORDER BY path'
).fetchall()
for d in dirs:
    print(f'DIR  owner={d[\"owner\"]}  path={d[\"path\"]}')
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

---

## 3. CLI — comando `mkdir`

### Crear directorio en la raíz
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs
```

**Salida esperada:**
```
Directorio creado: docs
```

### Crear directorio anidado
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs/proyectos
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs/proyectos/2026
```

### Verificar con ls
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
```

**Salida esperada:**
```
DIR   docs                    0 bytes  2026-05-24T...
DIR   docs/proyectos          0 bytes  2026-05-24T...
DIR   docs/proyectos/2026     0 bytes  2026-05-24T...
```

### Ejecutar desde contenedor cliente
```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client mkdir docs
```

---

## 4. CLI — comando `rmdir`

### Eliminar directorio vacío
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rmdir docs/proyectos/2026
```

**Salida esperada:**
```
Directorio eliminado: docs/proyectos/2026
```

### Flujo completo: crear → poblar → intentar borrar → vaciar → borrar
```bash
# 1. Crear directorio
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir proyectos

# 2. Subir archivo dentro del directorio
printf "contenido" > /tmp/archivo.txt
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/archivo.txt --remote-path proyectos/archivo.txt

# 3. Intentar rmdir (debe fallar — no vacío)
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rmdir proyectos
# Error: El directorio no está vacío

# 4. Borrar el archivo primero
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rm proyectos/archivo.txt

# 5. Ahora sí rmdir funciona
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rmdir proyectos
# Directorio eliminado: proyectos
```

### Ejecutar desde contenedor cliente
```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  pydfs-client rmdir docs
```

---

## 5. HTTP — protocolo con curl

### Crear directorio — POST /dirs/{path}
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X POST http://localhost:8000/dirs/docs \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP %{http_code}\n" | python3 -m json.tool
```

**Respuesta esperada (201):**
```json
{"path": "docs"}
```

### Crear directorio anidado
```bash
curl -s -X POST "http://localhost:8000/dirs/docs/proyectos" \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP %{http_code}\n"
```

### Eliminar directorio — DELETE /dirs/{path}
```bash
curl -s -X DELETE http://localhost:8000/dirs/docs \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP %{http_code}\n"
```

**Respuesta esperada (204):** sin body

### Intentar eliminar directorio no vacío
```bash
curl -s -X DELETE http://localhost:8000/dirs/docs \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Respuesta: {"detail": "El directorio no está vacío"} con HTTP 409
```

### Intentar crear directorio duplicado
```bash
curl -s -X POST http://localhost:8000/dirs/docs \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Respuesta: {"detail": "El directorio ya existe"} con HTTP 409
```

---

## 6. Postman

### POST /dirs/{path} — crear directorio
- **Método:** POST
- **URL:** `http://localhost:8000/dirs/docs`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** ninguno
- **Respuesta esperada:** 201 Created `{"path": "docs"}`

### DELETE /dirs/{path} — eliminar directorio
- **Método:** DELETE
- **URL:** `http://localhost:8000/dirs/docs`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** ninguno
- **Respuesta esperada:** 204 No Content

---

## 7. Swagger (http://localhost:8000/docs)

| Endpoint | Disponible | Notas |
|----------|-----------|-------|
| POST /dirs/{path} | ✅ | Ingresa el path en el campo path |
| DELETE /dirs/{path} | ✅ | Ingresa el path en el campo path |

Pasos en Swagger:
1. Clic en `POST /dirs/{path}` → Try it out
2. Ingresar el path: `docs` o `docs/proyectos`
3. Clic Execute → 201 indica éxito
4. Para borrar: `DELETE /dirs/{path}` → ingresar path → Execute → 204 indica éxito

---

## 8. Verificar en SQLite

### Ver directorios creados
```bash
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
rows = conn.execute(
    'SELECT owner, path, is_dir, created_at FROM files ORDER BY path'
).fetchall()
for r in rows:
    tipo = 'DIR ' if r['is_dir'] else 'FILE'
    print(f'{tipo}  {r[\"owner\"]}  {r[\"path\"]}')
"
```

### Verificar que rmdir borra solo la entrada del directorio (no afecta bloques)
```bash
# Contar bloques antes y después de rmdir
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
print('Total bloques:', conn.execute('SELECT COUNT(*) FROM blocks').fetchone()[0])
print('Total dirs:', conn.execute('SELECT COUNT(*) FROM files WHERE is_dir=1').fetchone()[0])
"
```

---

## 9. Casos de error esperados

| Situación | Mensaje CLI | HTTP Status |
|-----------|------------|-------------|
| mkdir sobre ruta ya existente | `Error: El directorio ya existe` | 409 Conflict |
| rmdir sobre directorio no vacío | `Error: El directorio no está vacío` | 409 Conflict |
| rmdir sobre directorio inexistente | `Error: Directorio no encontrado` | 404 Not Found |
| Sin token / token inválido | `Error: Sesión expirada o inválida.` | 401 Unauthorized |

---

## 10. Notas sobre directorios lógicos

- Los directorios **no tienen bloques** — solo son filas en `files` con `is_dir=1`.
- `rmdir` verifica que no haya entradas cuyo `path` empiece con `docs/` antes de borrar.
- No existe `mkdir -p` — cada nivel debe crearse por separado.
- Un directorio padre no necesita existir para crear uno hijo (`mkdir docs/proyectos`
  funciona aunque `docs` no exista aún).
