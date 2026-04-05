import math
import pandas as pd
import numpy as np
from src.constantes import G


def interpolar_perfil(P_geo_csv, num_puntos_extra=10):
    df = pd.read_csv(P_geo_csv, header=None)
    x = df.iloc[:, 0].to_numpy()
    z = df.iloc[:, 1].to_numpy()

    x_interp = []
    z_interp = []

    for i in range(len(x) - 1):
        x_start, x_end = x[i], x[i + 1]
        z_start, z_end = z[i], z[i + 1]
        xs = np.linspace(x_start, x_end, num_puntos_extra + 2)
        zs = np.linspace(z_start, z_end, num_puntos_extra + 2)
        if i > 0:
            xs = xs[1:]
            zs = zs[1:]
        x_interp.extend(xs)
        z_interp.extend(zs)

    return x_interp, z_interp


def colebrook(Re, D, epsilon, tol=1e-6, max_iter=100):
    f = 0.02
    for _ in range(max_iter):
        f_old = f
        f = (-2 * math.log10((epsilon / (3.7 * D)) + (2.51 / (Re * math.sqrt(f))))) ** -2
        if abs(f - f_old) < tol:
            break
    return f


def calcular_estado_final_tuberia_con_perdida(fluido, tuberia):
    P1  = fluido['presion']
    v1  = fluido['velocidad']
    rho = fluido['densidad']
    z1  = fluido['altura']
    mu  = fluido.get('viscosidad', 0.001)

    D1      = tuberia['diametro_inicial']
    D2      = tuberia['diametro_final']
    L       = tuberia.get('longitud', 10.0)
    z2      = tuberia['altura_final']
    epsilon = tuberia.get('rugosidad', 0.0002)

    A1 = math.pi * (D1 ** 2) / 4
    A2 = math.pi * (D2 ** 2) / 4
    v2 = v1 * (A1 / A2)

    Re = rho * v2 * D2 / mu
    f  = 64 / Re if Re < 2000 else colebrook(Re, D2, epsilon)

    hL    = f * (L / D2) * (v2 ** 2) / (2 * G)
    head1 = (P1 / (rho * G)) + (v1 ** 2) / (2 * G) + z1
    head2 = head1 - hL
    P2    = rho * G * (head2 - (v2 ** 2) / (2 * G) - z2)
    altura_presion_final = P2 / (rho * G)

    return {
        'presion_final':         P2,
        'velocidad_final':       v2,
        'altura_presion_final':  altura_presion_final,
        'perdida_carga':         hL,
        'numero_reynolds':       Re,
        'factor_friccion':       f,
    }


def generar_perfil_presion(P_geo_csv, fluido, tuberia, presion_final_m, bombas=None):
    rho = fluido['densidad']
    mu  = fluido['viscosidad']
    v   = fluido['velocidad']

    df      = pd.read_csv(P_geo_csv, header=None)
    x       = df.iloc[:, 0].to_list()
    z       = df.iloc[:, 1].to_list()
    D       = tuberia['diametro']
    epsilon = tuberia.get('rugosidad', 0.0002)

    Re = rho * v * D / mu
    f  = 64 / Re if Re < 2000 else colebrook(Re, D, epsilon)

    x_rev = x[::-1]
    z_rev = z[::-1]
    h_total_rev = [presion_final_m + z_rev[0]]

    for i in range(1, len(x_rev)):
        dx     = x_rev[i - 1] - x_rev[i]
        dz     = z_rev[i - 1] - z_rev[i]
        L_real = math.sqrt(dx ** 2 + dz ** 2)
        hf     = f * (L_real / D) * (v ** 2) / (2 * G)
        h_total_rev.append(h_total_rev[-1] + hf)

    x_list, h_list = x_rev[::-1], h_total_rev[::-1]

    bombas  = sorted(bombas or [], key=lambda b: b['x'])
    x_final = x_list.copy()
    h_final = h_list.copy()

    for bomba in bombas:
        x_b  = bomba['x']
        head = bomba['head']
        if x_b not in x_final:
            h_bomba = np.interp(x_b, x_final, h_final)
            x_final.append(x_b)
            h_final.append(h_bomba)

        x_final, h_final = zip(*sorted(zip(x_final, h_final)))
        x_final = list(x_final)
        h_final = list(h_final)
        idx_bomba = x_final.index(x_b)
        h_antes   = np.interp(x_b - 1e-6, x_final, h_final) if idx_bomba > 0 else h_final[idx_bomba]
        x_final.insert(idx_bomba, x_final[idx_bomba])
        h_final.insert(idx_bomba, h_antes)
        h_final[idx_bomba + 1] += head
        for i in range(idx_bomba + 2, len(h_final)):
            h_final[i] += head

    delta   = (presion_final_m + z[-1]) - h_final[-1]
    h_final = [h + delta for h in h_final]

    return x_final, h_final


def agregar_bomba(x_final, h_final, x_b, head):
    h_final_original = h_final[-1]

    if x_b not in x_final:
        h_bomba = np.interp(x_b, x_final, h_final)
        x_final.append(x_b)
        h_final.append(h_bomba)

    x_final, h_final = zip(*sorted(zip(x_final, h_final)))
    x_final, h_final = list(x_final), list(h_final)

    idx_bomba = x_final.index(x_b)
    h_antes   = np.interp(x_b - 1e-6, x_final, h_final) if idx_bomba > 0 else h_final[idx_bomba]
    x_final.insert(idx_bomba, x_b)
    h_final.insert(idx_bomba, h_antes)
    h_final[idx_bomba + 1] += head
    for i in range(idx_bomba + 2, len(h_final)):
        h_final[i] += head

    delta   = h_final_original - h_final[-1]
    h_final = [h + delta for h in h_final]

    return x_final, h_final


def generar_perfil_presion_con_bomba_desconocida(
    P_geo_csv, fluido, tuberia, presion_inicial_m, presion_final_m, bombas=None
):
    rho = fluido['densidad']
    mu  = fluido['viscosidad']
    v   = fluido['velocidad']

    df      = pd.read_csv(P_geo_csv, header=None)
    x       = df.iloc[:, 0].to_list()
    z       = df.iloc[:, 1].to_list()
    D       = tuberia['diametro']
    epsilon = tuberia.get('rugosidad', 0.0002)

    Re = rho * v * D / mu
    f  = 64 / Re if Re < 2000 else colebrook(Re, D, epsilon)

    x_rev       = x[::-1]
    z_rev       = z[::-1]
    h_total_rev = [presion_final_m + z_rev[0]]

    for i in range(1, len(x_rev)):
        dx     = x_rev[i - 1] - x_rev[i]
        dz     = z_rev[i - 1] - z_rev[i]
        L_real = math.sqrt(dx ** 2 + dz ** 2)
        hf     = f * (L_real / D) * (v ** 2) / (2 * G)
        h_total_rev.append(h_total_rev[-1] + hf)

    x_list, h_list = x_rev[::-1], h_total_rev[::-1]

    bombas_result    = []
    bombas_conocidas = [b for b in bombas if b.get('head') is not None]
    x_final          = x_list.copy()
    h_final          = h_list.copy()

    for bomba in bombas_conocidas:
        x_final, h_final = agregar_bomba(x_final, h_final, bomba['x'], bomba['head'])
        bombas_result.append({'x': bomba['x'], 'head': bomba['head']})

    h_deseada_inicial  = presion_inicial_m + z[0]
    delta_inicial      = h_final[0] - h_deseada_inicial
    bombas_desconocida = [b for b in bombas if b.get('head') is None]

    if bombas_desconocida:
        b    = bombas_desconocida[0]
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
    num_puntos_extra=None,
    singularidades=None,
):
    """
    Genera el perfil de presión con bombas automáticas y pérdidas singulares.

    singularidades: list[dict] con claves 'x_m' y 'k'
        Cada singularidad aplica una pérdida puntual hf = K * v² / (2g)
        en la posición x_m indicada.
    """

    # Leer / interpolar perfil topográfico
    if num_puntos_extra is None:
        df = pd.read_csv(P_geo_csv, header=None)
        x  = df.iloc[:, 0].to_list()
        z  = df.iloc[:, 1].to_list()
    else:
        x, z = interpolar_perfil(P_geo_csv, num_puntos_extra=num_puntos_extra)

    # Parámetros hidráulicos
    rho     = fluido['densidad']
    mu      = fluido['viscosidad']
    v       = fluido['velocidad']
    D       = tuberia['diametro']
    epsilon = tuberia.get('rugosidad', 0.0002)

    Re = rho * v * D / mu
    f  = 64 / Re if Re < 2000 else colebrook(Re, D, epsilon)

    # Pérdida singular por unidad (hf_k = K * v² / 2g); se multiplica por k en cada punto
    hf_v = (v ** 2) / (2 * G)

    # Construir lookup de singularidades: {x_m: k_total}
    # (si hay dos singularidades en el mismo X, se suman los K)
    sing_lookup: dict[float, float] = {}
    for s in (singularidades or []):
        xk = float(s["x_m"])
        sing_lookup[xk] = sing_lookup.get(xk, 0.0) + float(s["k"])

    # Inicialización del recorrido
    h_final  = [presion_inicial_m + z[0]]
    x_final  = [x[0]]
    bombas   = []

    # ── Primer punto ──────────────────────────────────────────────────────────
    h0 = presion_inicial_m + z[0]
    if (h0 - z[0]) <= altura_seguridad:
        h_final.append(h0 + head_bomba)
        x_final.append(x[0])
        bombas.append({"x": x[0], "head": head_bomba})
    else:
        h_final.append(h0)
        x_final.append(x[0])

    # ── Recorrido principal ───────────────────────────────────────────────────
    for i in range(1, len(x)):
        dx     = x[i] - x[i - 1]
        dz     = z[i] - z[i - 1]
        L_real = math.sqrt(dx ** 2 + dz ** 2)

        # Pérdida distribuida (Darcy-Weisbach)
        hf_dist = f * (L_real / D) * (v ** 2) / (2 * G)

        # Pérdida singular en este punto (si existe)
        hf_sing = sing_lookup.get(float(x[i]), 0.0) * hf_v

        h_nueva = h_final[-1] - hf_dist
        x_final.append(x[i])
        h_final.append(h_nueva)

        # ── Aplicar singularidad (caída vertical hacia abajo) ─────────────────
        if hf_sing > 0:
            h_antes_sing = h_nueva
            h_tras_sing  = h_antes_sing - hf_sing
            # Insertar punto antes (misma X) para dibujar la caída vertical
            x_final.append(x[i])
            h_final.append(h_tras_sing)
            h_nueva = h_tras_sing

        # ── Verificar si necesita bomba ───────────────────────────────────────
        if (h_nueva - z[i]) <= altura_seguridad:
            h_antes_bomba = h_nueva
            bombas.append({"x": x[i], "head": head_bomba})
            x_final.append(x[i])
            h_final.append(h_antes_bomba + head_bomba)

    return x_final, h_final, bombas


if __name__ == "__main__":
    fluido_1 = {
        'presion':    200000,
        'velocidad':  2.0,
        'densidad':   1000,
        'altura':     5.0,
        'viscosidad': 0.001,
    }
    tuberia_1 = {
        'diametro_inicial': 0.1,
        'diametro_final':   0.08,
        'altura_final':     8.0,
        'longitud':         20.0,
        'rugosidad':        0.0002,
    }
    resultado = calcular_estado_final_tuberia_con_perdida(fluido_1, tuberia_1)
    print(resultado)
