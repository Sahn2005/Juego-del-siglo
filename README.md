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

Dos aclaraciones
El texto de la pantalla REGLAS del juego es impreciso. Dice que con SIGLO ganas automáticamente si nadie te empata. En el código no es automático: quien saque 99 pierde contra otro que saque 100. El resultado depende del puntaje más alto, no de haber hecho SIGLO.
Esto es lo que programó tu proyecto. Si en tu grupo o tu curso se juega distinto, por ejemplo con otro valor de las fichas o con premios por SIGLO, dímelo y lo ajusto.
