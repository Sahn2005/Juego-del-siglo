# Siglo - Juego Tradicional Colombiano

**Siglo** es un videojuego digital de escritorio basado en el juego tradicional de la región Caribe colombiana. Está desarrollado en Python utilizando Pygame, con soporte para 1-6 jugadores (incluyendo jugadores controlados por la computadora).

## Objetivo del juego
El objetivo principal es acercarse a 99 o 100 puntos extrayendo fichas numeradas del 1 al 90 de una urna. Si el jugador suma 99 o 100, consigue "Siglo". Si supera los 100 puntos, "se va" y pierde esa ronda. El jugador que consigue "Siglo" o el que más se acerque a 100 sin pasarse gana la ronda.

## Requisitos
- Python 3.8+
- [Pygame](https://www.pygame.org/news)

## Instalación
1. Crear un entorno virtual (opcional pero recomendado):
   ```bash
   python -m venv venv
   ```
2. Activar el entorno virtual (Windows):
   ```bash
   venv\Scripts\activate
   ```
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Ejecución
```bash
python main.py
```

## Multijugador (en línea)
Hasta 6 personas pueden jugar en la misma mesa. Un servidor arbitra la partida (nadie puede hacer trampa desde su cliente) y cada jugador se conecta con su propia ventana.

**1. Quien hospeda** abre el servidor (desde la carpeta raíz del proyecto):
```bash
python servidor.py
```
Muestra su IP en la red local. Opciones: `--puerto 6000`, `--tiempo-turno 45`. El servidor no necesita pygame.

**2. Cada jugador** abre el juego y pulsa **MULTIJUGADOR** (o ejecuta `python cliente.py`), escribe la IP del servidor y su nombre.
- El anfitrión (el primero en entrar) pulsa **INICIAR PARTIDA** cuando haya al menos 2 jugadores.
- **Con 2 jugadores** (el clásico 1 vs 1) cada quien pide su propia ficha en su turno con el botón **BOLA**, como siempre.
- **Con 3 jugadores o más**, el anfitrión pasa a ser también el **repartidor**: en vez de que cada quien pida su ficha, el anfitrión pulsa **REPARTIR** para dársela a quien tenga el turno. En ambos casos, cada jugador conserva su propio botón **ME QUEDO** para plantarse en su turno.
- Mientras la ronda está en curso, **no ves el puntaje ni las fichas de los demás** (solo si están "Jugando" o "Me quedo"); se revelan si alguien se pasa de 100 (Me fui) o al terminar la ronda, para todos. Esto evita hacer trampa mirando la pantalla de otro.
- Cada turno tienes 30 s para decidir; si se acaba el tiempo, el servidor te planta (ME QUEDO).
- Al terminar la ronda el anfitrión pulsa **NUEVA RONDA**. La salida rota entre rondas y se cuentan las victorias.
- Si alguien se desconecta en plena ronda, queda plantado con lo que tenga. No se puede entrar a una ronda ya empezada.

**Jugar por Internet:** el servidor debe ser accesible desde fuera (redirigir el puerto 5555 TCP en el router hacia tu equipo, o correrlo en un VPS). En Windows, la primera vez el firewall pedirá permitir Python: acepta para redes privadas.

Un servidor = una mesa. No hay contraseña, así que no lo dejes abierto a Internet más tiempo del necesario.

## Jugar desde el navegador (web) y subirlo a un servidor
El mismo servidor sirve la página del juego y el WebSocket: **quien entre al enlace, juega**, desde PC o celular, sin instalar nada. Un jugador del navegador y otro con `cliente.py` pueden compartir la misma mesa.

```bash
pip install -r siglo_game/requirements-server.txt   # o requirements.txt (incluye pygame)
python servidor.py                # navegador en :8080 + escritorio (TCP) en :5555
python servidor.py --sin-tcp      # solo navegador (lo normal en un hosting)
```
Abre `http://IP-DEL-SERVIDOR:8080`, escribe tu nombre y listo. Los amigos usan el mismo enlace. La página se adapta al tamaño de pantalla (en celulares angostos las tarjetas se desplazan de lado).
La versión web incluye música ambiental suave en los menús y una melodía arcade original mientras la ronda está en curso. Cuando un jugador llega a SIGLO, el navegador anuncia «¡SIGLO!» con voz en español. El cambio de música es automático; la música se activa tras la primera interacción. Puedes silenciarla o reactivarla desde el botón, y se recuerda tu preferencia en ese navegador.

**Subirlo a un hosting con Docker** (Render, Railway, Fly.io, un VPS...): el `Dockerfile` de la raíz ya está listo. Los hostings suelen definir la variable `PORT`; el servidor la respeta. Ruta de comprobación de salud: `/health`.
```bash
docker build -t siglo .
docker run -p 8080:8080 siglo
```

**En un VPS con dominio y HTTPS** (recomendado; el navegador exige `wss://` si la página es `https://`). Con Caddy basta este `Caddyfile` (pide el certificado solo):
```
tu-dominio.com {
    reverse_proxy 127.0.0.1:8080
}
```
Con nginx hay que dejar pasar el WebSocket: en el `location /` agrega `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`.

Importante: el servidor guarda **una sola mesa en memoria**, así que debe ser una única instancia (no escales a varias réplicas) y se reinicia limpia si se cae. No tiene contraseña: cualquiera con el enlace puede sentarse.

## Cuentas, historial y base de datos

Hay tres formas de entrar: **invitado** (no se guarda nada), **iniciar sesión** o **crear cuenta**.

- **Navegador:** pantalla de inicio con usuario y contraseña (sesión por cookie). Muestra tus partidas, victorias y derrotas.
- **Escritorio (`cliente.py`) y 3D (`cliente_3d.py`):** pestañas *Invitado / Iniciar sesión / Registrarme*; la mesa muestra tus partidas jugadas y ganadas.
- Usuario: 3 a 10 caracteres (letras, números o `_`), sin distinguir mayúsculas. Contraseña: 8 a 128 caracteres, guardada solo como hash PBKDF2-SHA256 con sal.
- Una misma cuenta no puede sentarse dos veces en la mesa.

**Dónde se guardan los datos**
- Por defecto, en **SQLite**: `siglo_game/data/siglo.db` (cámbialo con la variable `SIGLO_DATABASE`).
- Si existe `DATABASE_URL`, usa **PostgreSQL** (crea las tablas `acct_users`, `acct_sessions` y `acct_games` solo). Es lo recomendado en un hosting como Render, donde el disco se borra al reiniciar.

En Render: *New + → PostgreSQL* (plan gratis), copia su **Internal Database URL**, y en tu Web Service ve a *Environment → Add Environment Variable*: `DATABASE_URL` = esa URL. Guarda y Render redespliega solo.

Pruebas contra un PostgreSQL real (se omiten si no hay): `SIGLO_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost/siglo_test pytest`.

## Vista 3D en el navegador

En la mesa del navegador hay un botón **VISTA 3D / VISTA 2D** (arriba a la derecha). Usa three.js (incluido en `web/vendor/`, no hace falta instalar nada) y recuerda tu elección. Si el navegador no soporta WebGL, se queda en 2D.

## Cliente 3D de escritorio (opcional, Ursina)

`pip install ursina` y luego `python cliente_3d.py` desde la raíz del proyecto (con `servidor.py` corriendo). Solo escritorio.

## Reglas Principales
- **Bolas**: 90 fichas numeradas del 1 al 90 sin repetición.
- **Viras**: Fichas mostradas al inicio.
- **Me quedo**: El jugador decide no sacar más bolas.
- **Bola**: El jugador extrae otra ficha.
- **Me fui**: El jugador supera los 100 puntos.
- **Siglo**: El jugador alcanza 99 o 100 puntos exactos.

## Controles
- Todo el juego se maneja mediante clics del ratón en la interfaz gráfica.
- Modo solitario (contra la IA): botones BOLA (pedir ficha) y ME QUEDO.
- Modo multijugador con 2 jugadores: BOLA (autoservicio) y ME QUEDO, igual que el solitario.
- Modo multijugador con 3+ jugadores: el anfitrión usa REPARTIR (le da la ficha a quien tenga el turno); cada jugador usa su propio ME QUEDO para plantarse.

## Pruebas
Para ejecutar las pruebas:
```bash
pytest tests/
```

## Arquitectura
El código está modularizado en la carpeta `src/` e implementa clases para `Game`, `Player`, `Deck`, `Ball` y `UI`, manejando un sistema de estados claro.

Multijugador (protocolo: una línea JSON por mensaje sobre TCP, descrito en `src/protocol.py`):
- `match.py`: reglas de la mesa en red (reutiliza `Deck`, `Player` y `Rules`), sin sockets ni pygame.
- `server.py`: servidor `asyncio` que valida cada acción con `Match` y difunde el estado.
- `net_client.py` y `online.py`: conexión en hilo aparte y pantallas del cliente.
- `board_ui.py`: mesa, fichas y tarjetas de jugador (mismo dibujo en solitario y en línea).
- `webapp.py` y `web/` (`index.html`, `style.css`, `app.js`): servidor aiohttp y cliente del navegador (canvas + WebSocket, sin paso de compilación). Reproduce los mismos colores y fichas que `board_ui.py`.
