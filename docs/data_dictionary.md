# Diccionario de datos

Esquema creado por Flyway en `db/migrations/`. Geometrías: puntos en EPSG:4326 (como las entrega el
DENUE); municipios y hexágonos en EPSG:6368 (UTM 13N, métrico). Atlas reproyecta al servir.

## `analytics.establishments`

Un registro por unidad económica del DENUE en la ZMG que cae en algún giro configurado.

| Campo | Origen DENUE | Notas |
|---|---|---|
| `denue_id` | `id` | Llave primaria. |
| `category` | — | Giro de `config/densimap.yaml` según `codigo_act`. |
| `scian_code`, `activity` | `codigo_act`, `nombre_act` | Clase SCIAN y su nombre oficial. |
| `name`, `legal_name` | `nom_estab`, `raz_social` | Pueden faltar; no se inventan. |
| `staff` | `per_ocu` | Estrato de personal ocupado (texto de INEGI). |
| `municipality_code`, `municipality` | `cve_mun`, `municipio` | Oficiales, no inferidos. |
| `settlement`, `postal_code` | `nomb_asent`, `cod_postal` | Colonia y código postal. |
| `opened` | `fecha_alta` | `YYYY-MM` → primer día del mes; si no tiene ese formato queda nulo. |
| `geometry` | `longitud`, `latitud` | Punto 4326. |
| `run_id` | — | Última corrida que insertó o cambió el registro. |

## `analytics.hexagons` y `analytics.hexagon_centers`

Recalculadas en cada carga. Solo existen celdas con al menos un establecimiento.

| Campo | Notas |
|---|---|
| `category` | Giro. |
| `size_m` | Lado del hexágono en metros: 250, 500, 1000 o 2000. |
| `count` | Establecimientos del giro dentro de la celda; cada punto cuenta una vez. |
| `density_km2` | `count` / área de la celda en km². |
| `geometry` | Hexágono (o su centroide en `hexagon_centers`), EPSG:6368. |

## `analytics.municipalities`

Los nueve municipios de la ZMG con `code` (clave INEGI de 3 dígitos), `name`, `area_km2` (IIEG) y
su polígono.

## `staging.rejected_records` y `meta.pipeline_runs`

- Rechazos de cada corrida con `reason` y el registro crudo en `raw`: `invalid_id`, `duplicate_id`,
  `invalid_coordinates` y `outside_study_area` (coordenadas fuera de los polígonos de la ZMG
  aunque la clave municipal sea de la ZMG).
- Cada corrida guarda archivo, SHA-256, edición del DENUE, estado (`started`, `completed`,
  `failed`) y conteos de aceptados, rechazados, insertados, actualizados y retirados.

## Límites conocidos

- El DENUE refleja unidades activas según INEGI; los negocios informales o recientes pueden faltar.
- La densidad municipal usa el área total del municipio, que incluye suelo no urbano: compara
  municipios con cautela y usa los hexágonos para la densidad local.
- Las fronteras de clases SCIAN agrupan giros distintos (722515 incluye neverías y refresquerías).
