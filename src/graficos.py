import matplotlib.pyplot as plt
import pandas as pd
import os

from src.fluido import generar_perfil_presion, generar_perfil_presion_con_bomba_desconocida, \
    generar_perfil_con_bombas_automaticas


def graficar_perfil_con_presion(csv_path, puntos_presion=None, titulo='Perfil de Terreno CSB con Presión'):
    """
    Grafica el perfil del terreno y opcionalmente puntos de presión en la tubería.

    Parámetros:
    -----------
    csv_path : str
        Ruta al archivo CSV del terreno.
    puntos_presion : list o tuple de dos arrays/lists (distancia, altura_presion)
        Ejemplo: ([0, 5, 10], [12, 14, 13])
    titulo : str
        Título del gráfico.
    """
    # Leer CSV
    df = pd.read_csv(csv_path, header=None)
    distancia_terreno = df.iloc[:, 0]
    altura_terreno = df.iloc[:, 1]

    plt.figure(figsize=(10, 6))
    # Perfil del terreno
    plt.plot(distancia_terreno, altura_terreno, '-', color='green', label='Terreno CSB')

    # Puntos de presión en la tubería
    if puntos_presion is not None:
        dist_p, alt_p = puntos_presion
        plt.plot(dist_p, alt_p, '-', color='red', label='Altura presión tubería')

    plt.xlabel('Distancia horizontal [m]')
    plt.ylabel('Altura [m]')
    plt.title(titulo)
    plt.grid(True)
    plt.legend()
    plt.show()

def graficar_perfil_y_presion(
    P_geo_csv,
    fluido,
    tuberia,
    presion_final_m,
    presion_inicial_m=None,
    bombas=None,
    titulo='Perfil y Línea de Presión'
):
    """
    Grafica el perfil topográfico y la línea de presión del fluido,
    considerando opcionalmente bombas y presión inicial conocida.
    """

    # Generar perfil de presión
    if presion_inicial_m is None:
        x, h_presion = generar_perfil_presion(P_geo_csv, fluido, tuberia, presion_final_m, bombas=bombas)
        bombas_result = bombas or []
    else:
        x, h_presion, bombas_result = generar_perfil_presion_con_bomba_desconocida(
            P_geo_csv, fluido, tuberia, presion_inicial_m, presion_final_m, bombas=bombas
        )

    # Leer perfil topográfico
    df = pd.read_csv(P_geo_csv, header=None)
    terreno_x = df[0].to_list()
    terreno_y = df[1].to_list()

    # Crear figura
    plt.figure(figsize=(10, 6))
    plt.plot(terreno_x, terreno_y, '-', color='green', label='Terreno CSB')
    plt.plot(x, h_presion, '-', color='blue', label='Línea de presión del fluido')

    # Graficar bombas sobre la línea de presión
    if bombas_result:
        print(bombas_result)
        for bomba in bombas_result:
            x_b = bomba['x']
            head_b = bomba['head']
            # Encontrar índice del punto más cercano
            idx = min(range(len(x)), key=lambda i: abs(x[i] - x_b))
            h_bomba = h_presion[idx]

            # Marcador exactamente sobre la línea de presión
            plt.scatter(x_b, h_bomba, color='red', marker='^', s=80,
                        label='Bomba' if 'Bomba' not in plt.gca().get_legend_handles_labels()[1] else "")
            plt.text(x_b, h_bomba + 0.5, f"+{head_b:.2f} m", color='red', ha='center', fontsize=9)

    # Mostrar presiones manométricas inicial y final
    presion_inicial_mano = h_presion[0] - terreno_y[0]
    presion_final_mano = h_presion[-1] - terreno_y[-1]

    plt.text(x[0], h_presion[0] + 1, f"{presion_inicial_mano:.2f} m", color='black', fontsize=9, ha='center')
    plt.text(x[-1], h_presion[-1] + 1, f"{presion_final_mano:.2f} m", color='black', fontsize=9, ha='center')

    # Detalles del gráfico
    plt.xlabel('Distancia horizontal [m]')
    plt.ylabel('Altura [m]')
    plt.title(titulo)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def graficar_perfil_con_bombas_automaticas(
    P_geo_csv,
    x_final,
    h_final,
    bombas,
    titulo='Perfil con Bombas Automáticas'
):
    """
    Grafica el perfil topográfico y la línea de presión generada automáticamente
    con bombas agregadas según la altura de seguridad.

    Parámetros:
    -----------
    P_geo_csv : str
        Ruta al archivo CSV con las columnas [x, z].
    x_final : list[float]
        Lista de posiciones X del perfil de presión.
    h_final : list[float]
        Lista de alturas totales (presión + cota).
    bombas : list[dict]
        Lista de bombas con 'x' y 'head'.
    titulo : str
        Título del gráfico.
    """

    # Leer perfil del terreno
    df = pd.read_csv(P_geo_csv, header=None)
    terreno_x = df[0].to_list()
    terreno_y = df[1].to_list()

    # Crear figura
    plt.figure(figsize=(10, 6))

    # Dibujar terreno y línea de presión
    plt.plot(terreno_x, terreno_y, '-', color='green', label='Terreno CSB')
    plt.plot(x_final, h_final, '-', color='blue', label='Línea de presión del fluido')

    # Dibujar bombas si existen
    if bombas:
        for bomba in bombas:
            x_b = bomba['x']
            head_b = bomba['head']
            # Buscar el punto más cercano para ubicar el triángulo sobre la línea de presión
            idx = min(range(len(x_final)), key=lambda i: abs(x_final[i] - x_b))
            h_bomba = h_final[idx]

            # Triángulo rojo encima de la línea de presión
            plt.scatter(x_b, h_bomba, color='red', marker='^', s=80,
                        label='Bomba' if 'Bomba' not in plt.gca().get_legend_handles_labels()[1] else "")
            plt.text(x_b, h_final[idx + 1] + 1, f"+{head_b:.2f} m", color='red', ha='center', fontsize=9)

    # Presiones manométricas inicial y final
    presion_inicial_mano = h_final[0] - terreno_y[0]
    presion_final_mano = h_final[-1] - terreno_y[-1]

    plt.text(x_final[0], terreno_y[0] - 2, f"{presion_inicial_mano:.2f} m", color='black', fontsize=9, ha='center')
    plt.text(x_final[-1], terreno_y[-1] - 2, f"{presion_final_mano:.2f} m", color='black', fontsize=9, ha='center')

    # Configuración del gráfico
    plt.xlabel('Distancia horizontal [m]')
    plt.ylabel('Altura [m]')
    plt.title(titulo)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    csv_path = os.path.join(BASE_DIR, 'data', 'P_geo.csv')

    fluido = {'densidad': 946, 'viscosidad': 0.00025, 'velocidad': 1.1}
    tuberia = {'diametro': 257 / 1000, 'rugosidad': 0.045}

    bombas = [
        # {'x': 150, 'head': 7},
        {'x': 120, 'head': None}
    ]

    graficar_perfil_y_presion(
        csv_path,
        fluido=fluido,
        tuberia=tuberia,
        presion_final_m=28,
        presion_inicial_m=15,
        bombas=bombas,
        titulo='Perfil con Bombas'
    )

    # x_final, h_final, bombas = generar_perfil_con_bombas_automaticas(
    #     P_geo_csv=csv_path,
    #     fluido=fluido,
    #     tuberia=tuberia,
    #     presion_inicial_m=2,
    #     altura_seguridad=3,
    #     head_bomba=6,
    #     num_puntos_extra=5
    # )
    #
    # graficar_perfil_con_bombas_automaticas(
    #     P_geo_csv=csv_path,
    #     x_final=x_final,
    #     h_final=h_final,
    #     bombas=bombas,
    #     titulo="Perfil con Bombas Automáticas"
    # )