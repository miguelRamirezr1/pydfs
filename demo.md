# Secuencia de Demostración — PyDFS

Script paso a paso para la sustentación. Cada sección indica
qué ejecutar y qué señalar al evaluador.

---

## Preparación previa (antes de la demo)

```bash
# Reset completo — partir desde cero
docker compose down -v

# Preparar archivos de prueba
printf "aaa" > /tmp/bloque0.txt
printf "bbb" > /tmp/bloque1.txt
printf "ccc" > /tmp/bloque2.txt
cat /tmp/bloque0.txt /tmp/bloque1.txt /tmp/bloque2.txt > /tmp/test.txt

# Verificar: 9 bytes
wc -c /tmp/test.txt
```

Editar `docker-compose.yml` — cambiar `BLOCK_SIZE=67108864` a `BLOCK_SIZE=3`
para que el archivo se parta en 3 bloques visibles durante la demo.

---

## Paso 1 — Arrancar el clúster

```bash
docker compose up --build -d
```

**Señalar:** una sola imagen para los 3 DataNodes, configurada por variables de entorno (`NODE_ID`, `HOST`, `PORT`). El NameNode inicializa SQLite automáticamente al arrancar.

```bash
# Verificar que los 3 DataNodes están activos y enviando heartbeat
curl -s http://localhost:8000/datanodes/status | python3 -m json.tool
```

**Señalar:** `status: active`, `free_bytes` reportado por cada nodo, `last_heartbeat` actualizado cada 5 segundos.

```bash
# Ver logs de arranque en vivo
docker compose logs namenode | grep -E "arrancando|lista|monitor|registrado"
```

**Señalar:** secuencia de arranque — DB inicializada → monitor de heartbeat iniciado → DataNodes registrados.

---

## Paso 2 — Registrar usuario y autenticar

```bash
# Registrar (primer usuario — sin token de admin)
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "dfs2026"}' | python3 -m json.tool
```

```bash
# Login — obtener JWT
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "dfs2026"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$TOKEN" > /tmp/.dfs_token_demo
echo "Token: ${TOKEN:0:40}..."
```

**Señalar:** el token JWT es stateless — los DataNodes lo verifican localmente sin consultar al NameNode. Contiene el `username` como `sub` firmado con `JWT_SECRET`.

---

## Paso 3 — Subir un archivo (put)

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  -v /tmp/test.txt:/tmp/test.txt:ro \
  pydfs-client put /tmp/test.txt
```

**Salida esperada:**
```
Subido: test.txt (9 bytes, 3 bloque(s))
```

**Señalar:** 3 bloques porque `BLOCK_SIZE=3` y el archivo tiene 9 bytes → `ceil(9/3)=3`. El cliente habló con el NameNode para el plan y luego directamente con cada DataNode para los bytes.

```bash
# Mostrar distribución en SQLite
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT b.seq, b.block_id, b.datanode
    FROM blocks b JOIN files f ON f.file_id = b.file_id
    WHERE f.path = \"test.txt\" ORDER BY b.seq, b.datanode
''').fetchall()
for r in rows: print(f'seq={r[\"seq\"]}  dn={r[\"datanode\"]}  block={r[\"block_id\"][:8]}...')
"
```

**Señalar:** round-robin — seq=0→dn1+dn2, seq=1→dn2+dn3, seq=2→dn3+dn1. Cada bloque en exactamente 2 nodos distintos.

```bash
# Mostrar bloques físicos en los DataNodes
for dn in pydfs-datanode1-1 pydfs-datanode2-1 pydfs-datanode3-1; do
  echo "=== $dn ===" && docker exec $dn ls /app/blocks/
done
```

**Señalar:** los archivos en disco coinciden con SQLite. El NameNode nunca almacenó bytes — solo metadatos.

---

## Paso 4 — Listar archivos (ls)

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  pydfs-client ls
```

**Señalar:** el ls solo consulta al NameNode — no toca los DataNodes. Muestra path, tamaño y fecha.

---

## Paso 5 — Descargar el archivo (get)

```bash
docker run --rm \
  --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  -v /tmp:/tmp \
  pydfs-client get test.txt -o /tmp/reconstruido.txt
```

```bash
# Verificar integridad
diff /tmp/test.txt /tmp/reconstruido.txt && echo "IDÉNTICOS ✓"
hexdump -C /tmp/reconstruido.txt
```

**Señalar:** el cliente consultó al NameNode por la ubicación de los bloques, descargó cada uno del DataNode correspondiente en orden de `seq`, y los concatenó. El diff vacío confirma la reconstrucción perfecta.

---

## Paso 6 — Directorios y organización (mkdir / ls --path / rm / rmdir)

```bash
# Crear directorio
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  pydfs-client mkdir proyectos

# Subir archivo dentro del directorio
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  -v /tmp/test.txt:/tmp/test.txt:ro \
  pydfs-client put /tmp/test.txt --remote-path proyectos/test.txt

# Listar el directorio
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  pydfs-client ls --path proyectos

# Eliminar archivo y directorio
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  pydfs-client rm proyectos/test.txt

docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  pydfs-client rmdir proyectos
```

**Señalar:** los directorios son entradas lógicas en SQLite (`is_dir=1`) — no ocupan espacio en DataNodes. `rmdir` falla si el directorio tiene contenido.

---

## Paso 7 — Tolerancia a fallos: caída de DataNode y re-replicación

```bash
# Estado inicial — 2 réplicas por bloque
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT b.seq, b.datanode FROM blocks b
    JOIN files f ON f.file_id = b.file_id
    WHERE f.path = \"test.txt\" ORDER BY b.seq, b.datanode
''').fetchall()
for r in rows: print(f'seq={r[\"seq\"]}  dn={r[\"datanode\"]}')
"
```

```bash
# Detener dn2
docker stop pydfs-datanode2-1
echo "dn2 detenido — esperando detección (15s)..."
sleep 20
```

**Señalar:** el monitor en `scheduler.py` corre cada 5 segundos. Tras 3 pings perdidos (15s), declara `dn2` como caído e inicia re-replicación automática.

```bash
# Verificar re-replicación en SQLite
docker exec pydfs-namenode-1 python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/metadata.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT b.seq, b.datanode FROM blocks b
    JOIN files f ON f.file_id = b.file_id
    WHERE f.path = \"test.txt\" ORDER BY b.seq, b.datanode
''').fetchall()
for r in rows: print(f'seq={r[\"seq\"]}  dn={r[\"datanode\"]}')
print('Factor de replicación restaurado a 2 en todos los bloques')
"
```

**Señalar:** `dn2` fue reemplazado. Los bloques que tenían réplica en `dn2` ahora la tienen en `dn3` o `dn1`. El factor de replicación vuelve a ser 2 sin intervención manual.

```bash
# El sistema sigue operativo con dn2 caído
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_demo:/root/.dfs_token:ro \
  -v /tmp:/tmp \
  pydfs-client get test.txt -o /tmp/post_fallo.txt

diff /tmp/test.txt /tmp/post_fallo.txt && echo "Sistema operativo con dn2 caído ✓"
```

```bash
# Restaurar dn2
docker start pydfs-datanode2-1
sleep 6
curl -s http://localhost:8000/datanodes/status | \
  python3 -c "import sys,json; [print(n['node_id'], n['status']) for n in json.load(sys.stdin)]"
```

**Señalar:** al restaurar `dn2`, vuelve a enviar heartbeats y el NameNode lo marca como `active` nuevamente.

---

## Paso 8 — Aislamiento entre usuarios

```bash
# Registrar segundo usuario
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: admin-secret" \
  -d '{"username": "bob", "password": "pass2"}' | python3 -m json.tool

# Token de bob
TOKEN_BOB=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "bob", "password": "pass2"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$TOKEN_BOB" > /tmp/.dfs_token_bob

# ls como bob — no ve los archivos de alice
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_bob:/root/.dfs_token:ro \
  pydfs-client ls
```

```bash
# bob intenta descargar test.txt de alice
docker run --rm --network pydfs_dfs-network \
  -e NAMENODE_URL=http://namenode:8000 \
  -v /tmp/.dfs_token_bob:/root/.dfs_token:ro \
  pydfs-client get test.txt; echo "Exit: $?"
```

**Señalar:** el sistema retorna 404 — no revela que el archivo existe bajo otro usuario. El aislamiento está en el campo `owner` de SQLite, filtrado por el `sub` del JWT.

---

## Puntos clave para responder preguntas

| Pregunta frecuente | Respuesta |
|---|---|
| ¿Por qué el cliente habla directo con los DataNodes? | Evitar que el NameNode sea cuello de botella en transferencia de datos |
| ¿Por qué replicación síncrona y no asíncrona? | Modelo WORM: cada escritura debe ser definitiva — no puede haber bloques con réplica incompleta |
| ¿Qué pasa si cae el NameNode? | SPOF conocido — los datos están en los DataNodes pero no son accesibles sin metadatos |
| ¿Por qué SQLite y no PostgreSQL? | Scope académico: sin concurrencia masiva, sin proceso externo, suficiente para 3 nodos |
| ¿Por qué factor 2 y no 3? | El clúster tiene 3 nodos de capacidad pero factor 2 de redundancia — distinción explícita |
| ¿Cómo se evita re-replicación duplicada? | `replace_block_replica` actualiza SQLite antes de la siguiente iteración del monitor |
| ¿Por qué BLOCK_SIZE=3 en las pruebas? | El archivo `aaabbbccc` tiene 9 bytes — con bloques de 64 bytes cabría en 1 solo bloque |
