
import pygame
import random
import sys

pygame.init()

# Ventana
ANCHO = 800
ALTO = 600

pantalla = pygame.display.set_mode((ANCHO, ALTO))
pygame.display.set_caption("Stickman Runner")

reloj = pygame.time.Clock()

# Colores
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)
ROJO = (255, 0, 0)
GRIS = (100, 100, 100)

# Carriles
carriles = [250, 400, 550]
carril_actual = 1

# Jugador
jugador_y = 500
salto = False
velocidad_salto = 0

# Obstáculos
obstaculos = []

# Puntuación
puntos = 0


def dibujar_stickman(x, y):
    pygame.draw.circle(pantalla, NEGRO, (x, y - 40), 15, 2)
    pygame.draw.line(pantalla, NEGRO, (x, y - 25), (x, y + 20), 3)
    pygame.draw.line(pantalla, NEGRO, (x - 15, y), (x + 15, y), 3)
    pygame.draw.line(pantalla, NEGRO, (x, y + 20), (x - 15, y + 45), 3)
    pygame.draw.line(pantalla, NEGRO, (x, y + 20), (x + 15, y + 45), 3)


def crear_obstaculo():
    carril = random.choice(carriles)
    obstaculos.append([carril, -50])


while True:
    for evento in pygame.event.get():
        if evento.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        if evento.type == pygame.KEYDOWN:
            if evento.key == pygame.K_LEFT and carril_actual > 0:
                carril_actual -= 1

            if evento.key == pygame.K_RIGHT and carril_actual < 2:
                carril_actual += 1

            if evento.key == pygame.K_UP and not salto:
                salto = True
                velocidad_salto = -18

    # Salto
    if salto:
        jugador_y += velocidad_salto
        velocidad_salto += 1

        if jugador_y >= 500:
            jugador_y = 500
            salto = False

    # Crear obstáculos
    if random.randint(1, 40) == 1:
        crear_obstaculo()
    # Mover obstáculos
    for obstaculo in list(obstaculos):
        obstaculo[1] += 5

        # Colisión simple
        jugador_x = carriles[carril_actual]
        distancia_x = abs(obstaculo[0] - jugador_x)
        if distancia_x < 30 and jugador_y > obstaculo[1] - 20:
            # Fin del juego
            print(f"Game over. Puntos: {puntos}")
            pygame.quit()
            sys.exit()

        # Si el obstáculo sale de la pantalla, eliminar y sumar punto
        if obstaculo[1] > ALTO + 50:
            obstaculos.remove(obstaculo)
            puntos += 1

    # Dibujar
    pantalla.fill(BLANCO)

    # Dibujar carriles (líneas guía)
    for x in carriles:
        pygame.draw.line(pantalla, GRIS, (x, 0), (x, ALTO), 1)

    # Dibujar obstáculos
    for obstaculo in obstaculos:
        ox, oy = obstaculo
        pygame.draw.rect(pantalla, ROJO, (ox - 20, oy - 20, 40, 40))

    # Dibujar jugador
    jugador_x = carriles[carril_actual]
    dibujar_stickman(jugador_x, jugador_y)

    # Puntuación
    try:
        fuente = pygame.font.SysFont(None, 36)
        texto = fuente.render(f"Puntos: {puntos}", True, NEGRO)
        pantalla.blit(texto, (10, 10))
    except Exception:
        pass

    pygame.display.flip()
    reloj.tick(60)
