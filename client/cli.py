import getpass
import os
from pathlib import Path

import click
import httpx

NAMENODE_URL = os.getenv("NAMENODE_URL", "http://localhost:8000")
TOKEN_FILE = Path.home() / ".dfs_token"


def _load_token() -> str:
    if not TOKEN_FILE.exists():
        raise click.ClickException("No hay sesión activa. Ejecuta: python cli.py login")
    return TOKEN_FILE.read_text().strip()


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

    token = resp.json()["access_token"]
    TOKEN_FILE.write_text(token)
    click.echo(f"Sesión iniciada como '{username}'.")


if __name__ == "__main__":
    cli()
