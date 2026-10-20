# ADR-001: descarga masiva del DENUE como fuente

Estado: aceptada · 2026-10-20

## Contexto

zmg-cafe-etl consulta la API `BuscarAreaAct` del DENUE: una petición por municipio, clase SCIAN y
página, con un token personal. DensiMap empieza con nueve giros y crecerá; con la API cada giro
nuevo multiplica las peticiones y obliga a manejar el token como secreto.

## Decisión

Usar la descarga masiva por entidad, `denue_14_csv.zip` (Jalisco, ~40 MB comprimido, ~400 mil
registros, ISO-8859-1). El ETL guarda el zip completo como snapshot fechado en `data/raw/` con su
SHA-256 y la edición (`05_2026`) leída del archivo de metadatos, y filtra localmente por clave
municipal y prefijo SCIAN.

## Consecuencias

- Sin token ni secretos; la corrida es reproducible desde el snapshot (`--offline`).
- Agregar un giro no requiere volver a descargar: basta con recargar el mismo snapshot.
- La frescura depende de la publicación de INEGI (ediciones semestrales), no de la consulta.
- Se lee la entidad completa aunque solo interese la ZMG; toma unos segundos.
