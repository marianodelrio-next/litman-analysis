# Instalación local de una wheel

Esta guía consume una distribución construida de `litman-core`, sin ejecutar
el código desde un checkout. Requiere Python 3.11, `uv` y autenticación de
Codex configurada por el usuario.

Construye u obtén una wheel como paso de empaquetado/release:

```sh
uv build --wheel --out-dir ./dist
```

En el directorio donde conservarás la instalación, crea un entorno e instala
la wheel concreta:

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /ruta/a/litman_core-0.1.0-py3-none-any.whl
```

El único comando público de ejecución es:

```sh
.venv/bin/litman-core run
.venv/bin/litman-core run --config /ruta/a/config.toml
```

Las rutas relativas del TOML se resuelven respecto al propio archivo. El
workspace temporal de LitMan usa `/tmp/litman-core` por defecto y se elimina al
terminar la ejecución. Configura la autenticación de Codex según tu entorno;
esta guía no crea credenciales ni instaladores.
