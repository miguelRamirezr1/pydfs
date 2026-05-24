# Informe Técnico Final — PyDFS

**Sistema de Archivos Distribuido estilo HDFS/GFS**
**Estudiante:** Miguel Ramirez
**Repositorio:** https://github.com/miguelRamirezr1/pydfs
**Fecha de entrega:** 24 de mayo de 2026

---

## 1. Introducción

Este informe documenta el diseño, implementación y validación de **PyDFS**, un sistema de archivos distribuido (DFS) minimalista inspirado en HDFS y GFS. El proyecto se desarrolló como ejercicio académico para comprender los principios fundamentales de los sistemas de archivos distribuidos: distribución de datos en bloques, replicación para tolerancia a fallos, coordinación centralizada de metadatos y autenticación de usuarios.

El sistema almacena archivos dividiéndolos en bloques de tamaño fijo y distribuyéndolos entre múltiples nodos de almacenamiento. Un nodo central coordina los metadatos y la autenticación, mientras que los nodos de almacenamiento guardan los bloques físicamente y se replican entre sí.

---

## 2. Contexto: tipos de DFS estudiados

Antes de implementar PyDFS se estudiaron tres tipos de DFS con modelos de consistencia distintos:

### NFS (Network File System)
DFS de acceso remoto puro, operando a nivel de kernel mediante el VFS de Linux. El cliente monta un directorio remoto y lo ve como local — sin copia local ni funcionamiento offline. Usa **replicación pesimista**: antes de escribir adquiere un bloqueo distribuido para garantizar consistencia inmediata. Modelo más simple de DFS pero sin tolerancia a fallos ni distribución de carga.

### Nextcloud (Sync-and-Share DFS)
DFS de sincronización a nivel de aplicación. Cada cliente mantiene una copia local completa. Usa **replicación optimista**: asume que los conflictos son raros, deja que las réplicas diverjan y reconcilia después. Consistencia eventual, no inmediata. Funciona offline. Protocolo WebDAV + sincronización propia.

### PyDFS (estilo HDFS/GFS — este proyecto)
DFS por bloques con modelo WORM (Write Once, Read Many). Combina distribución real de datos entre nodos con tolerancia a fallos mediante replicación activa (factor 2). A diferencia de NFS no hay un único punto de almacenamiento. A diferencia de Nextcloud no hay copia local en el cliente.

| Característica | NFS | Nextcloud | PyDFS |
|---|---|---|---|
| Distribución de bloques | No | No | Sí |
| Replicación | Pesimista | Optimista | Síncrona en pipeline |
| Copia local en cliente | No | Sí | No |
| Tolerancia a fallos | No | Sí | Sí |
| Consistencia | Inmediata | Eventual | Por escritura (WORM) |
| Funcionamiento offline | No | Sí | No |

---

## 3. Arquitectura del sistema

### Modelo: Maestro–Trabajador

```
Cliente (CLI)
    │
    ├──► NameNode :8000   (metadatos, auth, coordinación)
    │        │
    │        └──► SQLite  (persistencia)
    │
    ├──► DataNode1 :8001  (bloques físicos)
    ├──► DataNode2 :8002  (bloques físicos)
    └──► DataNode3 :8003  (bloques físicos)
```

El **NameNode** es el único punto de coordinación. Conoce la ubicación de todos los bloques pero nunca almacena datos. Los **DataNodes** almacenan bloques físicos, se registran en el NameNode al arrancar y envían heartbeats cada 5 segundos. El **cliente** habla con el NameNode para obtener el plan de bloques y luego interactúa directamente con los DataNodes para transferir bytes.

### Stack tecnológico

| Componente | Tecnología | Justificación |
|---|---|---|
| Lenguaje | Python 3.11 | Ecosistema rico, desarrollo ágil |
| Framework API | FastAPI | Swagger automático, async nativo, validación con Pydantic |
| Persistencia | SQLite | Sin servidor externo, librería estándar, suficiente para el scope académico |
| Autenticación | JWT (python-jose) | Stateless — DataNodes verifican tokens sin consultar NameNode |
| Contenedores | Docker + Docker Compose | Red bridge local simula clúster distribuido |
| HTTP client | httpx (async) + requests (sync) | httpx para endpoints async en DataNodes, requests para heartbeat síncrono |
| CLI | Click | Manejo de argumentos, errores descriptivos, exit codes |

**gRPC no se usó** — el setup (protobuf, stubs) tiene un coste alto de configuración y con archivos de prueba pequeños la diferencia de rendimiento es imperceptible. REST es suficiente para el scope.

**MOM (Kafka/RabbitMQ) no se usó** — la re-replicación se maneja con llamadas REST directas del NameNode a los DataNodes. Con 3 nodos no hay suficiente carga para justificar un broker de mensajes.

---

## 4. Estructura del repositorio

```
pydfs/
├── docker-compose.yml
├── CLAUDE.md
├── README.md
├── informe.md
├── postman_flujo_dfs.txt
├── tests/
│   ├── issue-47-put.md
│   ├── issue-48-get.md
│   ├── issue-49-ls.md
│   ├── issue-50-rm.md
│   ├── issue-51-mkdir-rmdir.md
│   └── issue-52-error-handling.md
├── namenode/
│   ├── Dockerfile
│   ├── main.py              ← FastAPI app + lifespan (init DB + monitor)
│   ├── auth.py              ← JWT: create_token, hash_password, verify_password
│   ├── metadata.py          ← Todas las operaciones SQLite
│   ├── scheduler.py         ← Round-Robin + monitor de heartbeat + re-replicación
│   └── routers/
│       ├── auth.py          ← POST /auth/register, POST /auth/login
│       ├── files.py         ← POST /files/upload, POST /files/{id}/confirm,
│       │                      GET /files, GET /files/{path}, DELETE /files/{path}
│       ├── dirs.py          ← POST /dirs/{path}, DELETE /dirs/{path}
│       └── datanodes.py     ← POST /datanodes/register, POST /datanodes/heartbeat,
│                              GET /datanodes/status
├── datanode/
│   ├── Dockerfile
│   ├── main.py              ← FastAPI app + lifespan (start heartbeat)
│   ├── heartbeat.py         ← Thread de registro + heartbeat periódico
│   └── routers/
│       └── blocks.py        ← PUT /blocks/{id}, GET /blocks/{id},
│                              DELETE /blocks/{id}, POST /blocks/{id}/replicate
└── client/
    ├── Dockerfile
    └── cli.py               ← Comandos: login, put, get, ls, rm, mkdir, rmdir
```

---

## 5. Decisiones de diseño

### 5.1 Autenticación — JWT stateless

El cliente se autentica una vez en `POST /auth/login` y recibe un token JWT firmado con `JWT_SECRET`. Los DataNodes verifican ese token localmente sin consultar al NameNode. Esto es crítico porque el cliente habla **directamente** con los DataNodes al transferir bloques — si los DataNodes necesitaran consultar al NameNode por cada bloque, el NameNode se convertiría en un cuello de botella.

### 5.2 Distribución de bloques — Round-Robin

El NameNode mantiene un cursor global que avanza secuencialmente sobre los DataNodes activos. A cada bloque le asigna el DataNode del cursor como primario y el siguiente como réplica. Resultado con 3 nodos:

```
Bloque 0: primario=dn1, réplica=dn2
Bloque 1: primario=dn2, réplica=dn3
Bloque 2: primario=dn3, réplica=dn1
```

Simple, determinista y uniforme con nodos homogéneos. El heartbeat ya reporta `free_bytes` para escalar a una estrategia Least-Used sin cambiar el protocolo.

### 5.3 Replicación — Síncrona en pipeline

El cliente recibe OK **solo cuando las 2 réplicas están confirmadas**. El flujo ocurre dentro de `PUT /blocks/{id}`:

```
Cliente → DataNode primario → (replica síncrona) → DataNode réplica → OK
                                                                       ↑
                                                    Responde al cliente solo aquí
```

Si la replicación falla, el DataNode primario borra su copia y responde 502. Esto garantiza consistencia: nunca hay un bloque con una sola réplica confirmada tras un `put` exitoso.

### 5.4 Factor de replicación — 2

Cada bloque se almacena en exactamente 2 DataNodes distintos. El clúster tiene 3 DataNodes disponibles (capacidad), pero el factor de replicación es 2 (redundancia). Esto permite tolerar la caída de 1 nodo sin pérdida de datos.

### 5.5 Detección de fallos y re-replicación

El monitor en `scheduler.py` corre cada 5 segundos. Un nodo se declara caído tras 15 segundos sin heartbeat (3 pings perdidos). Al detectar una caída:

1. Consulta SQLite: ¿qué bloques tienen una réplica en el nodo caído?
2. Para cada bloque afectado: encuentra el nodo superviviente, elige un candidato activo
3. Envía `POST /blocks/{id}/replicate` al nodo superviviente para que copie al candidato
4. Actualiza SQLite: reemplaza la referencia al nodo caído por el candidato

Este proceso es **idempotente**: si el monitor corre varias veces mientras el nodo sigue caído, `get_blocks_on_node` ya no retorna los bloques re-replicados (SQLite fue actualizado), evitando duplicados.

### 5.6 Persistencia — SQLite dentro del NameNode

SQLite es solo la capa de persistencia del NameNode. El archivo `.db` se monta como volumen Docker para sobrevivir reinicios del contenedor. La decisión de usar SQLite en lugar de PostgreSQL o Redis fue intencional: el scope académico no requiere concurrencia masiva, y SQLite elimina la dependencia de un proceso externo.

---

## 6. Esquema de base de datos

```sql
CREATE TABLE users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,   -- bcrypt
    created_at    TEXT NOT NULL
);

CREATE TABLE files (
    file_id    TEXT PRIMARY KEY,
    owner      TEXT NOT NULL,      -- username del propietario
    path       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    is_dir     INTEGER NOT NULL DEFAULT 0,  -- 1 para directorios lógicos
    created_at TEXT NOT NULL
);
-- UNIQUE INDEX en (owner, path) garantiza que cada usuario
-- no puede tener dos archivos/dirs con la misma ruta

CREATE TABLE blocks (
    block_id   TEXT NOT NULL,
    file_id    TEXT NOT NULL,
    seq        INTEGER NOT NULL,   -- orden del bloque en el archivo
    datanode   TEXT NOT NULL       -- una fila por réplica
    -- Un mismo block_id aparece 2 veces (factor de replicación = 2)
);

CREATE TABLE datanodes (
    node_id        TEXT PRIMARY KEY,
    host           TEXT NOT NULL,
    port           INTEGER NOT NULL,
    last_heartbeat TEXT NOT NULL,
    free_bytes     INTEGER NOT NULL
);
```

**Aislamiento entre usuarios:** todas las queries de archivos filtran por `owner = <sub del JWT>`. El JWT es firmado con `JWT_SECRET` y no puede ser modificado por el cliente.

---

## 7. Flujos principales

### Flujo PUT (escritura)

```
1. Cliente  → POST /auth/login              → NameNode → JWT token
2. Cliente  → POST /files/upload (path, size) → NameNode → plan de bloques
             NameNode calcula: num_blocks = ceil(size / BLOCK_SIZE)
             Asigna DataNodes por Round-Robin
3. Por cada bloque:
   Cliente  → PUT /blocks/{id}?replica_host=...  → DataNode primario
   DataNode primario → PUT /blocks/{id}            → DataNode réplica
   DataNode réplica  → OK                          → DataNode primario
   DataNode primario → OK                          → Cliente
4. Cliente  → POST /files/{file_id}/confirm  → NameNode
   NameNode escribe en SQLite: 2 filas en blocks por bloque
```

### Flujo GET (lectura)

```
1. Cliente  → GET /files/{path}         → NameNode → metadatos + ubicación de bloques
2. Por cada bloque (orden ascendente de seq):
   Cliente  → GET /blocks/{id}          → DataNode → bytes
3. Cliente concatena bloques en orden → archivo reconstruido
```

### Flujo de re-replicación

```
1. DataNode caído deja de enviar heartbeat
2. Monitor (cada 5s): detecta nodo con last_heartbeat > 15s → estado "down"
3. NameNode consulta SQLite: bloques con única réplica activa
4. Para cada bloque:
   NameNode → POST /blocks/{id}/replicate → DataNode fuente
   DataNode fuente → PUT /blocks/{id}     → DataNode destino
   NameNode actualiza SQLite: reemplaza referencia al nodo caído
```

---

## 8. Endpoints implementados

### NameNode (`:8000`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/auth/register` | Registrar usuario (bcrypt hash) |
| POST | `/auth/login` | Autenticar y emitir JWT |
| POST | `/files/upload` | Planificar bloques + asignar DataNodes |
| POST | `/files/{id}/confirm` | Confirmar subida y persistir en SQLite |
| GET | `/files` | Listar archivos del usuario (`?directory=` opcional) |
| GET | `/files/{path}` | Metadatos + ubicación de bloques |
| DELETE | `/files/{path}` | Eliminar archivo y notificar DataNodes |
| POST | `/dirs/{path}` | Crear directorio lógico |
| DELETE | `/dirs/{path}` | Eliminar directorio vacío |
| POST | `/datanodes/register` | DataNode se registra al arrancar |
| POST | `/datanodes/heartbeat` | DataNode reporta estado cada 5s |
| GET | `/datanodes/status` | Estado del clúster (monitoreo) |

### DataNode (`:8001 / :8002 / :8003`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| PUT | `/blocks/{id}` | Recibir bloque + replicar en pipeline |
| GET | `/blocks/{id}` | Servir bloque al cliente |
| DELETE | `/blocks/{id}` | Borrar bloque (invocado por NameNode en rm) |
| POST | `/blocks/{id}/replicate` | Re-replicación instruccionada por NameNode |

---

## 9. Resultados de pruebas

Todas las pruebas se ejecutaron sobre el clúster corriendo en Docker Compose con `BLOCK_SIZE=3` (para partición visible) y `BLOCK_SIZE=67108864` (producción).

### TSK 029 — put/get end-to-end ✓

Archivo `aaabbbccc` (9 bytes) particionado en 3 bloques con `BLOCK_SIZE=3`.

| seq | Contenido | DataNodes |
|-----|-----------|-----------|
| 0   | `aaa`     | dn1 + dn2 |
| 1   | `bbb`     | dn2 + dn3 |
| 2   | `ccc`     | dn3 + dn1 |

```
diff test.txt test_reconstruido.txt  →  vacío ✓
```

### TSK 030 — Replicación ✓

Cada bloque tiene exactamente 2 réplicas en SQLite y en los volúmenes físicos Docker. Verificado con `COUNT(*) GROUP BY block_id = 2` para todos los bloques.

### TSK 031 — Tolerancia a fallos ✓

```
docker stop pydfs-datanode2-1
# Esperar 15s → NameNode detecta caída
# Re-replicación automática:
#   seq=0: dn1 → dn3  (dn2 tenía la réplica)
#   seq=1: dn3 → dn1  (dn2 era el primario)
# get con dn2 caído → diff vacío ✓
```

### TSK 032 — Comandos CLI ✓

| Comando | Casos válidos | Casos inválidos |
|---------|--------------|-----------------|
| `put` | Subida con 1 y 3 bloques | Archivo local inexistente, ruta duplicada |
| `get` | Descarga y reconstrucción correcta | Ruta inexistente, DataNode caído |
| `ls` | Listar todo, filtrar por directorio | Sin sesión activa |
| `rm` | Eliminar archivo y bloques físicos | Archivo inexistente |
| `mkdir` | Crear directorio anidado | Directorio duplicado |
| `rmdir` | Eliminar directorio vacío | No vacío, inexistente |

Todos los errores retornan `exit code 1` con mensaje descriptivo, sin stack traces.

### TSK 033 — Aislamiento entre usuarios ✓

`testuser` y `user2` no pueden ver ni acceder a los archivos del otro. El sistema retorna 404 (no revela existencia de archivos ajenos). El aislamiento está garantizado por el campo `owner` en SQLite combinado con el JWT firmado.

### ENA 010 — Logs del sistema ✓

Eventos cubiertos por logs:

| Evento | Nivel | Ejemplo |
|--------|-------|---------|
| Arranque NameNode | INFO | `NameNode arrancando — inicializando base de datos` |
| Monitor iniciado | INFO | `heartbeat monitor iniciado (intervalo=5.0s, timeout=15.0s)` |
| Arranque DataNode | INFO | `DataNode dn1 arrancando` |
| DataNode registrado | INFO | `DataNode registrado: dn1 (datanode1:8001, free=2921836544 bytes)` |
| Bloque recibido | INFO | `bloque recibido: ec422ff7-... (3 bytes)` |
| Replicación completada | INFO | `replicación completada: ec422ff7-...` |
| Archivo confirmado | INFO | `archivo confirmado: owner=testuser path=test.txt size=9 bloques=3` |
| DataNode caído detectado | INFO | `DataNode dn2 is down — re-replicating 2 block(s)` |
| Re-replicación exitosa | INFO | `re-replicated block 71f3663a-...: dn1 → dn3` |

---

## 10. Decisiones que cambiaron respecto al diseño inicial

| Decisión | Plan inicial | Implementación real | Razón |
|----------|-------------|--------------------|-|
| BLOCK_SIZE para pruebas | `64` bytes | `3` bytes | 64 bytes es insuficiente para partir `aaabbbccc` (9 bytes) en 3 bloques; se necesita ≤3 |
| Logging en DataNode | No especificado | `logging.basicConfig` en `main.py` + logs en `blocks.py` y `heartbeat.py` | Necesario para depurar replicación y heartbeats |
| Logging en NameNode | Solo en scheduler | Extendido a `main.py`, `files.py` y `datanodes.py` | Trazabilidad completa del ciclo de vida |
| `get_file_blocks` | Solo retornaba `node_id` | Hace JOIN con `datanodes` para incluir `host` y `port` | El CLI necesita la dirección del DataNode para descargar bloques directamente |
| TSK 033 (re-replicación) | Issue separado | Cubierto dentro del mismo commit que TSK 032 | La lógica de detección y re-replicación es inseparable |

---

## 11. Limitaciones conocidas

- **WORM estricto:** no hay soporte para actualización parcial de archivos. Para modificar un archivo hay que borrarlo y subirlo de nuevo.
- **NameNode SPOF:** si el NameNode cae, el sistema no es accesible aunque los datos estén en los DataNodes. En un sistema productivo se usaría un NameNode secundario o un mecanismo de failover.
- **SQLite no es concurrente:** con muchos escritores simultáneos SQLite podría ser un cuello de botella. En producción se usaría PostgreSQL.
- **Seguridad de DataNodes:** los endpoints de los DataNodes no requieren autenticación JWT. En producción, los DataNodes solo deberían ser accesibles desde la red interna.
- **Sin soporte de archivos grandes en streaming:** el CLI carga cada bloque completo en memoria antes de enviarlo (`f.read(block_size)`). Con bloques de 64 MB esto es manejable, pero con bloques más grandes sería necesario streaming.

---

## 12. Conclusiones

PyDFS implementa con éxito los principios fundamentales de un DFS estilo HDFS/GFS:

1. **Separación de metadatos y datos** — el NameNode coordina sin almacenar bytes; los DataNodes almacenan sin conocer el contexto.
2. **Replicación síncrona en pipeline** — garantiza que cada escritura exitosa tiene factor 2 de replicación antes de confirmar al cliente.
3. **Tolerancia a fallos automática** — la caída de un DataNode no interrumpe el servicio; el monitor detecta la caída y restaura el factor de replicación sin intervención manual.
4. **Aislamiento multiusuario** — cada usuario ve solo sus propios archivos gracias a JWT + filtrado por `owner` en SQLite.
5. **Operabilidad** — el clúster completo arranca con un solo comando (`docker compose up --build`) y expone documentación interactiva en `/docs`.

El proyecto demuestra que los conceptos de HDFS (distribución por bloques, heartbeats, re-replicación) son implementables en pocas centenas de líneas de Python cuando se usa un framework moderno como FastAPI y se mantiene el scope bien delimitado.
