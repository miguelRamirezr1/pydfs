import getpass
import os
from pathlib import Path
from urllib.parse import urlparse

import click
import httpx

NAMENODE_URL = os.getenv("NAMENODE_URL", "http://localhost:8000")
TOKEN_FILE = Path.home() / ".dfs_token"


def _load_token() -> str:
    if not TOKEN_FILE.exists():
        raise click.ClickException("No hay sesión activa. Ejecuta: python cli.py login")
    return TOKEN_FILE.read_text().strip()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _check_response(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        raise click.ClickException("Sesión expirada o inválida. Ejecuta: python cli.py login")
    if resp.status_code not in (200, 201, 204):
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise click.ClickException(detail)


def _parse_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname, parsed.port


@click.group()
def cli():
    pass


@cli.command()
def login():
    """Autenticarse en el DFS y guardar el token JWT."""
    username = input("Usuario: ")
    password = getpass.getpass("Contraseña: ")

    try:
        resp = httpx.post(
            f"{NAMENODE_URL}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise click.ClickException(f"Login fallido: {exc.response.json().get('detail', exc)}")
    except Exception as exc:
        raise click.ClickException(f"Error de conexión: {exc}")

    TOKEN_FILE.write_text(resp.json()["access_token"])
    click.echo(f"Sesión iniciada como '{username}'.")


@cli.command()
@click.argument("local_path")
@click.option("--remote-path", "-r", default=None, help="Ruta destino en el DFS")
def put(local_path, remote_path):
    """Subir un archivo al DFS."""
    token = _load_token()
    local = Path(local_path)
    if not local.exists():
        raise click.ClickException(f"Archivo local no encontrado: {local_path}")

    remote = remote_path or local.name
    size = local.stat().st_size

    resp = httpx.post(
        f"{NAMENODE_URL}/files/upload",
        json={"path": remote, "size": size},
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    plan = resp.json()
    file_id = plan["file_id"]
    block_size = plan["block_size"]

    confirmed_blocks = []
    with open(local_path, "rb") as f:
        for block_info in plan["blocks"]:
            chunk = f.read(block_size)
            replica_host, replica_port = _parse_url(block_info["replica_url"])
            url = f"{block_info['primary_url']}/blocks/{block_info['block_id']}"

            try:
                resp = httpx.put(
                    url,
                    content=chunk,
                    params={"replica_host": replica_host, "replica_port": replica_port},
                    timeout=60,
                )
                _check_response(resp)
            except click.ClickException:
                raise
            except Exception as exc:
                raise click.ClickException(f"DataNode no disponible al subir bloque {block_info['seq']}: {exc}")

            confirmed_blocks.append({
                "block_id": block_info["block_id"],
                "seq": block_info["seq"],
                "primary_node_id": block_info["primary_node_id"],
                "replica_node_id": block_info["replica_node_id"],
            })

    resp = httpx.post(
        f"{NAMENODE_URL}/files/{file_id}/confirm",
        json={"path": remote, "size": size, "blocks": confirmed_blocks},
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    click.echo(f"Subido: {remote} ({size} bytes, {len(confirmed_blocks)} bloque(s))")


@cli.command()
@click.argument("remote_path")
@click.option("--output", "-o", default=None, help="Ruta local de salida")
def get(remote_path, output):
    """Descargar un archivo del DFS."""
    token = _load_token()

    resp = httpx.get(
        f"{NAMENODE_URL}/files/{remote_path}",
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    meta = resp.json()

    seen = {}
    for b in meta["blocks"]:
        key = (b["block_id"], b["seq"])
        if key not in seen:
            seen[key] = b
    ordered = sorted(seen.values(), key=lambda x: x["seq"])

    output_path = Path(output or Path(remote_path).name)
    with open(output_path, "wb") as out:
        for b in ordered:
            url = f"http://{b['host']}:{b['port']}/blocks/{b['block_id']}"
            try:
                resp = httpx.get(url, timeout=60)
                _check_response(resp)
            except click.ClickException:
                raise
            except Exception as exc:
                raise click.ClickException(f"DataNode no disponible al descargar bloque {b['seq']}: {exc}")
            out.write(resp.content)

    click.echo(f"Descargado: {output_path}")


@cli.command()
@click.option("--path", "-p", default=None, help="Filtrar por directorio")
def ls(path):
    """Listar archivos y directorios."""
    token = _load_token()
    params = {"directory": path} if path else {}

    resp = httpx.get(
        f"{NAMENODE_URL}/files",
        params=params,
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    files = resp.json()

    if not files:
        click.echo("(vacío)")
        return

    for f in files:
        tipo = "DIR " if f.get("is_dir") else "FILE"
        click.echo(f"{tipo}  {f['path']}  {f['size']} bytes  {f['created_at']}")


@cli.command()
@click.argument("remote_path")
def rm(remote_path):
    """Eliminar un archivo del DFS."""
    token = _load_token()

    resp = httpx.delete(
        f"{NAMENODE_URL}/files/{remote_path}",
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    click.echo(f"Eliminado: {remote_path}")


@cli.command()
@click.argument("path")
def mkdir(path):
    """Crear un directorio en el DFS."""
    token = _load_token()

    resp = httpx.post(
        f"{NAMENODE_URL}/dirs/{path}",
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    click.echo(f"Directorio creado: {path}")


@cli.command()
@click.argument("path")
def rmdir(path):
    """Eliminar un directorio vacío del DFS."""
    token = _load_token()

    resp = httpx.delete(
        f"{NAMENODE_URL}/dirs/{path}",
        headers=_auth_headers(token),
        timeout=10,
    )
    _check_response(resp)
    click.echo(f"Directorio eliminado: {path}")


if __name__ == "__main__":
    cli()
