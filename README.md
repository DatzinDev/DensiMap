# DensiMap

Mapa de densidad de giros comerciales en la Zona Metropolitana de Guadalajara (ZMG), un producto
de Datzin. Toma las unidades económicas del DENUE de INEGI, las agrupa por giro y deja ver cada
giro como capa con la simbología que elija el usuario: puntos, mapa de calor, hexágonos de densidad
o burbujas proporcionales.

```text
DENUE (descarga masiva) → extracción con snapshot → selección ZMG + SCIAN → PostGIS
  → Atlas (teselas vectoriales MVT) → MapLibre GL (estilo en el navegador)
```

## Giros iniciales

| Grupo | Capa | Clases SCIAN |
|---|---|---|
| Comida | Cafeterías | 722515 |
| Comida | Restaurantes | 7225xx salvo 722515 |
| Comida | Panaderías | 311812 |
| Comida | Tortillerías | 311830 |
| Comercio de barrio | Farmacias | 464111, 464112 |
| Comercio de barrio | Tiendas de abarrotes | 461110 |
| Servicios personales | Salones de belleza | 812110 |
| Servicios personales | Gimnasios | 713943, 713944 |
| Ocio nocturno | Bares y cantinas | 722412 |

Agregar un giro es editar `config/densimap.yaml` y volver a correr el ETL; la configuración
rechaza giros que se traslapen. La ZMG son los nueve municipios del archivo, con claves verificadas
contra el propio DENUE.

## Levantar el proyecto

Requisitos: Docker con Compose. Para desarrollo local, además `uv` y Python 3.13.

```bash
docker compose up -d --wait db
docker compose --profile migrate run --rm flyway      # esquema con Flyway
docker compose --profile etl run --rm etl             # descarga el DENUE (~40 MB) y carga
docker compose up -d --build --wait web               # http://localhost:8089
```

Para recargar un snapshot ya descargado sin volver a bajarlo:

```bash
docker compose --profile etl run --rm etl python -m densimap --offline data/raw/<carpeta>/denue_14_csv.zip
```

El ETL escribe los snapshots con el UID/GID 1000; si tu usuario es otro, define `DENSIMAP_UID` y
`DENSIMAP_GID`. Cada carga corre en una sola transacción: inserta los nuevos, actualiza los que
cambiaron, retira los que ya no aparecen en el DENUE y recalcula los hexágonos. Repetirla con el
mismo archivo no cambia nada. Una carga sin establecimientos aceptados se rechaza y queda
registrada como `failed`.

## Desarrollo

```bash
uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run pytest                                          # unitarias; las de integración se omiten

docker compose --profile test up -d --wait test-db
docker compose --profile test run --rm test-flyway
export DENSIMAP_TEST_DATABASE_URL=postgresql://densimap:densimap_test@127.0.0.1:$(docker compose port test-db 5432 | cut -d: -f2)/densimap_test
uv run pytest                                          # todo, contra la base desechable
```

`test-db` es una base sin volumen; nunca apuntes las pruebas a `db`.

## Qué publica la app

- `GET /` el mapa.
- `GET /densimap/categories` catálogo, totales por municipio, cortes por cuantiles de densidad y
  máximos por tamaño de hexágono; con eso el mapa arma leyendas y explicaciones.
- `GET /atlas/tiles/{capa}/{z}/{x}/{y}.mvt` teselas de Atlas para `establishments`, `hexagons`,
  `hexagon_centers` y `municipalities`, filtrables con `ATLAS_FILTER` (por ejemplo por `category` y
  `size_m`). La app añade `Cache-Control: public, max-age` (`TILE_MAX_AGE`, 3600 s por defecto).
- `GET /atlas/layers/establishments/download?format=geojson|csv&ATLAS_FILTER=…` descargas filtradas por giro.
- `GET /atlas/wfs` consulta de registros (la ficha de cada punto) y `GET /docs` la API completa.

## Documentación

- [Diccionario de datos](docs/data_dictionary.md)
- [ADR-001: descarga masiva del DENUE](docs/decisions/ADR-001-denue-masivo.md)
- [ADR-002: teselas vectoriales de Atlas y MapLibre](docs/decisions/ADR-002-mvt-maplibre.md)

## Fuentes y atribución

- INEGI, Directorio Estadístico Nacional de Unidades Económicas (DENUE), bajo los Términos de Libre
  Uso de la Información del INEGI. La edición cargada aparece en el encabezado del mapa.
- Límites municipales: IIEG Jalisco (decreto del Congreso del Estado, 2012), extracto de los nueve
  municipios en `data/reference/`.
- Mapas base: Esri, OpenStreetMap.

Basado en el flujo de [zmg-cafe-etl](https://github.com/hectmor/zmg-cafe-etl) y en Atlas de Datzin.
