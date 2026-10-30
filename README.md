# Juego-del-siglo

Reglas del juego (como está programado)

Material: 90 fichas numeradas del 1 al 90, sin repetir. Cada ficha vale su número.

Objetivo: acercarte lo más posible a 100 puntos sin pasarte.

Cómo se juega:

Al empezar la ronda, cada jugador recibe una ficha inicial, la vira, que es su primera ficha. En el juego se marca con un anillo dorado.
En tu turno decides:
BOLA: sacas otra ficha del mazo y su número se suma a tu puntaje.
ME QUEDO: te plantas con lo que tienes y ya no sacas más en esa ronda.
Mientras estés por debajo de 99 conservas el turno y puedes seguir sacando bolas.
Tu turno termina en estos casos:
SIGLO: llegas a exactamente 99 o 100.
ME FUI: te pasas de 100 y quedas eliminado de la ronda.
ME QUEDO: te plantas voluntariamente.

Quién gana la ronda:

Gana quien tenga el puntaje más alto sin pasarse de 100. Un 100 le gana a un 99.
Si dos o más empatan en el puntaje más alto, todos ganan la ronda.
Si todos se pasan de 100, nadie gana.

En multijugador, además: cada decisión tiene 30 segundos, y si se acaba el tiempo el servidor te planta (ME QUEDO). La salida rota entre rondas y se cuentan las victorias de cada jugador.

## Cuentas e historial

Desde el navegador, el escritorio (`cliente.py`) y el 3D (`cliente_3d.py`) puedes crear una cuenta o iniciar sesión. El panel de estado muestra las rondas terminadas, el puntaje, el estado del jugador, el resultado, los oponentes y el total de victorias y derrotas. También se puede jugar como invitado, pero esas partidas no se asocian a una cuenta.

El servidor web crea la base SQLite en `siglo_game/data/siglo.db`. Para usar otra ubicación (por ejemplo, un volumen persistente en un hosting), define `SIGLO_DATABASE` con la ruta del archivo antes de iniciar `servidor.py`. Las contraseñas se guardan con PBKDF2-HMAC-SHA256 y las sesiones web usan una cookie HTTP-only.


## Novedades de la versión fusionada

- Fichas de lotería (madera, aro rojo, número rojo) en escritorio, web y 3D.
- **Vista 3D en el navegador** (botón VISTA 3D / 2D) y cliente 3D de escritorio con Ursina (`pip install ursina`, `python cliente_3d.py`).
- Login/registro también en el cliente de escritorio y 3D; con `DATABASE_URL` las cuentas van a PostgreSQL (si no, SQLite).
- Con 3 o más jugadores, quien juega pide la bola (PEDIR BOLA) y el anfitrión la reparte.


## Guardar las cuentas en Render (importante)

En Render el disco del contenedor **se borra en cada reinicio o redespliegue**. Si el servidor corre sin
`DATABASE_URL`, las cuentas se guardan en un archivo SQLite y se pierden. Para que se conserven:

**Opción A (automática):** en Render elige *New → Blueprint* y apunta a este repositorio. El archivo
`render.yaml` crea el servicio web y una base PostgreSQL (`siglo-db`) y ya los conecta.

**Opción B (manual):** *New → PostgreSQL*, copia la *Internal Database URL*, y en el servicio web ve a
*Environment* y crea la variable `DATABASE_URL` con ese valor. Redespliega.

Las tablas se crean solas. Para comprobarlo abre `https://TU-APP.onrender.com/health`: debe decir
`"cuentas": "postgresql"` y `"cuentas_persistentes": true`. Si dice `sqlite`, falta `DATABASE_URL`.
(El plan gratis de PostgreSQL de Render caduca a los 30 días: pasado ese plazo hay que crear otra base o pasar a un plan de pago.)
