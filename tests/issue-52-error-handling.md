# Guía de pruebas — Issue #52 ENA 009: manejo de errores en CLI

Cubre todos los escenarios de error del CLI: token expirado, DataNode
no disponible, archivo no encontrado y errores de entrada inválida.
Todos los errores se presentan como mensajes claros con exit code 1.

---

## 1. Comandos Docker

### Levantar el clúster
```bash
docker compose up --build -d
```

### Ver logs (útil para correlacionar errores cliente-servidor)
```bash
docker compose logs -f namenode
docker compose logs -f datanode1
```

### Detener un DataNode específico (para simular caída)
```bash
docker stop pydfs-datanode1-1
docker stop pydfs-datanode2-1
docker stop pydfs-datanode3-1
```

### Reiniciar DataNode
```bash
docker start pydfs-datanode1-1
```

### Ver estado de los contenedores
```bash
docker compose ps
```

### Detener todos
```bash
docker compose down
```

---

## 2. Preparación del entorno

### 2.1 Obtener token válido
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$TOKEN" > ~/.dfs_token
```

### 2.2 Subir archivo de prueba
```bash
printf "aaabbbccc" > /tmp/test.txt
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt
```

---

## 3. Error: sin sesión activa (archivo ~/.dfs_token inexistente)

### CLI
```bash
rm -f ~/.dfs_token

NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
# Error: No hay sesión activa. Ejecuta: python cli.py login
# exit code: 1

NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt
# Error: No hay sesión activa. Ejecuta: python cli.py login
```

### HTTP equivalente
```bash
curl -s http://localhost:8000/files
# Respuesta: {"detail": "Not authenticated"} con HTTP 401
```

### Swagger
1. No hacer clic en Authorize (o borrar el token)
2. Ejecutar cualquier endpoint protegido
3. Respuesta: 401 Unauthorized

---

## 4. Error: token inválido o expirado

### CLI
```bash
echo "token.falso.invalido" > ~/.dfs_token

NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
# Error: Sesión expirada o inválida. Ejecuta: python cli.py login
# exit code: 1
```

### HTTP equivalente
```bash
curl -s http://localhost:8000/files \
  -H "Authorization: Bearer token.falso.invalido" | python3 -m json.tool
# {"detail": "Token inválido"} con HTTP 401
```

### Postman
- **Headers:** `Authorization: Bearer token.falso.invalido`
- Ejecutar cualquier endpoint protegido → 401 Unauthorized

---

## 5. Error: archivo local no encontrado (put)

### CLI
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/no_existe.txt
# Error: Archivo local no encontrado: /tmp/no_existe.txt
# exit code: 1
```

**Nota:** Este error ocurre antes de cualquier llamada HTTP — es validación local.

---

## 6. Error: archivo remoto no encontrado (get / rm)

### CLI — get
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py get archivo_inexistente.txt
# Error: Archivo no encontrado
# exit code: 1
```

### CLI — rm
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rm archivo_inexistente.txt
# Error: Archivo no encontrado
# exit code: 1
```

### HTTP equivalente
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s http://localhost:8000/files/archivo_inexistente.txt \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {"detail": "Archivo no encontrado"} con HTTP 404

curl -s -X DELETE http://localhost:8000/files/archivo_inexistente.txt \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {"detail": "Archivo no encontrado"} con HTTP 404
```

---

## 7. Error: ruta remota ya existe (put duplicado)

### CLI
```bash
# test.txt ya fue subido en la preparación
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt
# Error: Ya existe un archivo en esa ruta
# exit code: 1
```

### HTTP equivalente
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "test.txt", "size": 9}' | python3 -m json.tool
# {"detail": "Ya existe un archivo en esa ruta"} con HTTP 409
```

---

## 8. Error: DataNode no disponible al subir (put)

### Simular caída de todos los DataNodes excepto uno
```bash
docker stop pydfs-datanode2-1
docker stop pydfs-datanode3-1
# Solo queda dn1 activo — insuficiente para replicar (necesita 2)

sleep 16  # Esperar que el NameNode declare dn2 y dn3 como down

NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt --remote-path nuevo.txt
# Error: Se necesitan al menos 2 DataNodes activos
# exit code: 1
```

### Simular fallo durante la transferencia de un bloque
```bash
# Restaurar los DataNodes
docker start pydfs-datanode2-1
docker start pydfs-datanode3-1
sleep 10

# Detener un DataNode justo durante el put
docker stop pydfs-datanode1-1 &
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/test.txt --remote-path nuevo2.txt
# Es posible ver: Error: DataNode no disponible al subir bloque 0: ...
```

### HTTP equivalente
```bash
TOKEN=$(cat ~/.dfs_token)

# Verificar cuántos DataNodes están activos
curl -s http://localhost:8000/datanodes/status | python3 -c "
import sys, json
nodes = json.load(sys.stdin)
active = [n for n in nodes if n['status'] == 'active']
print(f'Activos: {len(active)} / {len(nodes)}')
"
```

### Restaurar
```bash
docker start pydfs-datanode1-1
docker start pydfs-datanode2-1
docker start pydfs-datanode3-1
```

---

## 9. Error: DataNode no disponible al descargar (get)

```bash
# Detener todos los DataNodes
docker stop pydfs-datanode1-1
docker stop pydfs-datanode2-1
docker stop pydfs-datanode3-1

sleep 2

NAMENODE_URL=http://localhost:8000 python3 client/cli.py get test.txt
# Error: DataNode no disponible al descargar bloque 0: ...
# exit code: 1

# Restaurar
docker start pydfs-datanode1-1
docker start pydfs-datanode2-1
docker start pydfs-datanode3-1
```

---

## 10. Error: directorio ya existe (mkdir)

### CLI
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir docs
# Error: El directorio ya existe
# exit code: 1
```

### HTTP equivalente
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X POST http://localhost:8000/dirs/docs \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {"detail": "El directorio ya existe"} con HTTP 409
```

---

## 11. Error: directorio no vacío (rmdir)

### CLI
```bash
# Crear directorio y subir archivo dentro
NAMENODE_URL=http://localhost:8000 python3 client/cli.py mkdir proyectos
printf "x" > /tmp/x.txt
NAMENODE_URL=http://localhost:8000 python3 client/cli.py put /tmp/x.txt --remote-path proyectos/x.txt

# Intentar borrar directorio no vacío
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rmdir proyectos
# Error: El directorio no está vacío
# exit code: 1
```

### HTTP equivalente
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X DELETE http://localhost:8000/dirs/proyectos \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {"detail": "El directorio no está vacío"} con HTTP 409
```

---

## 12. Error: directorio no encontrado (rmdir)

### CLI
```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py rmdir inexistente
# Error: Directorio no encontrado
# exit code: 1
```

### HTTP equivalente
```bash
TOKEN=$(cat ~/.dfs_token)

curl -s -X DELETE http://localhost:8000/dirs/inexistente \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {"detail": "Directorio no encontrado"} con HTTP 404
```

---

## 13. Resumen de todos los errores

| Comando | Situación | Mensaje CLI | HTTP Status | Exit code |
|---------|-----------|------------|-------------|-----------|
| cualquiera | Sin `~/.dfs_token` | `No hay sesión activa. Ejecuta: python cli.py login` | 401 | 1 |
| cualquiera | Token inválido/expirado | `Sesión expirada o inválida. Ejecuta: python cli.py login` | 401 | 1 |
| `put` | Archivo local no existe | `Archivo local no encontrado: /ruta` | — | 1 |
| `put` | Ruta remota ya existe | `Ya existe un archivo en esa ruta` | 409 | 1 |
| `put` | Menos de 2 DataNodes activos | `Se necesitan al menos 2 DataNodes activos` | 503 | 1 |
| `put` | DataNode cae durante transferencia | `DataNode no disponible al subir bloque N: ...` | — | 1 |
| `get` | Archivo no existe en DFS | `Archivo no encontrado` | 404 | 1 |
| `get` | DataNode no disponible | `DataNode no disponible al descargar bloque N: ...` | — | 1 |
| `rm` | Archivo no existe | `Archivo no encontrado` | 404 | 1 |
| `mkdir` | Directorio ya existe | `El directorio ya existe` | 409 | 1 |
| `rmdir` | Directorio no vacío | `El directorio no está vacío` | 409 | 1 |
| `rmdir` | Directorio no existe | `Directorio no encontrado` | 404 | 1 |

---

## 14. Verificar exit codes en shell

```bash
NAMENODE_URL=http://localhost:8000 python3 client/cli.py get no_existe.txt
echo "Exit code: $?"
# Exit code: 1

NAMENODE_URL=http://localhost:8000 python3 client/cli.py ls
echo "Exit code: $?"
# Exit code: 0 (éxito)
```
