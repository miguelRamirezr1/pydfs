# Guía de pruebas — Issue #48 TSK 025: comando `get`

Cubre la descarga de metadatos desde el NameNode, la descarga de
bloques desde los DataNodes y la reconstrucción del archivo local.

---

## 1. Comandos Docker

### Levantar el clúster
```bash
docker compose up --build -d
```

### Ver logs en tiempo real
```bash
docker compose logs -f                  # todos
docker compose logs -f namenode         # solo NameNode
docker compose logs -f datanode1        # solo DataNode1
```

### Estado de los contenedores
```bash
docker compose ps
```

### Detener el clúster
```bash
docker compose down
```

### Detener DataNode específico (simular caída)
```bash
docker stop pydfs-datanode2-1
```

### Reiniciar DataNode
```bash
docker start pydfs-datanode2-1
```

### Ejecutar comandos dentro de un contenedor
```bash
docker exec -it pydfs-namenode-1 bash
docker exec pydfs-datanode1-1 ls /app/blocks/
```

---

## 2. Preparación del entorno

### 2.1 Verificar DataNodes activos
```bash
curl -s http://localhost:8000/datanodes/status | python3 -m json.tool
```

### 2.2 Obtener token
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$TOKEN" > ~/.dfs_token
```

### 2.3 Prerequisito: subir un archivo primero
```bash
printf "aaa" > /tmp/bloque0.txt
printf "bbb" > /tmp/bloque1.txt
printf "ccc" > /tmp/bloque2.txt
cat /tmp/bloque0.txt /tmp/bloque1.txt /tmp/bloque2.txt > /tmp/test.txt

# Con BLOCK_SIZE=3 en docker-compose.yml para obtener 3 bloques
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt
```

---

## 3. CLI — comando `get`

### Descargar con nombre de archivo como salida (por defecto)
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py get test.txt
# Descarga en el directorio actual como test.txt
```

### Descargar especificando ruta de salida
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py get test.txt -o /tmp/reconstruido.txt
```

### Descargar desde subdirectorio
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py get docs/test.txt -o /tmp/docs_test.txt
```

### Ejecutar desde contenedor cliente
```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token:/root/.dfs_token:ro \
  -v /tmp:/tmp \
  pydfs-client get test.txt -o /tmp/reconstruido.txt
```

### Verificar que el archivo fue reconstruido correctamente
```bash
diff /tmp/test.txt /tmp/reconstruido.txt && echo "IDÉNTICOS ✓" || echo "DIFERENCIA ✗"
hexdump -C /tmp/reconstruido.txt
```

### Salida esperada (éxito)
```
Descargado: /tmp/reconstruido.txt
```

---

## 4. HTTP — protocolo paso a paso con curl

El comando `get` realiza N+1 llamadas HTTP (1 al NameNode + N por cada bloque).

### Paso 1: Obtener metadatos y ubicación de bloques (NameNode)
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s http://localhost:8000/files/test.txt \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Respuesta:**
```json
{
  "file_id": "xxxxxxxx-...",
  "path": "test.txt",
  "size": 9,
  "created_at": "2026-05-24T...",
  "blocks": [
    {"block_id": "aaaaaaaa-...", "seq": 0, "datanode": "dn1", "host": "datanode1", "port": 8001},
    {"block_id": "aaaaaaaa-...", "seq": 0, "datanode": "dn2", "host": "datanode2", "port": 8001},
    {"block_id": "bbbbbbbb-...", "seq": 1, "datanode": "dn2", "host": "datanode2", "port": 8001},
    {"block_id": "bbbbbbbb-...", "seq": 1, "datanode": "dn3", "host": "datanode3", "port": 8001},
    {"block_id": "cccccccc-...", "seq": 2, "datanode": "dn3", "host": "datanode3", "port": 8001},
    {"block_id": "cccccccc-...", "seq": 2, "datanode": "dn1", "host": "datanode1", "port": 8001}
  ]
}
```

**Nota:** El mismo `block_id` aparece dos veces (una por réplica). Para descargar
usa solo la primera aparición de cada `seq`, en orden ascendente.

### Paso 2: Descargar cada bloque del DataNode correspondiente

Mapeo de puertos (host → contenedor):
- datanode1:8001 → `localhost:8001`
- datanode2:8001 → `localhost:8002`
- datanode3:8001 → `localhost:8003`

```bash
# seq=0 desde dn1 (localhost:8001)
curl -s http://localhost:8001/blocks/<block_id_seq0> -o /tmp/chunk0.bin

# seq=1 desde dn2 (localhost:8002)
curl -s http://localhost:8002/blocks/<block_id_seq1> -o /tmp/chunk1.bin

# seq=2 desde dn3 (localhost:8003)
curl -s http://localhost:8003/blocks/<block_id_seq2> -o /tmp/chunk2.bin
```

### Paso 3: Reconstruir el archivo concatenando bloques en orden
```bash
cat /tmp/chunk0.bin /tmp/chunk1.bin /tmp/chunk2.bin > /tmp/reconstruido_manual.txt
hexdump -C /tmp/reconstruido_manual.txt
# Debe mostrar: aaabbbccc
```

---

## 5. Postman

### Paso 1 — GET /files/{path}
- **Método:** GET
- **URL:** `http://localhost:8000/files/test.txt`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** ninguno
- **Acción:** Copia los `block_id` de cada `seq` único (el primero de cada par).

### Paso 2 — GET /blocks/{block_id} en cada DataNode
- **Método:** GET
- **URL:** `http://localhost:8001/blocks/<block_id_seq0>`
- **Headers:** ninguno
- **Body:** ninguno
- **Guardar respuesta:** Send → Save Response → Save to file (`chunk0.bin`)
- Repetir para cada bloque con el puerto correcto del DataNode.

### Paso 3 — Reconstruir manualmente
Concatenar los archivos binarios descargados en orden de `seq`.

---

## 6. Swagger (http://localhost:8000/docs)

| Paso | Endpoint | Disponible en Swagger |
|------|----------|-----------------------|
| 1    | GET /files/{path} | ✅ — ingresa el path del archivo |
| 2    | GET /blocks/{id} en DataNode | ✅ en `http://localhost:8001/docs` — pero la respuesta binaria no se muestra bien en el navegador |

Para descargar el archivo binario del bloque usa curl o Postman (Save Response).

---

## 7. Verificar contenido de bloques en los DataNodes

```bash
# Ver bytes de un bloque específico
docker exec pydfs-datanode1-1 cat /app/blocks/<block_id>

# Listar todos los bloques de un DataNode
docker exec pydfs-datanode1-1 ls -la /app/blocks/

# Ver tamaño de cada bloque
docker exec pydfs-datanode1-1 du -b /app/blocks/*
```

---

## 8. Prueba de get con DataNode caído

```bash
# Detener dn1
docker stop pydfs-datanode1-1

# Esperar re-replicación (15 segundos)
sleep 20

# El get debe funcionar con las réplicas en dn2 y dn3
NAMENODE_URL=http://localhost:8000 python3 client/cli.py get test.txt -o /tmp/post_fallo.txt
diff /tmp/test.txt /tmp/post_fallo.txt && echo "OK — sistema tolerante a fallos ✓"

# Restaurar dn1
docker start pydfs-datanode1-1
```

---

## 9. Casos de error esperados

| Situación | Mensaje CLI | HTTP Status |
|-----------|------------|-------------|
| Archivo no existe en el DFS | `Error: Archivo no encontrado` | 404 Not Found |
| Sin token / token inválido | `Error: Sesión expirada o inválida.` | 401 Unauthorized |
| DataNode no disponible al descargar | `Error: DataNode no disponible al descargar bloque N: ...` | — |
| Bloque no encontrado en DataNode | respuesta 404 del DataNode | 404 Not Found |
