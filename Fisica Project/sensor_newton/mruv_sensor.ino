/*
 * PROYECTO: Sistema Automatizado de Medición y Almacenamiento de Datos en Tiempo Real 
 *           Mediante Arduino para el Estudio Experimental del MRUV
 * HARDWARE: Arduino Uno R3 (ATmega328P) + Sensor Ultrasónico HC-SR04
 * CONEXIONES: VCC -> 5V | GND -> GND | Trig -> D9 | Echo -> D10
 */

const int PIN_TRIG = 9;
const int PIN_ECHO = 10;

const float VEL_SONIDO = 343.0;          // Velocidad del sonido en el aire (m/s)
const unsigned long INTERVALO_MS = 45;   // Muestreo cada 45 ms (~22.2 Hz, entre 20 y 25 Hz)
const float DISTANCIA_TOPE = 0.055;      // Distancia de parada frente al bloque blanco (m)

float d0 = 0.750;                        // Distancia inicial por defecto (m)
unsigned long t_inicio_ensayo = 0;
unsigned long t_ultimo_muestreo = 0;
bool midiendo = false;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);
}

// Función para medir la distancia actual d(t) en metros (unidades SI)
float medirDistancia() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  // Timeout de 25000 us (~4.2 metros máx) para no bloquear el ciclo de muestreo
  unsigned long t_eco_us = pulseIn(PIN_ECHO, HIGH, 25000);

  if (t_eco_us == 0) {
    return -1.0; // Indica lectura fuera de rango o eco perdido
  }

  float t_eco_s = t_eco_us / 1000000.0;
  float d = (VEL_SONIDO * t_eco_s) / 2.0; // d(t) = (vs * t_eco) / 2
  return d;
}

void loop() {
  // Escuchar comandos provenientes de la interfaz en Python
  if (Serial.available() > 0) {
    char comando = Serial.read();

    // 'C': Calibrar distancia inicial d0 con el carrito en el punto de partida
    if (comando == 'C' || comando == 'c') {
      float suma = 0;
      int validas = 0;
      for (int i = 0; i < 10; i++) {
        float lec = medirDistancia();
        if (lec > 0.02 && lec < 2.00) {
          suma += lec;
          validas++;
        }
        delay(30);
      }
      if (validas > 0) {
        d0 = suma / validas;
      }
      Serial.print("CAL:");
      Serial.println(d0, 4);
    }
    // 'I': Iniciar captura en tiempo real del ensayo
    else if (comando == 'I' || comando == 'i') {
      float lec_inicial = medirDistancia();
      if (lec_inicial > 0.15 && lec_inicial < 1.50) {
        d0 = lec_inicial; // Fija d0 automáticamente al iniciar la carrera
      }
      t_inicio_ensayo = millis();
      t_ultimo_muestreo = t_inicio_ensayo;
      midiendo = true;
      Serial.println("START");
      // Emitir punto inicial (t = 0.000 s, d = d0, x = 0.000 m)
      Serial.print(0.000, 3);
      Serial.print(",");
      Serial.print(d0, 4);
      Serial.print(",");
      Serial.println(0.0000, 4);
    }
    // 'S': Detener captura manualmente
    else if (comando == 'S' || comando == 's') {
      midiendo = false;
      Serial.println("FIN");
    }
  }

  // Bucle principal de adquisición a 22.2 Hz (cada 45 ms)
  if (midiendo) {
    unsigned long t_actual = millis();
    if (t_actual - t_ultimo_muestreo >= INTERVALO_MS) {
      t_ultimo_muestreo = t_actual;

      float t_seg = (t_actual - t_inicio_ensayo) / 1000.0;
      float d = medirDistancia();

      if (d > 0.01 && d < 1.50) {
        float x = d0 - d; // Transformación de sistema de referencia: x(t) = d0 - d(t)
        if (x < 0.0) x = 0.0;

        // Enviar trama CSV por puerto serial: "t,d,x"
        Serial.print(t_seg, 3);
        Serial.print(",");
        Serial.print(d, 4);
        Serial.print(",");
        Serial.println(x, 4);

        // Detener automáticamente si el carrito llega al bloque blanco de tope (df <= 0.055 m)
        if (d <= DISTANCIA_TOPE && t_seg > 0.30) {
          midiendo = false;
          Serial.println("FIN");
        }
      }
    }
  }
}