import serial
import time
import sqlite3
import csv
import os

# --- CONFIGURACIÓN ---
# Reemplaza 'COM3' por el puerto exacto asignado a tu Arduino en Windows (o '/dev/ttyUSB0' en Linux)
PUERTO_COM = 'COM3'
BAUD_RATE = 9600
DB_NAME = "laboratorio_newton.db"
CSV_NAME = "datos_laboratorio_newton.csv"

# --- INICIALIZACIÓN DE BASE DE DATOS LOCAL (SQLite) ---
def inicializar_bd():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mediciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT,
            masa_carrito_g REAL,
            masa_colgante_kg REAL,
            distancia_cm REAL,
            tiempo_s REAL,
            aceleracion_m_s2 REAL
        )
    """)
    conn.commit()
    conn.close()

# --- GUARDAR MEDICIÓN EN SQLite Y CSV ---
def guardar_registro(m_carrito, m_colgante, distancia, tiempo, aceleracion):
    fecha_hora = time.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Inserción en Base de Datos SQLite
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mediciones (fecha_hora, masa_carrito_g, masa_colgante_kg, distancia_cm, tiempo_s, aceleracion_m_s2)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (fecha_hora, m_carrito, m_colgante, distancia, tiempo, aceleracion))
    conn.commit()
    conn.close()

    # 2. Respaldo en archivo CSV (formato tabular para Excel)
    archivo_existe = os.path.isfile(CSV_NAME)
    with open(CSV_NAME, mode='a', newline='', encoding='utf-8') as archivo_csv:
        writer = csv.writer(archivo_csv)
        if not archivo_existe:
            writer.writerow(["ID", "Fecha_Hora", "Masa_Carrito_g", "Masa_Colgante_kg", "Distancia_cm", "Tiempo_s", "Aceleracion_m_s2"])
        writer.writerow([None, fecha_hora, m_carrito, m_colgante, distancia, tiempo, aceleracion])

    print(f"\n[OK] Datos guardados exitosamente en '{DB_NAME}' y '{CSV_NAME}'.")

# --- FLUJO PRINCIPAL ---
def main():
    inicializar_bd()
    
    print("==================================================")
    print(" SISTEMA DE ADQUISICIÓN DE DATOS - LAB DE FÍSICA  ")
    print("==================================================")

    # Solicitar masa colgante para correlacionar con la Tabla N° 3 del laboratorio
    masa_carrito = 139.74  # Gramos fijos del móvil
    try:
        masa_colgante = float(input("Ingrese la masa del contrapeso m en kg (ejemplo: 2.370): "))
    except ValueError:
        masa_colgante = 0.0

    print(f"\nConectando al puerto {PUERTO_COM}...")
    try:
        arduino = serial.Serial(PUERTO_COM, BAUD_RATE, timeout=1)
        time.sleep(2)  # Pausa para que el Arduino complete el reinicio serial
        print("Conexion establecida. Esperando lanzamiento del carrito en la pista...\n")
    except serial.SerialException:
        print(f"[ERROR] No se pudo abrir el puerto {PUERTO_COM}. Asegurate de que el monitor serie de Arduino IDE este cerrado.")
        return

    try:
        while True:
            if arduino.in_waiting > 0:
                linea = arduino.readline().decode('utf-8', errors='ignore').strip()
                if linea:
                    print(f"[Arduino] {linea}")

                    # Detecta la línea clave generada por el código de Arduino
                    if linea.startswith("CSV_DATA:"):
                        datos = linea.replace("CSV_DATA:", "").split(",")
                        if len(datos) == 2:
                            tiempo = float(datos[0])
                            aceleracion = float(datos[1])
                            distancia = 70.0  # cm fijados en la práctica

                            guardar_registro(masa_carrito, masa_colgante, distancia, tiempo, aceleracion)
                            print("\nToma finalizada. Reinicie el Arduino para el siguiente ensayo.")
                            break
    except KeyboardInterrupt:
        print("\nPrograma detenido manualmente.")
    finally:
        arduino.close()

if __name__ == "__main__":
    main()