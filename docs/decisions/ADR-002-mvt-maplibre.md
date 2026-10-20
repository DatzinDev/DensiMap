# ADR-002: teselas vectoriales de Atlas y estilo en MapLibre

Estado: aceptada · 2026-10-20

## Contexto

Cada giro debe poder verse como puntos, calor, hexágonos o burbujas, con color, opacidad y tamaño
de hexágono que elige el usuario. El WMS de Atlas dibuja en el servidor con un estilo fijo por capa
y sin estilos dependientes de los datos, así que cada cambio de simbología sería una imagen nueva y
hexágonos o burbujas graduadas no serían posibles.

## Decisión

- Atlas (rama `develop`, fijada por commit) publica cuatro capas como MVT: `establishments`,
  `hexagons`, `hexagon_centers` y `municipalities`. Los giros no son tablas: cada capa del mapa es
  un filtro `ATLAS_FILTER` por `category` (y `size_m` en hexágonos y burbujas).
- Los hexágonos se calculan en el ETL con `ST_HexagonGrid` en EPSG:6368, en cuatro tamaños de lado
  (250 m, 500 m, 1 km, 2 km). Cada punto cuenta una sola vez y la densidad es conteo / área.
- MapLibre GL dibuja en el navegador: `circle`, `heatmap`, `fill` con cortes por cuantiles y
  `circle` con radio proporcional a la raíz del conteo.

## Consecuencias

- Cambiar simbología o color no toca el servidor; las teselas se reutilizan desde la caché HTTP.
- El presupuesto de Atlas es 100 mil elementos por tesela, sin truncar: el giro más grande de la
  ZMG (restaurantes, ~24 mil) cabe completo incluso a zoom metropolitano.
- La dependencia de Atlas apunta a un commit de `develop` hasta que el MVT se publique en PyPI.
