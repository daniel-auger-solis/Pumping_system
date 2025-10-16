import unittest
from src.fluido import calcular_estado_final_tuberia_con_perdida

class TestCalculoTuberia(unittest.TestCase):
    def test_resultado_basico(self):
        fluido = {
            'presion': 200000,
            'velocidad': 1.5,
            'densidad': 1000,
            'altura': 0.0,
            'viscosidad': 0.001
        }

        tuberia = {
            'diametro_inicial': 0.1,
            'diametro_final': 0.1,
            'longitud': 50.0,
            'altura_final': 1.0,
            'rugosidad': 0.0002
        }

        resultado = calcular_estado_final_tuberia_con_perdida(fluido, tuberia)

        self.assertLess(resultado['presion_final'], fluido['presion'])
        self.assertGreater(resultado['velocidad_final'], 0)
        self.assertGreater(resultado['perdida_carga'], 0)
        self.assertGreater(resultado['numero_reynolds'], 2000)
        self.assertTrue(0.01 < resultado['factor_friccion'] < 0.1)

if __name__ == '__main__':
    unittest.main()