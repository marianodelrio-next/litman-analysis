# Docker opcional

Docker ejecuta la misma CLI instalada en la imagen. Desde la raíz:

```sh
docker compose -f deployment/docker/compose.yaml build
docker compose -f deployment/docker/compose.yaml run --rm litman-core assess /input --output /output
```

Los mounts proporcionan `/input`, `/output`, `/data/runs` y `/job`; los jobs deben usar esas rutas internas. Las credenciales se proporcionan explícitamente mediante los mounts y variables de Compose.
