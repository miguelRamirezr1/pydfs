# PyDFS — Sistema de Archivos Distribuido

DFS minimalista inspirado en HDFS/GFS. Almacena archivos dividiéndolos en bloques y distribuyéndolos entre múltiples DataNodes. Un NameNode central coordina los metadatos y la autenticación.

## Requisitos

- Docker >= 24
- Docker Compose >= 2.20

## Arranque

### 1. Clonar el repositorio

```bash
git clone https://github.com/miguelRamirezr1/pydfs.git
cd pydfs
```

### 2. Construir las imágenes y levantar el clúster

```bash
docker-compose up --build
```

Esto construye las imágenes de `namenode`, `datanode` y `client`, y levanta los contenedores en la red `dfs-network`. Al arrancar, el NameNode inicializa automáticamente el esquema SQLite con las tablas `users`, `files`, `blocks` y `datanodes`.

## Configuración

Las variables de entorno se definen en `docker-compose.yml`:

| Variable | Servicio | Default | Descripción |
|---|---|---|---|
| `BLOCK_SIZE` | namenode | `67108864` | Tamaño de bloque en bytes (64 MB). Usar `64` para pruebas con archivos pequeños |
| `REPLICATION_FACTOR` | namenode | `2` | Copias por bloque |
| `HEARTBEAT_TIMEOUT` | namenode | `15` | Segundos para declarar un DataNode caído |
| `HEARTBEAT_INTERVAL` | datanodes | `5` | Segundos entre heartbeats |
| `JWT_SECRET` | todos | `changeme` | Clave de firma JWT. Cambiar en producción |

## Detener el clúster

```bash
docker-compose down
```
