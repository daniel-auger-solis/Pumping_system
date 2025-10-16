import math
import pandas as pd
import numpy as np
from src.constantes import G


def interpolar_perfil(P_geo_csv, num_puntos_extra=10):
    """
    Interpola linealmente puntos entre los existentes en un perfil topográfico.

    Parámetros:
    -----------
    P_geo_csv: str
        Ruta al CSV que contiene columnas [x, z].
    num_puntos_extra: int
        Cantidad de puntos a agregar entre cada par de puntos originales.

    Retorna:
    --------
    x_interp: list[float]
        Lista de posiciones X interpoladas.
    z_interp: list[float]
        Lista de alturas Z interpoladas.
    """
    # Leer perfil original
    df = pd.read_csv(P_geo_csv, header=None)
    x = df.iloc[:, 0].to_numpy()
    z = df.iloc[:, 1].to_numpy()

    x_interp = []
    z_interp = []

    for i in range(len(x) - 1):
        x_start, x_end = x[i], x[i + 1]
        z_start, z_end = z[i], z[i + 1]

        # Crear puntos interpolados linealmente
        xs = np.linspace(x_start, x_end, num_puntos_extra + 2)  # +2 para incluir extremos
        zs = np.linspace(z_start, z_end, num_puntos_extra + 2)

        # Evitar duplicar el último punto del segmento anterior
        if i > 0:
            xs = xs[1:]
            zs = zs[1:]

        x_interp.extend(xs)
        z_interp.extend(zs)

    return x_interp, z_interp

def colebrook(Re, D, epsilon, tol=1e-6, max_iter=100):
    """
    Calcula el factor de fricción usando la ecuación de Colebrook para flujo turbulento
    """
    f = 0.02  # valor inicial
    for _ in range(max_iter):
        f_old = f
        # Colebrook equation
        f = (-2*math.log10((epsilon/(3.7*D)) + (2.51/(Re*math.sqrt(f)))))**-2
        if abs(f - f_old) < tol:
            break
    return f

def calcular_estado_final_tuberia_con_perdida(fluido, tuberia):
    """
    Calcula presión, velocidad y altura de presión con pérdida calculada automáticamente.
    """

    # Datos iniciales
    P1 = fluido['presion']
    v1 = fluido['velocidad']
    rho = fluido['densidad']
    z1 = fluido['altura']
    mu = fluido.get('viscosidad', 0.001)  # viscosidad [Pa.s], default agua 20°C

    # Datos de la tubería
    D1 = tuberia['diametro_inicial']
    D2 = tuberia['diametro_final']
    L = tuberia.get('longitud', 10.0)      # longitud de tubería [m], valor por defecto
    z2 = tuberia['altura_final']
    epsilon = tuberia.get('rugosidad', 0.0002)  # rugosidad absoluta [m], default acero liso

    # 1️⃣ Velocidad final usando continuidad
    A1 = math.pi * (D1 ** 2) / 4
    A2 = math.pi * (D2 ** 2) / 4
    v2 = v1 * (A1 / A2)

    # 2️⃣ Calcular Reynolds para la sección final
    Re = rho * v2 * D2 / mu

    # 3️⃣ Determinar factor de fricción
    if Re < 2000:  # laminar
        f = 64 / Re
    else:  # turbulento
        f = colebrook(Re, D2, epsilon)

    # 4️⃣ Calcular pérdida de carga Darcy-Weisbach
    hL = f * (L / D2) * (v2**2) / (2 * G)

    # 5️⃣ Aplicar Bernoulli con pérdidas
    head1 = (P1 / (rho * G)) + (v1 ** 2) / (2 * G) + z1
    head2 = head1 - hL
    P2 = rho * G * (head2 - (v2 ** 2) / (2 * G) - z2)
    altura_presion_final = P2 / (rho * G)

    return {
        'presion_final': P2,
        'velocidad_final': v2,
        'altura_presion_final': altura_presion_final,
        'perdida_carga': hL,
        'numero_reynolds': Re,
        'factor_friccion': f
    }

def generar_perfil_presion(P_geo_csv, fluido, tuberia, presion_final_m, bombas=None):
    """
    Genera los puntos (x, h_fluido) del perfil de presión (en metros de columna de agua)
    a lo largo del perfil geográfico, considerando bombas que entregan energía al sistema.
    El cálculo inicial se hace en reversa (desde el extremo final) y luego se agregan bombas.
    """
    rho = fluido['densidad']
    mu = fluido['viscosidad']
    v = fluido['velocidad']

    # Leer perfil topográfico
    df = pd.read_csv(P_geo_csv, header=None)
    x = df.iloc[:, 0].to_list()
    z = df.iloc[:, 1].to_list()

    # Datos de la tubería
    D = tuberia['diametro']
    epsilon = tuberia.get('rugosidad', 0.0002)

    # Número de Reynolds y factor de fricción
    Re = rho * v * D / mu
    f = 64 / Re if Re < 2000 else colebrook(Re, D, epsilon)

    # ----------------------------
    # 1️⃣ Generar perfil en reversa (desde el extremo final)
    # ----------------------------
    x_rev = x[::-1]
    z_rev = z[::-1]

    h_total_rev = [presion_final_m + z_rev[0]]  # punto final con presión final conocida

    for i in range(1, len(x_rev)):
        dx = x_rev[i-1] - x_rev[i]  # distancia entre puntos consecutivos en reversa
        dz = z_rev[i-1] - z_rev[i]
        L_real = math.sqrt(dx**2 + dz**2)
        hf = f * (L_real / D) * (v**2) / (2 * G)
        h_total_rev.append(h_total_rev[-1] + hf)  # acumulamos hacia atrás

    # Revertir para orden normal de X
    x_list, h_list = x_rev[::-1], h_total_rev[::-1]

    # ----------------------------
    # 2️⃣ Insertar bombas
    # ----------------------------
    bombas = bombas or []
    bombas = sorted(bombas, key=lambda b: b['x'])

    x_final = x_list.copy()
    h_final = h_list.copy()

    for bomba in bombas:
        x_b = bomba['x']
        head = bomba['head']

        # Interpolar altura en la posición de la bomba si no existe
        if x_b not in x_final:
            h_bomba = np.interp(x_b, x_final, h_final)
            x_final.append(x_b)
            h_final.append(h_bomba)

        # Reordenar listas después de agregar bomba
        x_final, h_final = zip(*sorted(zip(x_final, h_final)))
        x_final = list(x_final)
        h_final = list(h_final)

        # Encontrar índice del punto de la bomba
        idx_bomba = x_final.index(x_b)

        # 1️⃣ Punto antes de la bomba (misma X, altura siguiendo pérdidas)
        # Se calcula como interpolación entre el punto anterior y el siguiente original
        if idx_bomba > 0:
            h_antes = np.interp(x_b - 1e-6, x_final, h_final)  # muy cerca antes de la bomba
        else:
            h_antes = h_final[idx_bomba]  # si es el primer punto

        x_final.insert(idx_bomba, x_final[idx_bomba])
        h_final.insert(idx_bomba, h_antes)

        # 2️⃣ Aplicar salto de la bomba
        h_final[idx_bomba + 1] += head

        # 3️⃣ Sumar efecto de la bomba a todos los puntos posteriores
        for i in range(idx_bomba + 2, len(h_final)):
            h_final[i] += head

    # Ajustar el perfil para que el último punto coincida con la presión final deseada
    delta = (presion_final_m + z[-1]) - h_final[-1]
    h_final = [h + delta for h in h_final]

    return x_final, h_final

def agregar_bomba(x_final, h_final, x_b, head):
    """
    Inserta una bomba en el perfil, agregando un punto antes y sumando el head a los puntos posteriores.
    """

    # Guardar altura final original (para mantenerla igual después del ajuste)
    h_final_original = h_final[-1]

    # Interpolar altura si la bomba no está en la lista
    if x_b not in x_final:
        h_bomba = np.interp(x_b, x_final, h_final)
        x_final.append(x_b)
        h_final.append(h_bomba)

    # Reordenar listas
    x_final, h_final = zip(*sorted(zip(x_final, h_final)))
    x_final, h_final = list(x_final), list(h_final)

    # Encontrar índice del punto de la bomba
    idx_bomba = x_final.index(x_b)

    # Punto antes de la bomba (misma X, altura siguiendo pérdidas)
    h_antes = np.interp(x_b - 1e-6, x_final, h_final) if idx_bomba > 0 else h_final[idx_bomba]
    x_final.insert(idx_bomba, x_b)
    h_final.insert(idx_bomba, h_antes)

    # Aplicar efecto de la bomba a este punto y posteriores
    h_final[idx_bomba + 1] += head
    for i in range(idx_bomba + 2, len(h_final)):
        h_final[i] += head

    # 🔹 Ajuste final: mantener la misma altura final que antes
    delta = h_final_original - h_final[-1]
    h_final = [h + delta for h in h_final]

    return x_final, h_final

def generar_perfil_presion_con_bomba_desconocida(
    P_geo_csv, fluido, tuberia, presion_inicial_m, presion_final_m, bombas=None
):
    """
    Genera el perfil de presión considerando:
    - Presión inicial en el primer punto.
    - Presión final en el último punto.
    - Bombas, donde si una bomba no tiene 'head', se calcula automáticamente para cumplir las condiciones.

    Retorna:
    --------
    x_final: list
        Lista de posiciones X
    h_final: list
        Lista de altura total (cota + presión)
    bombas_result: list[dict]
        Lista de bombas con todos los 'head' completados
    """

    rho = fluido['densidad']
    mu = fluido['viscosidad']
    v = fluido['velocidad']

    # Leer perfil topográfico
    df = pd.read_csv(P_geo_csv, header=None)
    x = df.iloc[:, 0].to_list()
    z = df.iloc[:, 1].to_list()

    # Datos de la tubería
    D = tuberia['diametro']
    epsilon = tuberia.get('rugosidad', 0.0002)

    # Número de Reynolds y factor de fricción
    Re = rho * v * D / mu
    f = 64 / Re if Re < 2000 else colebrook(Re, D, epsilon)
    print(f"Re: {Re}, f: {f}")

    # ----------------------------
    # 1️⃣ Generar perfil en reversa (desde el extremo final) sin bombas
    # ----------------------------
    x_rev = x[::-1]
    z_rev = z[::-1]

    L_total = 0
    h_total_rev = [presion_final_m + z_rev[0]]
    for i in range(1, len(x_rev)):
        dx = x_rev[i-1] - x_rev[i]
        dz = z_rev[i-1] - z_rev[i]
        L_real = math.sqrt(dx**2 + dz**2)
        hf = f * (L_real / D) * (v**2) / (2 * G)
        h_total_rev.append(h_total_rev[-1] + hf)
        L_total += L_real
    print(f"L_total: {L_total}")

    # Revertir al orden normal
    x_list, h_list = x_rev[::-1], h_total_rev[::-1]

    # ----------------------------
    # 2️⃣ Insertar solo bombas conocidas
    # ----------------------------
    bombas_result = []
    bombas_conocidas = [b for b in bombas if b.get('head') is not None]
    x_final = x_list.copy()
    h_final = h_list.copy()

    for bomba in bombas_conocidas:
        x_final, h_final = agregar_bomba(x_final, h_final, bomba['x'], bomba['head'])
        bombas_result.append({'x': bomba['x'], 'head': bomba['head']})

    # ----------------------------
    # 4️⃣ Insertar bomba faltante (head=None)
    # ----------------------------

    # Calcular diferencia en primer punto según presion_inicial_m
    h_deseada_inicial = presion_inicial_m + z[0]
    delta_inicial = h_final[0] - h_deseada_inicial

    # Insertar bomba desconocida
    bombas_desconocida = [b for b in bombas if b.get('head') is None]
    if bombas_desconocida:
        b = bombas_desconocida[0]
        head = delta_inicial
        x_final, h_final = agregar_bomba(x_final, h_final, b['x'], head)
        bombas_result.append({'x': b['x'], 'head': head})

    return x_final, h_final, bombas_result

def generar_perfil_con_bombas_automaticas(
    P_geo_csv,
    fluido,
    tuberia,
    presion_inicial_m,
    altura_seguridad,
    head_bomba,
    num_puntos_extra=None
):
    """
    Genera el perfil de presión considerando pérdidas y agrega bombas automáticamente
    cuando la altura total cae por debajo del terreno + altura_seguridad.
    """

    # Leer perfil topográfico
    if num_puntos_extra is None:
        df = pd.read_csv(P_geo_csv, header=None)
        x = df.iloc[:, 0].to_list()
        z = df.iloc[:, 1].to_list()
    else:
        x, z = interpolar_perfil(P_geo_csv, num_puntos_extra=num_puntos_extra)

    # Parámetros del fluido y tubería
    rho = fluido['densidad']
    mu = fluido['viscosidad']
    v = fluido['velocidad']
    D = tuberia['diametro']
    epsilon = tuberia.get('rugosidad', 0.0002)

    # Reynolds y factor de fricción
    Re = rho * v * D / mu
    f = 64 / Re if Re < 2000 else colebrook(Re, D, epsilon)

    # Inicialización
    h_final = [presion_inicial_m + z[0]]  # Altura total inicial
    bombas = []
    x_final = [x[0]]

    # ----- Analizar primer punto -----
    h0 = presion_inicial_m + z[0]
    if (h0 - z[0]) <= altura_seguridad:
        # Insertar bomba desde el inicio
        h_final.append(h0 + head_bomba)
        x_final.append(x[0])
        bombas.append({'x': x[0], 'head': head_bomba})
        print(f"💧 Bomba agregada en x={x[0]:.1f} m (head={head_bomba} m)")
    else:
        h_final.append(h0)
        x_final.append(x[0])

    # Recorrido a lo largo del perfil (desde el segundo punto)
    for i in range(1, len(x)):
        dx = x[i] - x[i - 1]
        dz = z[i] - z[i - 1]
        L_real = math.sqrt(dx ** 2 + dz ** 2)

        # Pérdida de carga
        hf = f * (L_real / D) * (v ** 2) / (2 * G)

        # Actualizar altura total considerando pérdida
        h_nueva = h_final[-1] - hf
        x_final.append(x[i])
        h_final.append(h_nueva)

        # Verificar si cae bajo la altura de seguridad
        if (h_nueva - z[i]) <= altura_seguridad:
            # Guardar la altura antes del salto
            h_antes_bomba = h_nueva

            # Agregar bomba al registro
            bombas.append({'x': x[i], 'head': head_bomba})

            # Insertar punto vertical en x_final / h_final (sin tocar x original)
            x_final.append(x[i])  # mismo punto X
            h_final.append(h_antes_bomba + head_bomba)  # salto de presión

            # Actualizar h_nueva para seguir el recorrido
            h_nueva = h_antes_bomba + head_bomba
            h_final[-1] = h_nueva

            print(f"💧 Bomba agregada en x={x[i]:.1f} m (head={head_bomba} m)")

    return x_final, h_final, bombas

if __name__ == "__main__":
    fluido_1 = {
        'presion': 200000,  # Pa
        'velocidad': 2.0,  # m/s
        'densidad': 1000,  # kg/m³
        'altura': 5.0,  # m
        'viscosidad': 0.001  # Pa.s
    }

    tuberia_1 = {
        'diametro_inicial': 0.1,  # m
        'diametro_final': 0.08,  # m
        'altura_final': 8.0,  # m
        'longitud': 20.0,  # m
        'rugosidad': 0.0002  # m
    }

    resultado = calcular_estado_final_tuberia_con_perdida(fluido_1, tuberia_1)
    print(resultado)