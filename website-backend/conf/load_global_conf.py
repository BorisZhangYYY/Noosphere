from __future__ import annotations

import os
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, Mapping, Optional


def read_global_conf(path: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """Read key-value settings from global.conf.

    This function loads an INI-style configuration file with sections such as
    [flask] and [postgres], and returns a nested dictionary. If the file is
    missing, an empty dictionary is returned. In this project, values from
    global.conf take precedence over process environment variables; if a key
    is absent in global.conf, fall back to environment variables, then to
    built-in defaults.

    Args:
        path: Optional absolute or relative path to the config file. If None,
            the function looks for a file named 'global.conf' in the same
            directory as this module.

    Returns:
        A nested dictionary mapping section names to dictionaries of string keys
        and values.
    """
    cfg_path = Path(path) if path else Path(__file__).resolve().parent / "global.conf"
    if not cfg_path.exists():
        return {}
    parser = ConfigParser()
    parser.read(cfg_path)
    result: Dict[str, Dict[str, str]] = {}
    for section in parser.sections():
        result[section] = {k: v for k, v in parser.items(section)}
    return result


_GLOBAL_CONF: Mapping[str, Mapping[str, str]] = read_global_conf()


def get_conf_str(section: str, key: str, env_key: str, default: str) -> str:
    """Read a string setting using the project precedence rules."""
    sec = _GLOBAL_CONF.get(section, {})
    val = sec.get(key)
    if val is not None:
        return str(val)
    env_val = os.getenv(env_key)
    if env_val is not None:
        return env_val
    return default


def get_conf_int(section: str, key: str, env_key: str, default: int) -> int:
    """Read an integer setting using the project precedence rules."""
    sec = _GLOBAL_CONF.get(section, {})
    sec_val = sec.get(key)
    if sec_val is not None:
        try:
            return int(sec_val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
    env_val = os.getenv(env_key)
    if env_val is not None:
        try:
            return int(env_val)
        except ValueError:
            return default
    return default


def get_conf_bool(section: str, key: str, env_key: str, default: bool) -> bool:
    """Read a boolean setting using the project precedence rules."""
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}
    sec_val = _GLOBAL_CONF.get(section, {}).get(key)
    if sec_val is not None:
        val = str(sec_val).strip().lower()
        if val in truthy:
            return True
        if val in falsy:
            return False
    env_val = os.getenv(env_key)
    if env_val is not None:
        val = env_val.strip().lower()
        if val in truthy:
            return True
        if val in falsy:
            return False
    return default

def build_postgres_dsn(user: str, password: str, host: str, port: int, db: str) -> str:
    """Build a PostgreSQL DSN string.

    Args:
        user: Database username.
        password: Database password, may be empty.
        host: Database host.
        port: Database port.
        db: Database name.

    Returns:
        A DSN string in the form of postgresql://user[:password]@host:port/db
    """
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"